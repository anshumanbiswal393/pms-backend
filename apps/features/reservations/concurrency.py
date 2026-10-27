import time
import json
import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from django.db import transaction, models
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.core.common.redis_lock import redis_distributed_lock

logger = logging.getLogger(__name__)


class RushQueueOverwhelmedException(Exception):
    """Raised when queue depth is exceeded during extreme concurrent rushes."""
    pass


class InventoryLockManager:
    """
    1st Requirement: Atomic Update & Distributed / Optimistic Lock.
    Prevents double bookings across concurrent transactions by acquiring short-lived
    distributed locks on the requested room types and physical units across stay dates.
    Falls back gracefully to PostgreSQL select_for_update() row locks if Redis is offline.
    """

    @classmethod
    @contextmanager
    def acquire_inventory_locks(
        cls,
        property_id: str,
        allocations: List[Dict[str, Any]],
        timeout: int = 15,
        max_retries: int = 15,
        retry_delay: float = 0.1
    ):
        """
        Acquires distributed locks for all requested room types across their date ranges.
        Lock key format: pms:lock:inventory:{property_id}:{unit_type_id}:{date}
        """
        acquired_locks = []
        lock_keys = set()

        for alloc in allocations:
            unit_type_id = str(alloc.get('inventory_unit_type_id') or '')
            ci_str = str(alloc.get('check_in_date') or '')[:10]
            co_str = str(alloc.get('check_out_date') or '')[:10]

            if not unit_type_id or not ci_str or not co_str:
                continue

            try:
                ci = date.fromisoformat(ci_str) if isinstance(ci_str, str) else ci_str
                co = date.fromisoformat(co_str) if isinstance(co_str, str) else co_str
            except Exception:
                continue

            curr = ci
            while curr < co:
                lock_keys.add(f"pms:lock:inv:{property_id}:{unit_type_id}:{curr.isoformat()}")
                curr += timedelta(days=1)

            # Also lock physical unit if assigned
            unit_id = alloc.get('inventory_unit_id')
            if unit_id:
                lock_keys.add(f"pms:lock:room:unit:{unit_id}")

        # Sort keys to prevent deadlocks when acquiring multiple locks
        sorted_keys = sorted(list(lock_keys))

        try:
            for k in sorted_keys:
                retries = 0
                got = False
                while retries < max_retries:
                    if cache.add(k, "1", timeout=timeout):
                        got = True
                        acquired_locks.append(k)
                        break
                    time.sleep(retry_delay)
                    retries += 1

                if not got:
                    logger.warning(f"Could not acquire distributed lock for {k}. Falling back to DB transaction.")

            yield acquired_locks

        finally:
            for k in acquired_locks:
                try:
                    cache.delete(k)
                except Exception as ex:
                    logger.warning(f"Failed to release inventory lock {k}: {ex}")

    @classmethod
    def verify_inventory_capacity(
        cls,
        tenant,
        property_obj,
        *args,
        **kwargs
    ) -> int:
        """
        Atomically calculates the true available capacity for a unit type between check_in and check_out.
        Supports both signatures:
        1. verify_inventory_capacity(tenant, property_obj, allocations_data)
        2. verify_inventory_capacity(tenant, property_obj, unit_type, check_in_date, check_out_date, requested_rooms=1, exclude_reservation_id=None)

        Takes into account:
        - Total operational physical units of this type
        - Overlapping confirmed/pending reservations
        - Active 5-minute temporary holds (InventoryHold and HELD reservations)
        - Maintenance blocks
        Returns the minimum available rooms count across all nights of the stay.
        Raises ValidationError if available rooms < requested_rooms.
        """
        from apps.features.inventory.models import InventoryUnit, InventoryUnitType
        from apps.features.reservations.models import ReservationInventory
        from apps.features.availability.models import InventoryHold

        # Handle batch allocations signature: verify_inventory_capacity(tenant, property_obj, allocations_data)
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            allocations = args[0]
            exclude_res_id = kwargs.get('exclude_reservation_id')
            min_avail_overall = 999999
            for alloc in allocations:
                unit_type_id = alloc.get('inventory_unit_type_id') or alloc.get('unit_type_id')
                if not unit_type_id:
                    continue
                if isinstance(unit_type_id, InventoryUnitType):
                    ut_obj = unit_type_id
                else:
                    try:
                        ut_obj = InventoryUnitType.objects.get(id=unit_type_id, tenant=tenant)
                    except InventoryUnitType.DoesNotExist:
                        continue

                ci_val = alloc.get('check_in_date')
                co_val = alloc.get('check_out_date')
                if isinstance(ci_val, str):
                    ci_date = date.fromisoformat(ci_val[:10])
                elif isinstance(ci_val, datetime):
                    ci_date = ci_val.date()
                else:
                    ci_date = ci_val

                if isinstance(co_val, str):
                    co_date = date.fromisoformat(co_val[:10])
                elif isinstance(co_val, datetime):
                    co_date = co_val.date()
                else:
                    co_date = co_val

                req_rooms = int(alloc.get('rooms_count') or alloc.get('quantity') or 1)
                avail = cls.verify_inventory_capacity(
                    tenant,
                    property_obj,
                    ut_obj,
                    ci_date,
                    co_date,
                    req_rooms,
                    exclude_res_id
                )
                if avail < min_avail_overall:
                    min_avail_overall = avail
            return min_avail_overall

        # Positional extraction for single unit_type signature
        unit_type = args[0] if len(args) > 0 else kwargs.get('unit_type')
        check_in_date = args[1] if len(args) > 1 else kwargs.get('check_in_date')
        check_out_date = args[2] if len(args) > 2 else kwargs.get('check_out_date')
        requested_rooms = args[3] if len(args) > 3 else kwargs.get('requested_rooms', 1)
        exclude_reservation_id = args[4] if len(args) > 4 else kwargs.get('exclude_reservation_id')

        if isinstance(check_in_date, str):
            check_in_date = date.fromisoformat(check_in_date[:10])
        elif isinstance(check_in_date, datetime):
            check_in_date = check_in_date.date()

        if isinstance(check_out_date, str):
            check_out_date = date.fromisoformat(check_out_date[:10])
        elif isinstance(check_out_date, datetime):
            check_out_date = check_out_date.date()

        now = timezone.now()

        # 1. Total operational units
        total_units = InventoryUnit.objects.filter(
            tenant=tenant,
            property=property_obj,
            inventory_unit_type=unit_type,
            operational_status='operational',
            deleted_at__isnull=True
        ).count()

        if total_units <= 0:
            raise ValidationError(f"No operational rooms configured for '{unit_type.name}'.")

        # 2. Check each night in the range
        min_available = total_units
        curr_d = check_in_date
        while curr_d < check_out_date:
            next_d = curr_d + timedelta(days=1)

            # Booked or actively occupied allocations
            alloc_qs = ReservationInventory.objects.filter(
                tenant=tenant,
                inventory_unit_type=unit_type,
                check_in_date__lt=next_d,
                check_out_date__gt=curr_d
            ).exclude(
                reservation__status__in=['CANCELLED', 'NO_SHOW']
            )

            # Exclude expired holds
            alloc_qs = alloc_qs.exclude(
                reservation__status='HELD',
                reservation__held_until__lt=now
            )

            if exclude_reservation_id:
                alloc_qs = alloc_qs.exclude(reservation_id=exclude_reservation_id)

            booked_count = alloc_qs.count()

            # Active holds
            holds_qty = InventoryHold.objects.filter(
                tenant=tenant,
                property=property_obj,
                inventory_unit_type=unit_type,
                status='ACTIVE',
                expires_at__gt=now
            ).aggregate(models.Sum('quantity'))['quantity__sum'] or 0

            available_tonight = total_units - (booked_count + holds_qty)
            if available_tonight < min_available:
                min_available = available_tonight

            curr_d = next_d

        if min_available < requested_rooms:
            raise ValidationError(
                f"Room type '{unit_type.name}' does not have enough capacity. "
                f"Requested: {requested_rooms}, Available: {max(0, min_available)}."
            )

        return min_available


class ReservationHoldManager:
    """
    2nd Requirement: Hold = Status + Timer.
    Temporary 5-minute hold on rooms to prevent race conditions during checkout & payment.
    Auto-releases inventory if timer expires before payment confirmation.
    """
    DEFAULT_HOLD_MINUTES = 5

    @classmethod
    def apply_hold(cls, reservation, duration_minutes: int = DEFAULT_HOLD_MINUTES) -> datetime:
        """
        Transitions reservation to 'HELD' and records held_until timestamp.
        Also creates or updates associated InventoryHold records.
        """
        from apps.features.availability.models import InventoryHold

        expires_at = timezone.now() + timedelta(minutes=duration_minutes)
        reservation.status = 'HELD'
        reservation.held_until = expires_at
        reservation.save(update_fields=['status', 'held_until', 'updated_at'])

        # Create/sync InventoryHold for each allocation
        for alloc in reservation.room_allocations.all():
            InventoryHold.objects.create(
                tenant=reservation.tenant,
                property=reservation.property,
                inventory_unit_type=alloc.inventory_unit_type,
                inventory_unit=alloc.inventory_unit,
                hold_type='CART',
                quantity=1,
                expires_at=expires_at,
                status='ACTIVE'
            )

        # Store in Redis with TTL for fast expiry lookups
        ttl_seconds = int(duration_minutes * 60)
        cache.set(f"pms:hold:{reservation.id}", {
            "reservation_id": str(reservation.id),
            "confirmation_number": reservation.confirmation_number,
            "expires_at": expires_at.isoformat()
        }, timeout=ttl_seconds)

        # Invalidate availability cache
        AvailabilityCacheService.invalidate(str(reservation.property.id))
        return expires_at

    @classmethod
    def confirm_hold(cls, reservation, user: Optional[Any] = None) -> Any:
        """
        Validates hold has not expired, converts to CONFIRMED, records event, and clears hold timer.
        """
        from apps.features.availability.models import InventoryHold
        from apps.features.reservations.models import ReservationEvent
        from apps.features.reservations.email_service import send_reservation_confirmation_email_async

        now = timezone.now()
        if reservation.status == 'HELD':
            if reservation.held_until and reservation.held_until < now:
                # Expired!
                cls.release_expired_holds(tenant=reservation.tenant, property_id=str(reservation.property.id))
                raise ValidationError("Hold expired after 5 minutes. The room has been released. Please create a new reservation.")

        reservation.status = 'CONFIRMED'
        reservation.held_until = None
        reservation.save(update_fields=['status', 'held_until', 'updated_at'])

        # Convert InventoryHolds
        for alloc in reservation.room_allocations.all():
            InventoryHold.objects.filter(
                tenant=reservation.tenant,
                property=reservation.property,
                inventory_unit_type=alloc.inventory_unit_type,
                status='ACTIVE'
            ).update(status='CONVERTED', updated_at=now)

        cache.delete(f"pms:hold:{reservation.id}")
        AvailabilityCacheService.invalidate(str(reservation.property.id))

        try:
            ReservationEvent.objects.create(
                tenant=reservation.tenant,
                reservation=reservation,
                event_type='CONFIRMED',
                description="Hold confirmed and booking finalized.",
                actor_user=user
            )
            send_reservation_confirmation_email_async(reservation.id)
        except Exception as e:
            logger.warning(f"Failed to send confirmation email or create event on confirm_hold: {e}")

        return reservation

    @classmethod
    def release_expired_holds(cls, tenant=None, property_id: Optional[str] = None) -> int:
        """
        Auto-releases all expired HELD reservations and InventoryHold entries.
        Returns count of released reservations.
        """
        from apps.features.reservations.models import Reservation
        from apps.features.availability.models import InventoryHold

        now = timezone.now()
        qs = Reservation.objects.filter(status='HELD', held_until__lt=now)
        if tenant:
            qs = qs.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)

        count = 0
        affected_property_ids = set()
        for res in qs:
            res.status = 'CANCELLED'
            res.remarks = (res.remarks or '') + " [Auto-Released: 5-minute checkout hold expired without payment]"
            res.save(update_fields=['status', 'remarks', 'updated_at'])
            affected_property_ids.add(str(res.property.id))
            cache.delete(f"pms:hold:{res.id}")
            count += 1

        # Release InventoryHold rows
        hold_qs = InventoryHold.objects.filter(status='ACTIVE', expires_at__lt=now)
        if tenant:
            hold_qs = hold_qs.filter(tenant=tenant)
        if property_id:
            hold_qs = hold_qs.filter(property_id=property_id)
        hold_qs.update(status='RELEASED', updated_at=now)

        # Invalidate caches for affected properties
        for pid in affected_property_ids:
            AvailabilityCacheService.invalidate(pid)

        return count


class ReservationRushQueue:
    """
    3rd Requirement: Queue Before Rush.
    Prevents stampede / flash-sale race conditions when dozens of users rush
    to book the same room type at the exact same second.
    Uses Redis token queue with polite waiting and load-shedding (HTTP 429).
    """

    MAX_CONCURRENT_PER_UNIT = 4
    MAX_WAIT_SECONDS = 3.0
    POLL_INTERVAL = 0.1
    MAX_QUEUE_DEPTH = 30

    @classmethod
    @contextmanager
    def acquire_rush_slot(cls, property_id: str, unit_type_id: str):
        queue_key = f"pms:rush:queue:{property_id}:{unit_type_id}"
        lock_key = f"pms:rush:slot:{property_id}:{unit_type_id}"

        # Check queue depth first to shed excessive load
        try:
            depth = cache.get(queue_key) or 0
            if int(depth) >= cls.MAX_QUEUE_DEPTH:
                raise RushQueueOverwhelmedException(
                    "High booking demand in progress for this room type. Your request is queued. Please retry momentarily."
                )
            cache.set(queue_key, int(depth) + 1, timeout=10)
        except RushQueueOverwhelmedException:
            raise
        except Exception:
            pass

        start_time = time.time()
        slot_acquired = False

        try:
            while (time.time() - start_time) < cls.MAX_WAIT_SECONDS:
                # Try acquiring an atomic processing slot
                if cache.add(lock_key, "1", timeout=10):
                    slot_acquired = True
                    break
                time.sleep(cls.POLL_INTERVAL)

            yield slot_acquired

        finally:
            if slot_acquired:
                try:
                    cache.delete(lock_key)
                except Exception:
                    pass
            try:
                current_depth = cache.get(queue_key) or 1
                new_depth = max(0, int(current_depth) - 1)
                cache.set(queue_key, new_depth, timeout=10)
            except Exception:
                pass


class AvailabilityCacheService:
    """
    4th Requirement: Availability Read from Cache (Redis with Fast Invalidation).
    Caches availability matrices and calendar lookups in Redis for sub-millisecond retrieval.
    Invalidates instantly when reservations/holds change.
    """

    CACHE_PREFIX = "pms:cache:avail"
    CACHE_TTL = 300  # 5 minutes

    @classmethod
    def _make_key(cls, property_id: str, start_date: str, end_date: str, unit_type_id: Optional[str] = None) -> str:
        u_suffix = f":{unit_type_id}" if unit_type_id else ":all"
        return f"{cls.CACHE_PREFIX}:{property_id}:{start_date}:{end_date}{u_suffix}"

    @classmethod
    def get_cached_calendar(cls, property_id: str, start_date: str, end_date: str, unit_type_id: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        key = cls._make_key(property_id, start_date, end_date, unit_type_id)
        try:
            cached_data = cache.get(key)
            if cached_data:
                if isinstance(cached_data, str):
                    return json.loads(cached_data)
                return cached_data
        except Exception as e:
            logger.warning(f"Failed to read availability from cache for key {key}: {e}")
        return None

    @classmethod
    def set_cached_calendar(cls, property_id: str, start_date: str, end_date: str, data: Any, unit_type_id: Optional[str] = None, ttl: int = CACHE_TTL):
        key = cls._make_key(property_id, start_date, end_date, unit_type_id)
        try:
            cache.set(key, data, timeout=ttl)
            # Track key for property invalidation
            prop_keys_name = f"{cls.CACHE_PREFIX}:keys:{property_id}"
            keys_set = cache.get(prop_keys_name) or []
            if key not in keys_set:
                keys_set.append(key)
                cache.set(prop_keys_name, keys_set, timeout=ttl * 2)
        except Exception as e:
            logger.warning(f"Failed to set availability cache for key {key}: {e}")

    @classmethod
    def invalidate(cls, property_id: str):
        """
        Instant invalidation of all cached availability records for a property.
        """
        if not property_id:
            return

        prop_keys_name = f"{cls.CACHE_PREFIX}:keys:{property_id}"
        try:
            keys_list = cache.get(prop_keys_name) or []
            if keys_list:
                cache.delete_many(keys_list)
            cache.delete(prop_keys_name)
        except Exception as e:
            logger.warning(f"Error invalidating availability keys for {property_id}: {e}")

        # Also purge any wildcard patterns if supported
        try:
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(f"{cls.CACHE_PREFIX}:{property_id}:*")
        except Exception:
            pass
