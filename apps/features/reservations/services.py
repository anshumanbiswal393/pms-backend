import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationRateSnapshot, ReservationGuest, ReservationEvent,
    ReservationServiceAddon, ReservationPackage, ReservationCoupon
)
from apps.features.crm.models import GuestProfile, GuestContact, GuestDocument
from apps.features.inventory.models import InventoryUnit, InventoryUnitType
from apps.features.rates.models import RatePlan, RatePlanVersion, Service, HospitalityPackage, Coupon, MealPlan, TenantMealPlanPrice

from apps.core.common.redis_lock import redis_distributed_lock

def check_room_availability(tenant, room, check_in_date, check_out_date, exclude_allocation_id=None):
    """
    Checks if a physical room (InventoryUnit) is available on the specified dates.
    Uses a Redis distributed lock to serialize checks and prevent concurrent double bookings.
    If Redis fails, falls back to a PostgreSQL row-level lock (select_for_update) on the room.
    """
    lock_key = f"pms:lock:room:unit:{room.id}"
    with redis_distributed_lock(lock_key) as acquired:
        if not acquired:
            # Fallback row-level database lock
            list(InventoryUnit.objects.select_for_update().filter(id=room.id))
            
        overlapping = ReservationInventory.objects.filter(
            tenant=tenant,
            inventory_unit=room,
            check_in_date__lt=check_out_date,
            check_out_date__gt=check_in_date
        ).exclude(reservation__status='CANCELLED')
        
        if exclude_allocation_id:
            overlapping = overlapping.exclude(id=exclude_allocation_id)
            
        if overlapping.exists():
            raise ValidationError(f"Room {room.name} is already booked or occupied for these dates.")

def make_serializable(data):
    if isinstance(data, dict):
        return {k: make_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [make_serializable(x) for x in data]
    elif isinstance(data, uuid.UUID):
        return str(data)
    elif isinstance(data, Decimal):
        return str(data)
    elif hasattr(data, 'isoformat'):
        return data.isoformat()
    return data

def calculate_item_tax(tenant, item_price, per_night_tariff=None, guests_count=1):
    """
    Calculates tax by dynamically inspecting DB SystemTax rules (min_tariff, max_tariff, calculation_base, flat_amount, rate)
    without any hardcoded rates or thresholds. Returns tuple of (applicable_tax, tax_label).
    """
    from apps.core.common.models import SystemTax
    from django.db.models import Q
    
    active_rates = SystemTax.objects.filter(
        Q(tenant=tenant) | Q(tenant__isnull=True),
        status__iexact='active'
    )
    tariff = Decimal(str(per_night_tariff)) if per_night_tariff is not None else Decimal(str(item_price))
    item_amt = Decimal(str(item_price))
    
    applicable_tax = Decimal('0.00')
    tax_names = []

    for rate_obj in active_rates:
        # Tariff slab filtering dynamically read from DB columns min_tariff & max_tariff
        if rate_obj.min_tariff is not None and tariff < rate_obj.min_tariff:
            continue
        if rate_obj.max_tariff is not None and rate_obj.max_tariff > Decimal('0.00') and tariff > rate_obj.max_tariff:
            continue

        base = (rate_obj.calculation_base or 'folio_subtotal').lower()
        rate_pct = Decimal(str(rate_obj.rate or '0.00'))
        flat_amt = Decimal(str(rate_obj.flat_amount or '0.00'))

        tax_item = Decimal('0.00')
        # If rate percentage is specified (e.g. GST 10%, 15%, 5%), compute percentage of item amount
        if rate_pct > Decimal('0.00'):
            tax_item += item_amt * (rate_pct / Decimal('100.0'))
        
        # If flat fixed amount is specified (e.g. per-night fee or per-guest fee)
        if flat_amt > Decimal('0.00'):
            if base == 'per_guest_night':
                tax_item += flat_amt * Decimal(str(guests_count))
            else:
                tax_item += flat_amt

        applicable_tax += tax_item

        if rate_obj.name:
            tax_names.append(rate_obj.name)

    label_str = ", ".join(tax_names) if tax_names else "GST Tax"
    return applicable_tax, label_str

class BookingEngine:
    @staticmethod
    def generate_confirmation_number():
        return f"RET-{uuid.uuid4().hex[:8].upper()}"

    @classmethod
    @transaction.atomic
    def create_booking(cls, tenant, property_obj, booking_data, user=None):
        """
        Creates a Reservation transaction, room allocations, guest linkings, and daily snapshots.
        Expected booking_data format:
        {
            'primary_guest_id': UUID,
            'reservation_source_id': UUID,
            'group_block_id': UUID (optional),
            'corporate_account_id': UUID (optional),
            'reservation_type': str,
            'market_segment': str,
            'origin_country_id': UUID (optional),
            'arrival_date': date,
            'departure_date': date,
            'booking_reference': str (optional),
            'notes': str (optional),
            'remarks': str (optional),
            'special_requests': str (optional),
            'allocations': [
                {
                    'inventory_unit_type_id': UUID,
                    'check_in_date': date,
                    'check_out_date': date,
                    'adult_count': int,
                    'child_count': int,
                    'infant_count': int,
                    'rate_plan_id': UUID,
                    'nightly_rates': [
                        {
                            'date': date,
                            'amount': Decimal,
                            'rate_plan_version_id': UUID
                        }
                    ]
                }
            ]
        }
        """
        # Resolve Primary Guest (either lookup by UUID or create inline)
        if booking_data.get('primary_guest_id'):
            primary_guest = GuestProfile.objects.get(id=booking_data['primary_guest_id'], tenant=tenant)
        else:
            full_name = booking_data.get('fullName') or booking_data.get('event_organizer_name') or "Inline Guest"
            email = booking_data.get('email') or booking_data.get('event_organizer_email') or ""
            phone = booking_data.get('phone') or booking_data.get('event_organizer_contact') or ""
            address = booking_data.get('address') or booking_data.get('event_organizer_billing_address') or ""
            nationality = booking_data.get('nationality') or ""
            id_type = booking_data.get('idType') or "PASSPORT"
            id_number = booking_data.get('idNumber') or ""

            parts = full_name.strip().split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else "Guest"

            contact = None
            if email or phone:
                contact = GuestContact.objects.filter(tenant=tenant, email=email, phone=phone).first()
                if not contact and email:
                    contact = GuestContact.objects.filter(tenant=tenant, email=email).first()
                if not contact and phone:
                    contact = GuestContact.objects.filter(tenant=tenant, phone=phone).first()

            if contact:
                primary_guest = contact.guest
                if email and contact.email != email:
                    contact.email = email
                if phone and contact.phone != phone:
                    contact.phone = phone
                if address:
                    contact.address_line_1 = address
                contact.save()
            else:
                primary_guest = GuestProfile.objects.create(
                    tenant=tenant,
                    first_name=first_name,
                    last_name=last_name,
                    nationality=nationality,
                    guest_type='DOMESTIC'
                )
                GuestContact.objects.create(
                    tenant=tenant,
                    guest=primary_guest,
                    email=email,
                    phone=phone,
                    address_line_1=address,
                    is_primary=True
                )
                if id_number:
                    doc_type = 'PASSPORT'
                    id_type_upper = id_type.upper()
                    if 'ID' in id_type_upper or 'CARD' in id_type_upper or 'AADHAAR' in id_type_upper:
                        doc_type = 'NATIONAL_ID'
                    elif 'LICENSE' in id_type_upper or 'LICENCE' in id_type_upper or 'DRIVING' in id_type_upper:
                        doc_type = 'DRIVING_LICENCE'

                    GuestDocument.objects.create(
                        tenant=tenant,
                        guest=primary_guest,
                        document_type=doc_type,
                        document_number=id_number,
                        is_verified=False
                    )
        
        # Resolve Reservation Source
        res_source_id = booking_data.get('reservation_source_id')
        if not res_source_id:
            from apps.core.reference.models import ReservationSource
            source_name = booking_data.get('source') or 'Direct'
            source_obj = ReservationSource.objects.filter(tenant=tenant, name__iexact=source_name).first()
            if not source_obj:
                source_obj = ReservationSource.objects.filter(tenant=tenant).first()
            if source_obj:
                res_source_id = source_obj.id

        # Verify Corporate Account if provided
        corp_account = None
        if booking_data.get('corporate_account_id'):
            corp_account = CorporateAccount.objects.get(id=booking_data['corporate_account_id'], tenant=tenant)

        # Verify Group Block if provided
        group_block = None
        if booking_data.get('group_block_id'):
            group_block = GroupBlock.objects.get(id=booking_data['group_block_id'], tenant=tenant)
            if group_block.status != 'OPEN':
                raise ValidationError("Cannot book against a closed or released group block.")
            if group_block.cutoff_date < timezone.now().date():
                raise ValidationError("Group block cutoff date has passed.")

        # Convert special requests list to a comma-separated string
        spec_requests = booking_data.get('special_requests')
        if isinstance(spec_requests, list):
            spec_requests_str = ", ".join(spec_requests)
        else:
            spec_requests_str = spec_requests or ""

        # Create Reservation Header
        conf_no = cls.generate_confirmation_number()
        reservation = Reservation.objects.create(
            tenant=tenant,
            property=property_obj,
            primary_guest=primary_guest,
            reservation_source_id=res_source_id,
            group_block=group_block,
            corporate_account=corp_account,
            status='PENDING',
            booking_date=timezone.now().date(),
            arrival_date=booking_data['arrival_date'],
            departure_date=booking_data['departure_date'],
            booking_reference=booking_data.get('booking_reference'),
            notes=booking_data.get('notes'),
            remarks=booking_data.get('remarks'),
            special_requests=spec_requests_str,
            reservation_type=booking_data.get('reservation_type', 'Individual'),
            market_segment=booking_data.get('market_segment', 'Direct'),
            origin_country_id=booking_data.get('origin_country_id'),
            confirmation_number=conf_no,
            check_in_time=booking_data.get('check_in_time', '12:00 PM'),
            check_out_time=booking_data.get('check_out_time', '11:00 AM'),
            corporate_po_ref=booking_data.get('corporate_po_ref'),
            corporate_billing_type=booking_data.get('corporate_billing_type'),
            corporate_employee_id=booking_data.get('corporate_employee_id'),
            corporate_cost_center=booking_data.get('corporate_cost_center'),
            corporate_gst_number=booking_data.get('corporate_gst_number'),
            corporate_travel_purpose=booking_data.get('corporate_travel_purpose'),
            event_venue=booking_data.get('event_venue'),
            event_type=booking_data.get('event_type'),
            event_pax=booking_data.get('event_pax', 0),
            event_start_time=booking_data.get('event_start_time'),
            event_end_time=booking_data.get('event_end_time'),
            event_organizer_name=booking_data.get('event_organizer_name'),
            event_organizer_contact=booking_data.get('event_organizer_contact'),
            event_organizer_email=booking_data.get('event_organizer_email'),
            event_organizer_billing_address=booking_data.get('event_organizer_billing_address'),
            event_seating_arrangement=booking_data.get('event_seating_arrangement'),
            event_catering_menu=booking_data.get('event_catering_menu')
        )

        total_amount = Decimal('0.00')
        tax_amount = Decimal('0.00')

        # Create Allocations and Snapshots
        for alloc_item in booking_data.get('allocations', []):
            unit_type = InventoryUnitType.objects.get(id=alloc_item['inventory_unit_type_id'], tenant=tenant)
            
            unit_id = alloc_item.get('inventory_unit_id')
            assigned_unit = None
            if unit_id:
                try:
                    assigned_unit = InventoryUnit.objects.get(id=unit_id, tenant=tenant)
                except InventoryUnit.DoesNotExist:
                    pass

            if assigned_unit:
                check_room_availability(
                    tenant=tenant,
                    room=assigned_unit,
                    check_in_date=alloc_item['check_in_date'],
                    check_out_date=alloc_item['check_out_date']
                )

            # Create Reservation Inventory Allocation
            allocation = ReservationInventory.objects.create(
                tenant=tenant,
                reservation=reservation,
                inventory_unit_type=unit_type,
                inventory_unit=assigned_unit,
                check_in_date=alloc_item['check_in_date'],
                check_out_date=alloc_item['check_out_date'],
                adult_count=alloc_item.get('adult_count', 2),
                child_count=alloc_item.get('child_count', 0),
                infant_count=alloc_item.get('infant_count', 0),
                status='RESERVED',
                inventory_snapshot={
                    'name': unit_type.name,
                    'code': unit_type.code,
                    'base_occupancy': unit_type.base_occupancy,
                    'max_occupancy': unit_type.max_occupancy
                }
            )

            # Link primary guest snapshot inside ReservationGuest
            ReservationGuest.objects.create(
                tenant=tenant,
                reservation_inventory=allocation,
                guest=primary_guest,
                is_primary=True,
                guest_snapshot={
                    'first_name': primary_guest.first_name,
                    'last_name': primary_guest.last_name,
                    'email': primary_guest.contacts.filter(is_primary=True).first().email if primary_guest.contacts.filter(is_primary=True).exists() else None,
                    'phone': primary_guest.contacts.filter(is_primary=True).first().phone if primary_guest.contacts.filter(is_primary=True).exists() else None,
                }
            )

            # Create daily rate snapshots
            rate_plan = RatePlan.objects.get(id=alloc_item['rate_plan_id'], tenant=tenant)
            
            # Resolve guest chosen meal plan or rate plan default meal plan
            meal_plan = None
            meal_plan_id = alloc_item.get('meal_plan_id')
            if meal_plan_id:
                try:
                    meal_plan = MealPlan.objects.get(id=meal_plan_id)
                except (MealPlan.DoesNotExist, Exception):
                    pass
            if not meal_plan:
                meal_plan = rate_plan.default_meal_plan

            meal_price = Decimal("0.00")
            if meal_plan:
                unit_type_id = alloc_item.get('inventory_unit_type_id')
                mp_price_obj = None
                if unit_type_id:
                    mp_price_obj = TenantMealPlanPrice.objects.filter(
                        tenant=tenant, inventory_unit_type_id=unit_type_id, meal_plan=meal_plan
                    ).first()
                if mp_price_obj:
                    meal_price = mp_price_obj.price
                else:
                    meal_price = meal_plan.price_adjustment

            for rate_day in alloc_item.get('nightly_rates', []):
                version_id = rate_day.get('rate_plan_version_id')
                rate_version = None
                if version_id:
                    try:
                        rate_version = RatePlanVersion.objects.get(id=version_id, rate_plan=rate_plan)
                    except RatePlanVersion.DoesNotExist:
                        pass
                
                if not rate_version:
                    rate_version = rate_plan.versions.first()
                
                if not rate_version:
                    rate_version = RatePlanVersion.objects.create(
                        rate_plan=rate_plan,
                        version_number=1,
                        snapshot={}
                    )

                amount = Decimal(str(rate_day.get('amount', 0)))
                
                # Setup simple rate/policy snapshot representation
                rate_snapshot = {
                    'rate_plan_code': rate_plan.code,
                    'rate_plan_name': rate_plan.name,
                    'version_number': rate_version.version_number,
                    'amount': str(amount),
                    'meal_plan_code': meal_plan.code if meal_plan else None,
                    'meal_plan_name': meal_plan.name if meal_plan else None,
                    'meal_plan_price': str(meal_price) if meal_plan else "0.00",
                }
                policy_snapshot = {
                    'cancellation_policy_code': rate_plan.cancellation_policy.code if rate_plan.cancellation_policy else None,
                    'free_cancellation_hours': rate_plan.cancellation_policy.free_cancellation_hours if rate_plan.cancellation_policy else 0
                }

                ReservationRateSnapshot.objects.create(
                    tenant=tenant,
                    reservation_inventory=allocation,
                    date=rate_day['date'],
                    rate_plan=rate_plan,
                    rate_plan_version=rate_version,
                    amount_charged=amount,
                    rate_snapshot=rate_snapshot,
                    policy_snapshot=policy_snapshot
                )

                total_amount += amount
                
                # Dynamic tax calculation checking DB TaxRates (min_tariff, max_tariff, calculation_base)
                guest_cnt = allocation.adult_count + allocation.child_count
                item_tax_amt, _ = calculate_item_tax(tenant=tenant, item_price=amount, per_night_tariff=amount, guests_count=guest_cnt)
                tax_amount += item_tax_amt

        # Add packages
        packages = booking_data.get('packages', [])
        for pkg_id in packages:
            try:
                pkg = HospitalityPackage.objects.get(id=pkg_id, tenant=tenant)
                ReservationPackage.objects.create(
                    tenant=tenant,
                    reservation=reservation,
                    package=pkg,
                    price=pkg.price
                )
                total_amount += pkg.price
                pkg_tax_amt, _ = calculate_item_tax(tenant=tenant, item_price=pkg.price)
                tax_amount += pkg_tax_amt
            except HospitalityPackage.DoesNotExist:
                continue

        # Add services
        services = booking_data.get('services', [])
        for svc_id in services:
            try:
                svc = Service.objects.get(id=svc_id, tenant=tenant)
                ReservationServiceAddon.objects.create(
                    tenant=tenant,
                    reservation=reservation,
                    service=svc,
                    price=svc.price
                )
                total_amount += svc.price
                svc_tax_amt, _ = calculate_item_tax(tenant=tenant, item_price=svc.price)
                tax_amount += svc_tax_amt
            except Service.DoesNotExist:
                continue

        # Apply coupon
        coupon_code = booking_data.get('coupon_code') or booking_data.get('couponCode')
        discount_amount = Decimal('0.00')
        if coupon_code:
            code_str = str(coupon_code).strip()
            coupon = Coupon.objects.filter(tenant=tenant, code__iexact=code_str, is_active=True).first()
            if not coupon:
                coupon = Coupon.objects.filter(code__iexact=code_str, is_active=True).first()
            if coupon:
                if not coupon.max_uses or coupon.current_uses < coupon.max_uses:
                    if coupon.discount_type == 'FLAT':
                        discount_amount = coupon.discount_value
                    elif coupon.discount_type == 'PERCENTAGE':
                        discount_amount = total_amount * (coupon.discount_value / Decimal('100.0'))
                    
                    ReservationCoupon.objects.create(
                        tenant=tenant,
                        reservation=reservation,
                        coupon=coupon
                    )
                    coupon.current_uses += 1
                    coupon.save()

        reservation.total_amount = total_amount
        reservation.tax_amount = tax_amount
        reservation.discount_amount = discount_amount

        paid_val = Decimal(str(booking_data.get('paid_amount') or booking_data.get('paidAmount') or '0.00'))
        reservation.paid_amount = paid_val
        net_payable = (total_amount + tax_amount) - discount_amount
        reservation.balance_amount = max(Decimal('0.00'), net_payable - paid_val)
        reservation.status = 'CONFIRMED'
        reservation.save()

        if paid_val > Decimal('0.00'):
            payment_method_str = booking_data.get('payment_method') or booking_data.get('paymentMethod') or 'Cash'
            ReservationEvent.objects.create(
                tenant=tenant,
                reservation=reservation,
                event_type='PAYMENT_RECEIVED',
                description=f"Deposit Payment of ₹{paid_val} received via {payment_method_str}.",
                actor_user=user
            )

        # Update Group Block pickup count
        if group_block:
            group_block.pickup_rooms = group_block.pickup_rooms + len(booking_data.get('allocations', []))
            group_block.save(update_fields=['pickup_rooms'])

        # Create Timeline event
        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='CREATED',
            description=f"Reservation created with confirmation number {conf_no}.",
            actor_user=user,
            payload_diff=make_serializable(model_to_dict(reservation, exclude=['created_at', 'updated_at', 'deleted_at']))
        )

        return reservation


class RoomAssignmentEngine:
    @staticmethod
    @transaction.atomic
    def assign_room(tenant, allocation_id, room_id, user=None, upgrade_reason=None):
        """
        Assigns an InventoryUnit room to a ReservationInventory.
        Supports upgrade verification: if target room type differs from the booked type, handles and logs room upgrades.
        """
        allocation = ReservationInventory.objects.get(id=allocation_id, tenant=tenant)
        room = InventoryUnit.objects.get(id=room_id, tenant=tenant)

        # Check occupancy compatibility or status
        if room.operational_status != 'operational':
            raise ValidationError(f"Room {room.name} is currently offline/under maintenance.")

        check_room_availability(
            tenant=tenant,
            room=room,
            check_in_date=allocation.check_in_date,
            check_out_date=allocation.check_out_date,
            exclude_allocation_id=allocation.id
        )

        upgrade_from = None
        if room.inventory_unit_type != allocation.inventory_unit_type:
            # Upgrade occurred
            upgrade_from = allocation.inventory_unit_type
            if not upgrade_reason:
                raise ValidationError("Room type upgrade reason is required.")

        allocation.inventory_unit = room
        allocation.assigned_at = timezone.now()
        allocation.assigned_by = user
        allocation.status = 'ASSIGNED'
        if upgrade_from:
            allocation.upgrade_from_inventory_type = upgrade_from
            allocation.upgrade_reason = upgrade_reason
        allocation.save()

        # Update operational statuses
        room.housekeeping_status = 'dirty'  # Mark dirty upon guest assignment/prep
        room.save(update_fields=['housekeeping_status'])

        # Log timeline event
        desc = f"Room {room.name} assigned to reservation allocation."
        if upgrade_from:
            desc += f" Upgraded from {upgrade_from.code} due to: {upgrade_reason}"

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=allocation.reservation,
            event_type='ROOM_ASSIGNED',
            description=desc,
            actor_user=user,
            payload_diff=make_serializable({
                'allocation_id': str(allocation.id),
                'room_id': str(room.id),
                'room_name': room.name,
                'upgraded': upgrade_from is not None,
                'upgrade_from': str(upgrade_from.id) if upgrade_from else None
            })
        )

        return allocation

    @staticmethod
    @transaction.atomic
    def upgrade_room(tenant, allocation_id, new_inventory_type_id, upgrade_reason, user=None):
        allocation = ReservationInventory.objects.get(id=allocation_id, tenant=tenant)
        new_type = InventoryUnitType.objects.get(id=new_inventory_type_id, tenant=tenant)

        old_type = allocation.inventory_unit_type
        allocation.upgrade_from_inventory_type = old_type
        allocation.inventory_unit_type = new_type
        allocation.upgrade_reason = upgrade_reason
        allocation.assigned_by = user
        allocation.assigned_at = timezone.now()
        allocation.save()

        # Clear physical room assignment if it is no longer compatible
        if allocation.inventory_unit and allocation.inventory_unit.inventory_unit_type != new_type:
            allocation.inventory_unit = None
            allocation.save(update_fields=['inventory_unit'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=allocation.reservation,
            event_type='ROOM_UPGRADED',
            description=f"Room type upgraded from {old_type.code} to {new_type.code}. Reason: {upgrade_reason}",
            actor_user=user,
            payload_diff=make_serializable({
                'allocation_id': str(allocation.id),
                'old_type_id': str(old_type.id),
                'new_type_id': str(new_type.id),
                'upgrade_reason': upgrade_reason
            })
        )
        return allocation

    @staticmethod
    @transaction.atomic
    def change_room(tenant, allocation_id, new_room_id, new_check_in_date=None, new_check_out_date=None, user=None):
        allocation = ReservationInventory.objects.get(id=allocation_id, tenant=tenant)
        new_room = InventoryUnit.objects.get(id=new_room_id, tenant=tenant)

        if new_room.operational_status != 'operational':
            raise ValidationError(f"Room {new_room.name} is currently offline/under maintenance.")

        target_ci = new_check_in_date if new_check_in_date else allocation.check_in_date
        target_co = new_check_out_date if new_check_out_date else allocation.check_out_date

        check_room_availability(
            tenant=tenant,
            room=new_room,
            check_in_date=target_ci,
            check_out_date=target_co,
            exclude_allocation_id=allocation.id
        )

        old_room_name = allocation.inventory_unit.name if allocation.inventory_unit else "Unassigned"
        allocation.inventory_unit = new_room
        if new_check_in_date:
            allocation.check_in_date = new_check_in_date
        if new_check_out_date:
            allocation.check_out_date = new_check_out_date
        allocation.assigned_by = user
        allocation.assigned_at = timezone.now()
        allocation.save()

        # Update main reservation arrival/departure dates if this is the primary or single allocation
        reservation = allocation.reservation
        if new_check_in_date or new_check_out_date:
            all_allocs = reservation.room_allocations.all()
            earliest_ci = min([a.check_in_date for a in all_allocs])
            latest_co = max([a.check_out_date for a in all_allocs])
            reservation.arrival_date = earliest_ci
            reservation.departure_date = latest_co
            reservation.save(update_fields=['arrival_date', 'departure_date'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='ROOM_CHANGED',
            description=f"Room/Dates changed from {old_room_name} to {new_room.name} ({target_ci} -> {target_co}).",
            actor_user=user,
            payload_diff=make_serializable({
                'allocation_id': str(allocation.id),
                'old_room': old_room_name,
                'new_room': new_room.name,
                'new_room_id': str(new_room.id),
                'check_in_date': str(target_ci),
                'check_out_date': str(target_co)
            })
        )
        return allocation


class CheckInCheckOutEngine:
    @staticmethod
    @transaction.atomic
    def check_in(tenant, reservation_id, user=None):
        """
        Checks in all allocations and guest records linked to the reservation.
        """
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status not in ['CONFIRMED', 'PENDING']:
            raise ValidationError("Reservation must be in CONFIRMED or PENDING state to check in.")

        reservation.status = 'CHECKED_IN'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            if not alloc.inventory_unit:
                raise ValidationError("Cannot check in without assigning a physical room first.")
            alloc.status = 'CHECKED_IN'
            alloc.save(update_fields=['status'])

            # Log check-in time for each guest mapping
            for res_guest in alloc.guests.all():
                res_guest.is_checked_in = True
                res_guest.checked_in_at = timezone.now()
                res_guest.save(update_fields=['is_checked_in', 'checked_in_at'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='CHECKED_IN',
            description="Reservation successfully checked in.",
            actor_user=user
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def check_out(tenant, reservation_id, user=None):
        """
        Checks out the reservation and validates folio ledger balances.
        """
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status != 'CHECKED_IN':
            raise ValidationError("Reservation must be checked in to execute check-out.")

        # Compute actual outstanding balance dynamically to avoid stale stored values
        actual_balance = (reservation.total_amount + reservation.tax_amount - reservation.discount_amount) - reservation.paid_amount
        if actual_balance > Decimal('0.00'):
            raise ValidationError(f"Cannot checkout reservation with outstanding folio balance of {actual_balance}.")

        reservation.status = 'CHECKED_OUT'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'CHECKED_OUT'
            alloc.save(update_fields=['status'])

            # Log checkout time for each guest mapping
            for res_guest in alloc.guests.all():
                res_guest.checked_out_at = timezone.now()
                res_guest.save(update_fields=['checked_out_at'])

            # Clean housekeeping state on the room (automatically converts room to dirty)
            if alloc.inventory_unit:
                alloc.inventory_unit.housekeeping_status = 'dirty'
                alloc.inventory_unit.save(update_fields=['housekeeping_status'])

                # Auto-create a pending RUSH cleaning task in Housekeeping
                try:
                    from apps.features.housekeeping.models import CleaningTask
                    CleaningTask.objects.get_or_create(
                        tenant=tenant,
                        room=alloc.inventory_unit,
                        status='PENDING',
                        defaults={'priority': 'RUSH'}
                    )
                except Exception as e:
                    logger.warning(f"Could not auto-create cleaning task for room {alloc.inventory_unit.name}: {e}")

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='CHECKED_OUT',
            description="Reservation successfully checked out.",
            actor_user=user
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def undo_check_in(tenant, reservation_id, user=None):
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status != 'CHECKED_IN':
            raise ValidationError("Reservation must be checked in to undo check-in.")

        reservation.status = 'CONFIRMED'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'RESERVED'
            alloc.save(update_fields=['status'])

            for res_guest in alloc.guests.all():
                res_guest.is_checked_in = False
                res_guest.checked_in_at = None
                res_guest.save(update_fields=['is_checked_in', 'checked_in_at'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='REVERTED_CHECK_IN',
            description="Reservation check-in undone.",
            actor_user=user
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def undo_check_out(tenant, reservation_id, user=None):
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status != 'CHECKED_OUT':
            raise ValidationError("Reservation must be checked out to undo check-out.")

        reservation.status = 'CHECKED_IN'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'CHECKED_IN'
            alloc.save(update_fields=['status'])

            for res_guest in alloc.guests.all():
                res_guest.checked_out_at = None
                res_guest.save(update_fields=['checked_out_at'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='REVERTED_CHECK_OUT',
            description="Reservation check-out undone.",
            actor_user=user
        )
        return reservation


class ReservationModificationEngine:
    @staticmethod
    @transaction.atomic
    def modify_remarks(tenant, reservation_id, remarks, special_requests=None, user=None):
        """
        Modifies reservation notes, remarks, and special requests.
        """
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        old_data = {
            'remarks': reservation.remarks,
            'special_requests': reservation.special_requests
        }
        reservation.remarks = remarks
        if special_requests is not None:
            reservation.special_requests = special_requests
        reservation.save(update_fields=['remarks', 'special_requests'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='MODIFIED',
            description="Remarks and special requests modified.",
            actor_user=user,
            payload_diff=make_serializable({
                'before': old_data,
                'after': {
                    'remarks': reservation.remarks,
                    'special_requests': reservation.special_requests
                }
            })
        )
        return reservation


class ReservationCancellationEngine:
    @staticmethod
    @transaction.atomic
    def cancel_reservation(tenant, reservation_id, cancellation_reason=None, user=None):
        """
        Cancels the reservation, cancels all allocations, releases group pickup rooms.
        """
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status in ['CHECKED_IN', 'CHECKED_OUT', 'CANCELLED']:
            raise ValidationError("Cannot cancel a check-in, check-out, or already cancelled booking.")

        reservation.status = 'CANCELLED'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'CANCELLED'
            alloc.save(update_fields=['status'])

        # Adjust Group Block pickup counts if applicable
        if reservation.group_block:
            reservation.group_block.pickup_rooms = max(0, reservation.group_block.pickup_rooms - reservation.room_allocations.count())
            reservation.group_block.save(update_fields=['pickup_rooms'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='CANCELLED',
            description=f"Reservation cancelled. Reason: {cancellation_reason or 'Not Specified'}",
            actor_user=user,
            payload_diff=make_serializable({'reason': cancellation_reason})
        )
        return reservation


class ReservationSearchEngine:
    @staticmethod
    def search_reservations(tenant, search_query=None, status_filter=None, arrival_from=None, departure_to=None,
                            confirmation=None, phone=None, guest=None, room=None, property_id=None):
        """
        Filters and searches reservations by status, date ranges, confirmation numbers, or guest names.
        """
        qs = Reservation.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if arrival_from:
            qs = qs.filter(arrival_date__gte=arrival_from)
        if departure_to:
            qs = qs.filter(departure_date__lte=departure_to)
        
        # Specific search fields
        if confirmation:
            qs = qs.filter(confirmation_number__iexact=confirmation)
        if phone:
            qs = qs.filter(primary_guest__phone__icontains=phone)
        if guest:
            qs = qs.filter(
                models.Q(primary_guest__first_name__icontains=guest) |
                models.Q(primary_guest__last_name__icontains=guest)
            )
        if room:
            # Filter by room name or room id in allocations
            qs = qs.filter(room_allocations__inventory_unit__name__iexact=room)

        if search_query:
            qs = qs.filter(
                models.Q(confirmation_number__icontains=search_query) |
                models.Q(primary_guest__first_name__icontains=search_query) |
                models.Q(primary_guest__last_name__icontains=search_query) |
                models.Q(booking_reference__icontains=search_query)
            )
        return qs.distinct().order_by('-created_at')


class ReservationEnhancementEngine:
    @staticmethod
    @transaction.atomic
    def reinstate_reservation(tenant, reservation_id, user=None):
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status != 'CANCELLED':
            raise ValidationError("Only cancelled reservations can be reinstated.")
        
        reservation.status = 'CONFIRMED'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'RESERVED'
            alloc.save(update_fields=['status'])

        if reservation.group_block:
            reservation.group_block.pickup_rooms = min(
                reservation.group_block.total_rooms,
                reservation.group_block.pickup_rooms + reservation.room_allocations.count()
            )
            reservation.group_block.save(update_fields=['pickup_rooms'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='REINSTATED',
            description="Reservation successfully reinstated from cancelled status.",
            actor_user=user
        )
        return reservation

    @staticmethod
    @transaction.atomic
    def split_reservation(tenant, reservation_id, allocation_ids, user=None):
        parent = Reservation.objects.get(id=reservation_id, tenant=tenant)
        all_allocs = parent.room_allocations.all()
        if all_allocs.count() <= 1:
            raise ValidationError("Only multi-room reservations can be split.")

        # Create child reservation header
        child_conf = BookingEngine.generate_confirmation_number()
        
        # Clone parent reservation
        child = Reservation.objects.create(
            tenant=tenant,
            property=parent.property,
            primary_guest=parent.primary_guest,
            reservation_source=parent.reservation_source,
            group_block=parent.group_block,
            corporate_account=parent.corporate_account,
            status=parent.status,
            booking_date=timezone.now().date(),
            arrival_date=parent.arrival_date,
            departure_date=parent.departure_date,
            total_amount=Decimal('0.00'),
            tax_amount=Decimal('0.00'),
            discount_amount=Decimal('0.00'),
            paid_amount=Decimal('0.00'),
            balance_amount=Decimal('0.00'),
            booking_reference=parent.booking_reference,
            notes=parent.notes,
            confirmation_number=child_conf,
            reservation_type=parent.reservation_type,
            market_segment=parent.market_segment,
            origin_country=parent.origin_country,
            remarks=parent.remarks,
            special_requests=parent.special_requests
        )

        total_split_amount = Decimal('0.00')

        # Transfer selected allocations
        for alloc_id in allocation_ids:
            alloc = all_allocs.get(id=alloc_id)
            alloc.reservation = child
            alloc.save(update_fields=['reservation'])

            # Recalculate amount from snapshots
            from django.db.models import Sum
            snapshots_total = alloc.rate_snapshots.aggregate(total=Sum('amount_charged'))['total'] or Decimal('0.00')
            total_split_amount += snapshots_total

        # Update parent and child total amounts
        parent.total_amount = max(Decimal('0.00'), parent.total_amount - total_split_amount)
        parent.balance_amount = max(Decimal('0.00'), parent.balance_amount - total_split_amount)
        parent.save(update_fields=['total_amount', 'balance_amount'])

        child.total_amount = total_split_amount
        child.balance_amount = total_split_amount
        child.save(update_fields=['total_amount', 'balance_amount'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=parent,
            event_type='SPLIT_PARENT',
            description=f"Reservation split. Child reservation confirmation: {child.confirmation_number}",
            actor_user=user
        )

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=child,
            event_type='SPLIT_CHILD',
            description=f"Reservation created via split from parent: {parent.confirmation_number}",
            actor_user=user
        )

        return parent, child

    @staticmethod
    @transaction.atomic
    def merge_reservations(tenant, primary_reservation_id, secondary_reservation_id, user=None):
        primary = Reservation.objects.get(id=primary_reservation_id, tenant=tenant)
        secondary = Reservation.objects.get(id=secondary_reservation_id, tenant=tenant)

        if primary.property != secondary.property:
            raise ValidationError("Reservations must belong to the same property to merge.")
        if primary.primary_guest != secondary.primary_guest:
            raise ValidationError("Reservations must belong to the same guest to merge.")

        secondary_allocs = list(secondary.room_allocations.all())
        secondary_total_amount = secondary.total_amount

        for alloc in secondary_allocs:
            alloc.reservation = primary
            alloc.save(update_fields=['reservation'])

        # Mark secondary as CANCELLED
        secondary.status = 'CANCELLED'
        secondary.save(update_fields=['status'])

        # Update primary amounts
        primary.total_amount += secondary_total_amount
        primary.balance_amount += secondary_total_amount
        primary.save(update_fields=['total_amount', 'balance_amount'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=primary,
            event_type='MERGED',
            description=f"Merged with reservation confirmation: {secondary.confirmation_number}",
            actor_user=user
        )

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=secondary,
            event_type='CANCELLED',
            description=f"Reservation cancelled due to merge into: {primary.confirmation_number}",
            actor_user=user
        )

        return primary


class PricingEngine:
    @staticmethod
    def estimate_price(tenant, data):
        """
        Estimates the total reservation price, daily breakdowns, taxes, and coupon discounts.
        data format: PriceEstimationSerializer validated_data
        """
        # Parse allocations and calculate base rates
        total_amount = Decimal('0.00')
        tax_amount = Decimal('0.00')
        discount_amount = Decimal('0.00')
        
        breakdown = []
        
        matched_tax_labels = []

        # Calculate rates for allocations
        for alloc in data.get('allocations', []):
            try:
                from apps.features.inventory.models import InventoryUnitType
                unit_type = InventoryUnitType.objects.get(id=alloc.get('inventory_unit_type_id'), tenant=tenant)
                unit_type_name = unit_type.name
            except Exception:
                unit_type_name = "Room"
                
            alloc_total = Decimal('0.00')
            night_count = len(alloc.get('nightly_rates', [])) or 1
            for rate_day in alloc.get('nightly_rates', []):
                amt = Decimal(str(rate_day.get('amount', 0)))
                alloc_total += amt
            
            per_night_tariff = alloc_total / Decimal(str(night_count))
            guest_cnt = alloc.get('adult_count', 2) + alloc.get('child_count', 0)
            alloc_tax, tax_lbl = calculate_item_tax(
                tenant=tenant,
                item_price=alloc_total,
                per_night_tariff=per_night_tariff,
                guests_count=guest_cnt
            )
            if tax_lbl and tax_lbl not in matched_tax_labels:
                matched_tax_labels.append(tax_lbl)

            breakdown.append({
                'label': f"Room Charges ({unit_type_name})",
                'amount': float(alloc_total)
            })
            total_amount += alloc_total
            tax_amount += alloc_tax
            
        # Add packages
        for pkg_id in data.get('packages', []):
            try:
                pkg = HospitalityPackage.objects.get(id=pkg_id, tenant=tenant)
                pkg_tax, _ = calculate_item_tax(tenant=tenant, item_price=pkg.price)
                breakdown.append({
                    'label': f"Package: {pkg.name}",
                    'amount': float(pkg.price)
                })
                total_amount += pkg.price
                tax_amount += pkg_tax
            except HospitalityPackage.DoesNotExist:
                pass
                
        # Add services
        for svc_id in data.get('services', []):
            try:
                svc = Service.objects.get(id=svc_id, tenant=tenant)
                svc_tax, _ = calculate_item_tax(tenant=tenant, item_price=svc.price)
                breakdown.append({
                    'label': f"Service: {svc.name}",
                    'amount': float(svc.price)
                })
                total_amount += svc.price
                tax_amount += svc_tax
            except Service.DoesNotExist:
                pass
                
        # Calculate discount from coupon
        coupon_code = data.get('coupon_code')
        if coupon_code:
            try:
                coupon = Coupon.objects.get(tenant=tenant, code=coupon_code.upper().strip(), is_active=True)
                if not coupon.max_uses or coupon.current_uses < coupon.max_uses:
                    if coupon.discount_type == 'FLAT':
                        discount_amount = coupon.discount_value
                    elif coupon.discount_type == 'PERCENTAGE':
                        discount_amount = total_amount * (coupon.discount_value / Decimal('100.0'))
                        
                    breakdown.append({
                        'label': f"Discount ({coupon.code})",
                        'amount': float(-discount_amount)
                    })
            except Coupon.DoesNotExist:
                pass
                
        total_price = (total_amount + tax_amount) - discount_amount
        
        # Include dynamic tax breakdown row with exact DB tax component name
        tax_row_label = ", ".join(matched_tax_labels) if matched_tax_labels else "GST Tax"
        breakdown.append({
            'label': tax_row_label,
            'amount': float(tax_amount)
        })
        
        return {
            'breakdown': breakdown,
            'base_amount': float(total_amount),
            'tax_amount': float(tax_amount),
            'coupon_discount': float(discount_amount),
            'total_price': float(total_price)
        }

