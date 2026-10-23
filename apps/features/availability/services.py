from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from apps.features.availability.models import InventoryAvailability, InventoryRestriction, InventoryHold
from apps.features.inventory.models import InventoryUnitType

class AvailabilityCalculationService:
    @staticmethod
    def get_active_holds_quantity(tenant, property_id, unit_type_id, date):
        # Hold is active if status = ACTIVE and expires_at > now
        # Note: Date holds are scoped by their timestamp expires_at
        holds = InventoryHold.objects.filter(
            tenant=tenant,
            property_id=property_id,
            inventory_unit_type_id=unit_type_id,
            status='ACTIVE',
            expires_at__gt=timezone.now()
        )
        return sum(hold.quantity for hold in holds)

    @classmethod
    def calculate_available(cls, tenant, property_id, unit_type_id, date, allocated_count, overbooking_limit, sold_count, blocked_count):
        active_holds = cls.get_active_holds_quantity(tenant, property_id, unit_type_id, date)
        available = (allocated_count + overbooking_limit) - (sold_count + blocked_count + active_holds)
        return max(0, available)


class HoldService:
    @staticmethod
    def create_hold(tenant, property, unit_type, expires_at, quantity=1, hold_type='CART', unit=None):
        if property.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        if unit_type.property != property:
            raise ValidationError("Unit type must belong to the resolved property context.")
        if unit and unit.inventory_unit_type != unit_type:
            raise ValidationError("Unit type must match the specific unit's type.")

        return InventoryHold.objects.create(
            tenant=tenant, property=property, inventory_unit_type=unit_type,
            inventory_unit=unit, hold_type=hold_type, quantity=quantity,
            expires_at=expires_at, status='ACTIVE'
        )

    @staticmethod
    def release_hold(hold):
        hold.status = 'RELEASED'
        hold.save(update_fields=['status', 'updated_at'])
        return hold

    @staticmethod
    def convert_hold(hold):
        hold.status = 'CONVERTED'
        hold.save(update_fields=['status', 'updated_at'])
        return hold

    @staticmethod
    def expire_holds():
        expired_count = InventoryHold.objects.filter(
            status='ACTIVE',
            expires_at__lt=timezone.now()
        ).update(
            status='RELEASED',
            updated_at=timezone.now()
        )
        return expired_count


class RestrictionService:
    @staticmethod
    def get_restriction(tenant, property_id, date, unit_type_id=None, rate_plan_id=None, restriction_type=None):
        qs = InventoryRestriction.objects.filter(
            tenant=tenant,
            property_id=property_id,
            date=date
        )
        if unit_type_id:
            qs = qs.filter(models.Q(inventory_unit_type_id=unit_type_id) | models.Q(inventory_unit_type__isnull=True))
        if rate_plan_id:
            qs = qs.filter(models.Q(rate_plan_id=rate_plan_id) | models.Q(rate_plan_id__isnull=True))
        if restriction_type:
            qs = qs.filter(restriction_type=restriction_type)
        return qs.first()

    @classmethod
    def is_stop_sell(cls, tenant, property_id, date, unit_type_id=None, rate_plan_id=None):
        r = cls.get_restriction(tenant, property_id, date, unit_type_id, rate_plan_id, 'STOP_SELL')
        return r is not None

    @classmethod
    def is_cta(cls, tenant, property_id, date, unit_type_id=None, rate_plan_id=None):
        r = cls.get_restriction(tenant, property_id, date, unit_type_id, rate_plan_id, 'CTA')
        return r is not None

    @classmethod
    def is_ctd(cls, tenant, property_id, date, unit_type_id=None, rate_plan_id=None):
        r = cls.get_restriction(tenant, property_id, date, unit_type_id, rate_plan_id, 'CTD')
        return r is not None

    @classmethod
    def validate_min_los(cls, tenant, property_id, date, stay_length, unit_type_id=None, rate_plan_id=None):
        r = cls.get_restriction(tenant, property_id, date, unit_type_id, rate_plan_id, 'MIN_LOS')
        if r and r.restriction_value and stay_length < r.restriction_value:
            return False, f"Stay length {stay_length} is less than minimum length of stay restriction ({r.restriction_value})."
        return True, ""

    @classmethod
    def validate_max_los(cls, tenant, property_id, date, stay_length, unit_type_id=None, rate_plan_id=None):
        r = cls.get_restriction(tenant, property_id, date, unit_type_id, rate_plan_id, 'MAX_LOS')
        if r and r.restriction_value and stay_length > r.restriction_value:
            return False, f"Stay length {stay_length} exceeds maximum length of stay restriction ({r.restriction_value})."
        return True, ""


class AvailabilityCalendarService:
    @staticmethod
    def get_calendar(tenant, property_id, start_date, end_date, unit_type_id=None):
        from apps.features.reservations.concurrency import AvailabilityCacheService
        cached_result = AvailabilityCacheService.get_cached_calendar(
            property_id=str(property_id),
            start_date=start_date,
            end_date=end_date,
            unit_type_id=str(unit_type_id) if unit_type_id else None
        )
        if cached_result is not None:
            return cached_result

        unit_types = InventoryUnitType.objects.filter(tenant=tenant, property_id=property_id)
        if unit_type_id:
            unit_types = unit_types.filter(id=unit_type_id)

        avail_qs = InventoryAvailability.objects.filter(
            tenant=tenant, property_id=property_id, date__range=[start_date, end_date]
        )
        rest_qs = InventoryRestriction.objects.filter(
            tenant=tenant, property_id=property_id, date__range=[start_date, end_date]
        )

        avail_map = {}
        for a in avail_qs:
            avail_map[(a.inventory_unit_type_id, a.date)] = a

        rest_map = {}
        for r in rest_qs:
            key = (r.inventory_unit_type_id, r.date)
            if key not in rest_map:
                rest_map[key] = []
            rest_map[key].append(r)

        calendar = []
        curr_date = start_date
        while curr_date <= end_date:
            for ut in unit_types:
                avail_record = avail_map.get((ut.id, curr_date))
                
                allocated = avail_record.allocated_count if avail_record else 0
                sold = avail_record.sold_count if avail_record else 0
                blocked = avail_record.blocked_count if avail_record else 0
                overbooking = avail_record.overbooking_limit if avail_record else 0
                
                active_holds = AvailabilityCalculationService.get_active_holds_quantity(
                    tenant, property_id, ut.id, curr_date
                )
                
                available = (allocated + overbooking) - (sold + blocked + active_holds)
                available = max(0, available)
                
                # Retrieve specific restrictions
                restrictions = rest_map.get((ut.id, curr_date), [])
                restrictions += rest_map.get((None, curr_date), []) # Add general restrictions
                
                rest_data = {
                    'CTA': False,
                    'CTD': False,
                    'STOP_SELL': False,
                    'MIN_LOS': None,
                    'MAX_LOS': None,
                }
                for r in restrictions:
                    if r.restriction_type in ['CTA', 'CTD', 'STOP_SELL']:
                        rest_data[r.restriction_type] = True
                      # For LOS controls, store value
                    elif r.restriction_type in ['MIN_LOS', 'MAX_LOS']:
                        rest_data[r.restriction_type] = r.restriction_value

                calendar.append({
                    'date': curr_date.isoformat(),
                    'unit_type': {
                        'id': str(ut.id),
                        'code': ut.code,
                        'name': ut.name,
                    },
                    'allocated_count': allocated,
                    'sold_count': sold,
                    'blocked_count': blocked,
                    'overbooking_limit': overbooking,
                    'active_holds_count': active_holds,
                    'available_count': available,
                    'restrictions': rest_data
                })
            curr_date += timedelta(days=1)
            
        AvailabilityCacheService.set_cached_calendar(
            property_id=str(property_id),
            start_date=start_date,
            end_date=end_date,
            calendar_data=calendar,
            ttl=120,
            unit_type_id=str(unit_type_id) if unit_type_id else None
        )
        return calendar


class AvailabilitySyncService:
    @staticmethod
    def rebuild_matrix(tenant, property_id, start_date, end_date):
        avail_records = InventoryAvailability.objects.filter(
            tenant=tenant, property_id=property_id, date__range=[start_date, end_date]
        )
        for record in avail_records:
            record.save()
        return len(avail_records)
