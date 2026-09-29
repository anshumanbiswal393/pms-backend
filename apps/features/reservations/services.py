import uuid
import random
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict

logger = logging.getLogger(__name__)
from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationRateSnapshot, ReservationGuest, ReservationEvent,
    ReservationServiceAddon, ReservationPackage, ReservationCoupon,
    ReservationExtraCharge
)
from apps.features.crm.models import GuestProfile, GuestContact, GuestDocument
from apps.features.crm.services import EncryptionHelper
from apps.features.inventory.models import InventoryUnit, InventoryUnitType
from apps.features.rates.models import RatePlan, RatePlanVersion, Service, HospitalityPackage, Coupon, MealPlan, TenantMealPlanPrice

from apps.core.common.redis_lock import redis_distributed_lock
from apps.features.reservations.email_service import send_reservation_confirmation_email_async
from apps.core.common.notification_service import NotificationService

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

        # Also check active group blocks
        from apps.features.reservations.models import GroupBlock
        active_blocks = GroupBlock.objects.filter(
            tenant=tenant,
            status='OPEN',
            start_date__lt=check_out_date,
            end_date__gt=check_in_date
        )
        for b in active_blocks:
            room_sels = getattr(b, 'room_selections', None)
            if isinstance(room_sels, list):
                for rs in room_sels:
                    assigned = rs.get('assignedRooms') if isinstance(rs, dict) else []
                    if assigned and room.name in assigned:
                        raise ValidationError(f"Room {room.name} is currently blocked in Group '{b.name}' for these dates.")
            pickup_loc = getattr(b, 'pickup_location', None)
            if pickup_loc and room.name in [r.strip() for r in pickup_loc.split(',') if r.strip()]:
                raise ValidationError(f"Room {room.name} is currently blocked in Group '{b.name}' for these dates.")

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
        while True:
            candidate = str(random.randint(100000, 999999))
            if not Reservation.objects.filter(confirmation_number=candidate).exists():
                return candidate

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
        # Resolve Primary Guest (either lookup by UUID, lookup by contact/email/phone, or create inline)
        primary_guest = None
        if booking_data.get('primary_guest_id'):
            try:
                primary_guest = GuestProfile.objects.get(id=booking_data['primary_guest_id'], tenant=tenant)
            except GuestProfile.DoesNotExist:
                primary_guest = None

        phone = (booking_data.get('phone') or booking_data.get('event_organizer_contact') or '').strip()
        email = (booking_data.get('email') or booking_data.get('event_organizer_email') or '').strip()
        address = (booking_data.get('address') or booking_data.get('event_organizer_billing_address') or '').strip()
        id_type = booking_data.get('idType') or "PASSPORT"
        id_number = (booking_data.get('idNumber') or '').strip()
        id_proof_url = booking_data.get('id_proof_url') or booking_data.get('idProofUrl') or ""

        if not primary_guest and (email or phone):
            contact = None
            if email and phone and phone not in ['+91-', '+91', '0000000000']:
                contact = GuestContact.objects.filter(tenant=tenant, email=email, phone=phone).first()
            if not contact and phone and phone not in ['+91-', '+91', '0000000000']:
                contact = GuestContact.objects.filter(tenant=tenant, phone=phone).first()
            if not contact and email and email != 'guest@example.com':
                contact = GuestContact.objects.filter(tenant=tenant, email=email).first()
            if contact:
                primary_guest = contact.guest

        if primary_guest:
            if phone or email or address:
                contact = primary_guest.contacts.filter(is_primary=True).first() or primary_guest.contacts.first()
                if contact:
                    if phone and phone not in ['+91-', '+91', '0000000000'] and contact.phone != phone:
                        if not GuestContact.objects.filter(tenant=tenant, email=contact.email, phone=phone).exclude(id=contact.id).exists():
                            contact.phone = phone
                    if email and email != 'guest@example.com' and contact.email != email:
                        if not GuestContact.objects.filter(tenant=tenant, email=email, phone=contact.phone).exclude(id=contact.id).exists():
                            contact.email = email
                    if address and address != 'Address':
                        contact.address_line_1 = address
                    try:
                        contact.save()
                    except Exception:
                        pass
                elif phone or email:
                    clean_email = email or f"guest_{primary_guest.id.hex[:8]}@example.com"
                    clean_phone = phone or '0000000000'
                    if not GuestContact.objects.filter(tenant=tenant, email=clean_email, phone=clean_phone).exists():
                        try:
                            GuestContact.objects.create(
                                tenant=tenant,
                                guest=primary_guest,
                                email=clean_email,
                                phone=clean_phone,
                                address_line_1=address or '',
                                is_primary=True
                            )
                        except Exception:
                            pass
            if id_number or id_proof_url:
                doc = primary_guest.documents.first()
                if not doc:
                    doc_type = 'PASSPORT'
                    id_type_upper = id_type.upper()
                    if any(kw in id_type_upper for kw in ['ID', 'CARD', 'AADHAAR', 'NATIONAL', 'VOTER', 'PAN']):
                        doc_type = 'NATIONAL_ID'
                    elif any(kw in id_type_upper for kw in ['LICENSE', 'LICENCE', 'DRIVING']):
                        doc_type = 'DRIVING_LICENCE'
                    encrypted_doc_num = EncryptionHelper.encrypt(id_number) if id_number else ""
                    try:
                        GuestDocument.objects.create(
                            tenant=tenant,
                            guest=primary_guest,
                            document_type=doc_type,
                            document_number=encrypted_doc_num,
                            attachment_url=id_proof_url,
                            is_verified=False
                        )
                    except Exception:
                        pass
        else:
            full_name = booking_data.get('fullName') or booking_data.get('event_organizer_name') or "Inline Guest"
            nationality = booking_data.get('nationality') or ""

            parts = full_name.strip().split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else "Guest"

            primary_guest = GuestProfile.objects.create(
                tenant=tenant,
                first_name=first_name,
                last_name=last_name,
                nationality=nationality,
                guest_type='DOMESTIC'
            )
            clean_email = email or f"guest_{primary_guest.id.hex[:8]}@example.com"
            clean_phone = phone or '0000000000'
            if GuestContact.objects.filter(tenant=tenant, email=clean_email, phone=clean_phone).exists():
                clean_email = f"guest_{primary_guest.id.hex[:8]}@example.com"
            try:
                GuestContact.objects.create(
                    tenant=tenant,
                    guest=primary_guest,
                    email=clean_email,
                    phone=clean_phone,
                    address_line_1=address,
                    is_primary=True
                )
            except Exception as ex:
                logger.warning(f"Could not create contact for guest {primary_guest.id}: {ex}")

            if id_number or id_proof_url:
                doc_type = 'PASSPORT'
                id_type_upper = id_type.upper()
                if any(kw in id_type_upper for kw in ['ID', 'CARD', 'AADHAAR', 'NATIONAL', 'VOTER', 'PAN']):
                    doc_type = 'NATIONAL_ID'
                elif any(kw in id_type_upper for kw in ['LICENSE', 'LICENCE', 'DRIVING']):
                    doc_type = 'DRIVING_LICENCE'

                encrypted_doc_num = EncryptionHelper.encrypt(id_number) if id_number else ""
                try:
                    GuestDocument.objects.create(
                        tenant=tenant,
                        guest=primary_guest,
                        document_type=doc_type,
                        document_number=encrypted_doc_num,
                        attachment_url=id_proof_url,
                        is_verified=False
                    )
                except Exception:
                    pass
        
        # Resolve Reservation Source
        res_source_id = booking_data.get('reservation_source_id')
        from apps.core.reference.models import ReservationSource
        from apps.core.common.models import BookingSource
        source_name = booking_data.get('source') or booking_data.get('reservation_source_name')

        source_obj = None
        if res_source_id:
            source_obj = ReservationSource.objects.filter(id=res_source_id).first()
            if not source_obj:
                bs = BookingSource.objects.filter(id=res_source_id).first()
                if bs:
                    code = bs.name.lower().replace(" ", "_").replace("-", "_")[:64]
                    source_obj, _ = ReservationSource.objects.get_or_create(
                        code=code,
                        defaults={'name': bs.name, 'is_active': bs.is_active}
                    )
        
        if not source_obj and source_name:
            bs = BookingSource.objects.filter(name__iexact=source_name).first()
            if bs:
                code = bs.name.lower().replace(" ", "_").replace("-", "_")[:64]
                source_obj, _ = ReservationSource.objects.get_or_create(
                    code=code,
                    defaults={'name': bs.name, 'is_active': bs.is_active}
                )
            else:
                source_obj = (
                    ReservationSource.objects.filter(name__iexact=source_name).first()
                    or ReservationSource.objects.filter(code__iexact=source_name.lower().replace(" ", "_")).first()
                    or ReservationSource.objects.filter(name__icontains=source_name).first()
                )
                if not source_obj:
                    code = source_name.lower().replace(" ", "_").replace("-", "_")[:64]
                    source_obj, _ = ReservationSource.objects.get_or_create(
                        code=code,
                        defaults={'name': source_name, 'is_active': True}
                    )

        if not source_obj:
            source_obj = (
                ReservationSource.objects.filter(code='direct').first()
                or ReservationSource.objects.filter(name__icontains='direct').first()
                or ReservationSource.objects.first()
            )

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
            primary_contact = primary_guest.contacts.filter(is_primary=True).first() or primary_guest.contacts.first()
            primary_doc = primary_guest.documents.first()
            doc_number_plain = ""
            if primary_doc and primary_doc.document_number:
                try:
                    doc_number_plain = EncryptionHelper.decrypt(primary_doc.document_number)
                except Exception:
                    doc_number_plain = str(primary_doc.document_number)

            ReservationGuest.objects.create(
                tenant=tenant,
                reservation_inventory=allocation,
                guest=primary_guest,
                is_primary=True,
                guest_snapshot={
                    'name': f"{primary_guest.first_name or ''} {primary_guest.last_name or ''}".strip(),
                    'first_name': primary_guest.first_name,
                    'last_name': primary_guest.last_name,
                    'type': 'Primary',
                    'email': primary_contact.email if primary_contact else None,
                    'phone': primary_contact.phone if primary_contact else None,
                    'address': f"{primary_contact.address_line_1 or ''} {primary_contact.city or ''} {primary_contact.state or ''}".strip() if primary_contact else None,
                    'id_type': primary_doc.document_type if primary_doc else None,
                    'id_number': doc_number_plain or None,
                    'id_proof_url': primary_doc.attachment_url if primary_doc else None,
                }
            )

            # Persist additional / accompanying guests for this allocation
            add_guests = booking_data.get('additional_guests') or booking_data.get('additionalGuests') or []
            for g_item in add_guests:
                if not isinstance(g_item, dict):
                    continue
                g_name = (g_item.get('name') or g_item.get('fullName') or '').strip()
                if not g_name:
                    continue
                g_type = g_item.get('type') or g_item.get('guest_type') or 'Adult'
                g_age = str(g_item.get('age') or '')
                g_gender = g_item.get('gender') or ''
                g_id_type = g_item.get('idType') or g_item.get('id_type') or 'NATIONAL_ID'
                g_id_number = (g_item.get('idNumber') or g_item.get('id_number') or '').strip()
                g_id_url = g_item.get('idProofUrl') or g_item.get('id_proof_url') or ''
                g_phone = (g_item.get('phone') or '').strip()
                g_email = (g_item.get('email') or '').strip()

                parts = g_name.split(' ', 1)
                g_first = parts[0]
                g_last = parts[1] if len(parts) > 1 else 'Guest'

                sec_guest = None
                try:
                    sec_guest = GuestProfile.objects.create(
                        tenant=tenant,
                        first_name=g_first,
                        last_name=g_last,
                        guest_type='DOMESTIC'
                    )
                    if g_phone or g_email:
                        sec_email = g_email or f"sec_{sec_guest.id.hex[:8]}@example.com"
                        sec_phone = g_phone or '0000000000'
                        if not GuestContact.objects.filter(tenant=tenant, email=sec_email, phone=sec_phone).exists():
                            try:
                                GuestContact.objects.create(
                                    tenant=tenant,
                                    guest=sec_guest,
                                    phone=sec_phone,
                                    email=sec_email,
                                    is_primary=True
                                )
                            except Exception:
                                pass
                    if g_id_number:
                        enc_doc = EncryptionHelper.encrypt(g_id_number)
                        doc_t = 'PASSPORT' if 'PASSPORT' in g_id_type.upper() else 'DRIVING_LICENCE' if any(k in g_id_type.upper() for k in ['DRIV', 'LICEN']) else 'NATIONAL_ID'
                        GuestDocument.objects.create(
                            tenant=tenant,
                            guest=sec_guest,
                            document_type=doc_t,
                            document_number=enc_doc,
                            attachment_url=g_id_url,
                            is_verified=False
                        )
                except Exception as ex:
                    logger.warning(f"Failed to create secondary guest profile: {ex}")

                ReservationGuest.objects.create(
                    tenant=tenant,
                    reservation_inventory=allocation,
                    guest=sec_guest,
                    is_primary=False,
                    guest_snapshot={
                        'name': g_name,
                        'first_name': g_first,
                        'last_name': g_last,
                        'type': g_type,
                        'age': g_age,
                        'gender': g_gender,
                        'phone': g_phone,
                        'email': g_email,
                        'id_type': g_id_type,
                        'id_number': g_id_number,
                        'id_proof_url': g_id_url,
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

            # Handle per-allocation Extra Charge (e.g. Extra Person or custom room extra charge)
            extra_charge_val = Decimal(str(alloc_item.get('extra_charge') or alloc_item.get('extraCharge') or 0))
            if extra_charge_val > Decimal('0.00'):
                desc = f"Extra Person / Room Charge ({unit_type.name})"
                extra_tax, _ = calculate_item_tax(tenant=tenant, item_price=extra_charge_val)
                ReservationExtraCharge.objects.create(
                    tenant=tenant,
                    reservation=reservation,
                    description=desc,
                    amount=extra_charge_val,
                    tax_amount=extra_tax,
                    tax_type='Excluded',
                    tax_percent=Decimal('0.00'),
                    date=alloc_item['check_in_date']
                )
                total_amount += extra_charge_val
                tax_amount += extra_tax

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

        # Add booking-level extra charges
        extra_charges_list = booking_data.get('extra_charges') or booking_data.get('extraCharges') or []
        for ec in extra_charges_list:
            if isinstance(ec, dict):
                ec_amt = Decimal(str(ec.get('amount') or 0))
                if ec_amt > Decimal('0.00'):
                    ec_desc = ec.get('description') or 'Extra Charge'
                    # Prevent duplicate creation if room extra charges were already recorded per allocation
                    if ec_desc.startswith("Extra Guest Charge (") and any((a.get('extra_charge') or a.get('extraCharge')) for a in booking_data.get('allocations', [])):
                        continue
                    ec_tax_type = ec.get('taxType') or ec.get('tax_type') or 'Excluded'
                    ec_tax_percent = Decimal(str(ec.get('taxPercent') or ec.get('tax_percent') or 0))
                    ec_date = ec.get('date') or reservation.arrival_date
                    
                    if ec_tax_type == 'Excluded':
                        if ec_tax_percent > 0:
                            ec_tax = ec_amt * (ec_tax_percent / Decimal('100.0'))
                        else:
                            ec_tax, _ = calculate_item_tax(tenant=tenant, item_price=ec_amt)
                        ec_base = ec_amt
                    else:
                        ec_tax = ec_amt - (ec_amt / (Decimal('1.0') + ec_tax_percent / Decimal('100.0'))) if ec_tax_percent > 0 else Decimal('0.00')
                        ec_base = ec_amt - ec_tax

                    ReservationExtraCharge.objects.create(
                        tenant=tenant,
                        reservation=reservation,
                        description=ec_desc,
                        amount=ec_base,
                        tax_amount=ec_tax,
                        tax_type=ec_tax_type,
                        tax_percent=ec_tax_percent,
                        date=ec_date
                    )
                    total_amount += ec_base
                    tax_amount += ec_tax

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

        # 1. Asynchronously send Confirmation Email with PDF Invoice attachment to guest
        send_reservation_confirmation_email_async(reservation.id)

        # 2. Trigger Real-time System Notification for New Reservation / OTA
        try:
            source_name = reservation.reservation_source.name if reservation.reservation_source else "Direct"
            is_ota = any(ota_kw in source_name.upper() for ota_kw in ['OTA', 'BOOKING.COM', 'EXPEDIA', 'AGODA', 'AIRBNB', 'MMT', 'GOIBIBO'])
            category = 'OTA' if is_ota else 'RESERVATION'
            title = f"New OTA Booking: {source_name} ({conf_no})" if is_ota else f"New Reservation: {conf_no}"
            
            guest_name_str = f"{primary_guest.first_name} {primary_guest.last_name}".strip() if primary_guest else "Guest"
            arr_date_str = reservation.arrival_date.strftime('%d %b') if reservation.arrival_date else ''
            dep_date_str = reservation.departure_date.strftime('%d %b') if reservation.departure_date else ''
            
            NotificationService.send_notification(
                tenant=tenant,
                property_obj=property_obj,
                category=category,
                title=title,
                message=f"{guest_name_str} booked for {arr_date_str} - {dep_date_str}. Total: ₹{net_payable:,.2f}",
                level="success",
                link_url=f"/reservations/{reservation.id}",
                metadata={"reservation_id": str(reservation.id), "confirmation_number": conf_no, "source": source_name},
                actor_user=user
            )
        except Exception as e:
            pass

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
        if room.inventory_unit_type:
            allocation.inventory_unit_type = room.inventory_unit_type
            allocation.inventory_snapshot = {
                'id': str(room.inventory_unit_type.id),
                'code': room.inventory_unit_type.code,
                'name': room.inventory_unit_type.name,
                'base_occupancy': room.inventory_unit_type.base_occupancy,
                'max_occupancy': room.inventory_unit_type.max_occupancy,
            }
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
        if new_room.inventory_unit_type:
            allocation.inventory_unit_type = new_room.inventory_unit_type
            allocation.inventory_snapshot = {
                'id': str(new_room.inventory_unit_type.id),
                'code': new_room.inventory_unit_type.code,
                'name': new_room.inventory_unit_type.name,
                'base_occupancy': new_room.inventory_unit_type.base_occupancy,
                'max_occupancy': new_room.inventory_unit_type.max_occupancy,
            }
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

        # Check-in date validation: guest cannot check in before scheduled arrival date
        current_date = timezone.localdate()
        prop_bdate = reservation.property.business_date if (reservation.property and reservation.property.business_date) else None
        effective_date = max(current_date, prop_bdate) if prop_bdate else current_date
        if reservation.arrival_date and reservation.arrival_date > effective_date:
            raise ValidationError(
                f"Guest cannot check in before the scheduled arrival date ({reservation.arrival_date.strftime('%d-%b-%Y')})."
            )

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

        # Trigger System Notification for Check-in
        try:
            primary_guest_name = f"{reservation.primary_guest.first_name} {reservation.primary_guest.last_name}".strip() if reservation.primary_guest else "Guest"
            assigned_rooms = ", ".join([a.inventory_unit.name for a in reservation.room_allocations.all() if a.inventory_unit]) or "Room"
            NotificationService.send_notification(
                tenant=tenant,
                property_obj=reservation.property,
                category="CHECKIN",
                title=f"Guest Checked In: {primary_guest_name}",
                message=f"Reservation {reservation.confirmation_number} checked into Room {assigned_rooms}.",
                level="success",
                link_url=f"/reservations/{reservation.id}",
                metadata={"reservation_id": str(reservation.id), "confirmation_number": reservation.confirmation_number},
                actor_user=user
            )
        except Exception as e:
            pass

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

        # Trigger System Notification for Check-out
        try:
            primary_guest_name = f"{reservation.primary_guest.first_name} {reservation.primary_guest.last_name}".strip() if reservation.primary_guest else "Guest"
            assigned_rooms = ", ".join([a.inventory_unit.name for a in reservation.room_allocations.all() if a.inventory_unit]) or "Room"
            NotificationService.send_notification(
                tenant=tenant,
                property_obj=reservation.property,
                category="CHECKOUT",
                title=f"Guest Checked Out: {primary_guest_name}",
                message=f"Reservation {reservation.confirmation_number} checked out from Room {assigned_rooms}. Room marked dirty for cleaning.",
                level="info",
                link_url=f"/reservations/{reservation.id}",
                metadata={"reservation_id": str(reservation.id), "confirmation_number": reservation.confirmation_number},
                actor_user=user
            )
        except Exception as e:
            pass

        return reservation

    @staticmethod
    @transaction.atomic
    def undo_check_in(tenant, reservation_id, user=None):
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status != 'CHECKED_IN':
            raise ValidationError("Reservation must be checked in to undo check-in.")

        # Same-day validation: only allow undo check-in on the same operational date (business date or local date)
        today_local = timezone.localdate()
        current_bdate = reservation.property.business_date if (reservation.property and reservation.property.business_date) else today_local
        checkin_event = reservation.timeline_events.filter(event_type='CHECKED_IN').order_by('-created_at').first()
        checkin_date = checkin_event.created_at.date() if checkin_event else (reservation.arrival_date or today_local)

        if checkin_date < today_local and checkin_date < current_bdate:
            raise ValidationError(
                f"Cannot undo check-in. Check-in was completed on {checkin_date}, which is prior to current date. Undo check-in is only permitted on the same operational date."
            )

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

        # Same-day validation: only allow undo check-out on the same operational date (business date or local date)
        today_local = timezone.localdate()
        current_bdate = reservation.property.business_date if (reservation.property and reservation.property.business_date) else today_local
        checkout_event = reservation.timeline_events.filter(event_type='CHECKED_OUT').order_by('-created_at').first()
        checkout_date = checkout_event.created_at.date() if checkout_event else (reservation.departure_date or today_local)

        if checkout_date < today_local and checkout_date < current_bdate:
            raise ValidationError(
                f"Cannot undo check-out. Check-out was completed on {checkout_date}, which is prior to current date. Undo check-out is only permitted on the same operational date."
            )

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

    @staticmethod
    @transaction.atomic
    def mark_no_show(tenant, reservation_id, user=None, reason=None):
        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        if reservation.status not in ['CONFIRMED', 'PENDING']:
            raise ValidationError("Only Confirmed or Pending reservations can be marked as No-Show.")

        reservation.status = 'NO_SHOW'
        reservation.save(update_fields=['status'])

        for alloc in reservation.room_allocations.all():
            alloc.status = 'CANCELLED'
            alloc.save(update_fields=['status'])

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='NO_SHOW',
            description=f"Reservation marked as No-Show by {user.username if user and hasattr(user, 'username') else 'system'}.",
            actor_user=user,
            payload_diff=make_serializable({
                'reason': reason or 'Guest did not arrive by check-in time'
            })
        )
        return reservation

    @classmethod
    def auto_mark_expired_no_shows(cls, tenant, property_id=None):
        """
        Automatically transitions reservations whose stay has ended (departure_date < current_date)
        and were never checked in (status IN ['CONFIRMED', 'PENDING']) to 'NO_SHOW'.
        Cached to run at most once every 5 minutes per tenant.
        """
        from django.core.cache import cache
        cache_key = f"auto_no_show_check_{tenant.id}_{property_id or 'all'}"
        if cache.get(cache_key):
            return 0

        current_date = timezone.localdate()
        qs = Reservation.objects.filter(
            tenant=tenant,
            status__in=['CONFIRMED', 'PENDING'],
            departure_date__lt=current_date
        )
        if property_id:
            qs = qs.filter(property_id=property_id)

        # Bulk update in database without looping
        updated_count = qs.update(status='NO_SHOW')
        cache.set(cache_key, True, 300)  # 5 minutes
        return updated_count


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

    @staticmethod
    @transaction.atomic
    def amend_stay(tenant, reservation_id, new_departure_date, new_arrival_date=None, user=None):
        """
        Amends/extends reservation stay dates.
        Recalculates nightly rates, extra guest charges, and per-night taxes (GST).
        Generates or removes ReservationRateSnapshot records for newly added or removed dates.
        Updates reservation.departure_date, room_allocations check_out_date, total_amount, tax_amount, balance_amount.
        Updates or creates GuestFolio and posts FolioTransaction records for the amended nights.
        """
        from datetime import datetime, timedelta
        from decimal import Decimal
        from apps.features.reservations.models import Reservation, ReservationRateSnapshot, ReservationExtraCharge, ReservationEvent
        from apps.features.front_office.models import GuestFolio, FolioTransaction

        reservation = Reservation.objects.get(id=reservation_id, tenant=tenant)
        old_dep = reservation.departure_date
        old_arr = reservation.arrival_date

        if isinstance(new_departure_date, str):
            new_dep = datetime.strptime(new_departure_date.split('T')[0], '%Y-%m-%d').date()
        else:
            new_dep = new_departure_date

        if new_arrival_date:
            if isinstance(new_arrival_date, str):
                new_arr = datetime.strptime(new_arrival_date.split('T')[0], '%Y-%m-%d').date()
            else:
                new_arr = new_arrival_date
        else:
            new_arr = old_arr

        if new_dep <= new_arr:
            raise ValidationError("New departure date must be strictly after the arrival date.")

        allocations = list(reservation.room_allocations.all())

        # Check room availability if extending stay and room is assigned
        for alloc in allocations:
            if alloc.inventory_unit and new_dep > alloc.check_out_date:
                check_room_availability(
                    tenant=tenant,
                    room=alloc.inventory_unit,
                    check_in_date=alloc.check_out_date,
                    check_out_date=new_dep,
                    exclude_allocation_id=alloc.id
                )

        # Update allocations check-in & check-out dates
        for alloc in allocations:
            alloc.check_in_date = new_arr
            alloc.check_out_date = new_dep
            alloc.save(update_fields=['check_in_date', 'check_out_date'])

        # Find or create GuestFolio for this reservation
        folio = GuestFolio.objects.filter(reservation=reservation, tenant=tenant).first()
        if not folio:
            try:
                conf_prefix = str(reservation.confirmation_number or reservation.id)[:8]
                folio_num = f"FOL-{conf_prefix}"
                folio = GuestFolio.objects.create(
                    tenant=tenant,
                    reservation=reservation,
                    folio_number=folio_num,
                    status='OPEN',
                    total_charges=Decimal('0.00'),
                    total_payments=Decimal(str(reservation.paid_amount or '0.00')),
                    balance=Decimal('0.00')
                )
            except Exception:
                folio = None

        newly_added_charges = []

        # Process each allocation's snapshots
        for alloc in allocations:
            unit_type = alloc.inventory_unit_type
            guest_cnt = (alloc.adult_count or 1) + (alloc.child_count or 0)
            existing_snaps = {s.date: s for s in alloc.rate_snapshots.all()}

            # If shortening stay: delete snapshots falling outside the new range
            for s_date, snap in list(existing_snaps.items()):
                if s_date < new_arr or s_date >= new_dep:
                    snap.delete()
                    del existing_snaps[s_date]

            # Also cleanup any ReservationExtraCharge records outside new date range
            ReservationExtraCharge.objects.filter(
                reservation=reservation,
                date__lt=new_arr
            ).delete()
            ReservationExtraCharge.objects.filter(
                reservation=reservation,
                date__gte=new_dep
            ).delete()

            # Resolve template rate plan and nightly base rate from existing snapshots
            ref_snap = alloc.rate_snapshots.first()
            if ref_snap:
                rate_plan = ref_snap.rate_plan
                rate_version = ref_snap.rate_plan_version
                nightly_rate = ref_snap.amount_charged
                policy_snapshot = ref_snap.policy_snapshot
                rate_snapshot_tmpl = dict(ref_snap.rate_snapshot or {})
            else:
                from apps.features.rates.models import RatePlan, RatePlanInventory
                rate_plan = RatePlan.objects.filter(tenant=tenant).first()
                rate_version = rate_plan.versions.first() if rate_plan else None
                # lookup base rate from inventory
                rpi = RatePlanInventory.objects.filter(tenant=tenant, inventory_unit_type=unit_type).first()
                nightly_rate = Decimal(str(rpi.base_rate if rpi and rpi.base_rate else (unit_type.base_price or '2000.00')))
                policy_snapshot = {}
                rate_snapshot_tmpl = {
                    'rate_plan_code': rate_plan.code if rate_plan else 'BAR',
                    'rate_plan_name': rate_plan.name if rate_plan else 'Best Available Rate',
                    'amount': str(nightly_rate),
                }

            # Iterate every night of the stay
            curr_d = new_arr
            while curr_d < new_dep:
                if curr_d not in existing_snaps:
                    # Create missing snapshot for newly added date
                    snap_data = dict(rate_snapshot_tmpl)
                    snap_data['amount'] = str(nightly_rate)

                    new_snap = ReservationRateSnapshot.objects.create(
                        tenant=tenant,
                        reservation_inventory=alloc,
                        date=curr_d,
                        rate_plan=rate_plan,
                        rate_plan_version=rate_version,
                        amount_charged=nightly_rate,
                        rate_snapshot=snap_data,
                        policy_snapshot=policy_snapshot
                    )
                    existing_snaps[curr_d] = new_snap

                    # Compute nightly tax
                    night_tax, tax_lbl = calculate_item_tax(
                        tenant=tenant,
                        item_price=nightly_rate,
                        per_night_tariff=nightly_rate,
                        guests_count=guest_cnt
                    )

                    newly_added_charges.append({
                        'date': curr_d,
                        'desc': f"Room Charge ({unit_type.name})",
                        'amount': nightly_rate,
                        'tax': night_tax,
                        'tax_lbl': tax_lbl
                    })

                    # Post to GuestFolio if open
                    if folio:
                        try:
                            FolioTransaction.objects.create(
                                tenant=tenant,
                                folio=folio,
                                transaction_type='CHARGE',
                                charge_code='ROOM_RATE',
                                amount=nightly_rate,
                                description=f"Room Charge ({unit_type.name}) - {curr_d.strftime('%d %b %Y')}"
                            )
                            if night_tax > Decimal('0.00'):
                                FolioTransaction.objects.create(
                                    tenant=tenant,
                                    folio=folio,
                                    transaction_type='CHARGE',
                                    charge_code='TAX',
                                    amount=night_tax,
                                    description=f"{tax_lbl} - {curr_d.strftime('%d %b %Y')}"
                                )
                        except Exception:
                            pass

                curr_d += timedelta(days=1)

        # Recalculate total_amount and tax_amount for the entire reservation
        total_room_charges = Decimal('0.00')
        total_room_tax = Decimal('0.00')
        for alloc in allocations:
            guest_cnt = (alloc.adult_count or 1) + (alloc.child_count or 0)
            for snap in alloc.rate_snapshots.all():
                total_room_charges += snap.amount_charged
                t_amt, _ = calculate_item_tax(
                    tenant=tenant,
                    item_price=snap.amount_charged,
                    per_night_tariff=snap.amount_charged,
                    guests_count=guest_cnt
                )
                total_room_tax += t_amt

        # Sum Extra Charges
        extra_charges = ReservationExtraCharge.objects.filter(reservation=reservation)
        total_extra_charges = sum((ec.amount for ec in extra_charges), Decimal('0.00'))
        total_extra_tax = sum((ec.tax_amount for ec in extra_charges), Decimal('0.00'))

        # Sum Packages & Services
        total_pkg_charges = sum((p.price for p in reservation.packages.all()), Decimal('0.00'))
        total_pkg_tax = Decimal('0.00')
        for p in reservation.packages.all():
            p_tax, _ = calculate_item_tax(tenant=tenant, item_price=p.price)
            total_pkg_tax += p_tax

        total_svc_charges = sum((s.price for s in reservation.services.all()), Decimal('0.00'))
        total_svc_tax = Decimal('0.00')
        for s in reservation.services.all():
            s_tax, _ = calculate_item_tax(tenant=tenant, item_price=s.price)
            total_svc_tax += s_tax

        total_amount = total_room_charges + total_extra_charges + total_pkg_charges + total_svc_charges
        total_tax = total_room_tax + total_extra_tax + total_pkg_tax + total_svc_tax
        discount = reservation.discount_amount or Decimal('0.00')

        reservation.departure_date = new_dep
        reservation.arrival_date = new_arr
        reservation.total_amount = total_amount
        reservation.tax_amount = total_tax
        net_payable = (total_amount + total_tax) - discount
        paid_val = reservation.paid_amount or Decimal('0.00')
        reservation.balance_amount = max(Decimal('0.00'), net_payable - paid_val)
        reservation.save()

        # Update GuestFolio balance
        if folio:
            try:
                folio.total_charges = net_payable
                folio.total_payments = paid_val
                folio.balance = net_payable - paid_val
                folio.save()
            except Exception:
                pass

        # Create Timeline Event
        diff_str = f"Stay amended from {old_dep} to {new_dep}. Total charges updated to ₹{net_payable:.2f} (New Balance: ₹{reservation.balance_amount:.2f})."
        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='AMENDED',
            description=diff_str,
            actor_user=user,
            payload_diff=make_serializable({
                'previous_departure': str(old_dep),
                'new_departure': str(new_dep),
                'new_total_amount': str(total_amount),
                'new_tax_amount': str(total_tax),
                'new_net_payable': str(net_payable),
                'new_balance': str(reservation.balance_amount),
                'newly_added_charges': newly_added_charges
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
                unit_type = None
                unit_type_name = "Room"
                
            alloc_total = Decimal('0.00')
            night_count = len(alloc.get('nightly_rates', [])) or 1
            for rate_day in alloc.get('nightly_rates', []):
                amt = Decimal(str(rate_day.get('amount', 0)))
                alloc_total += amt

            # Extra Adult & Extra Child Calculation
            adult_count = int(alloc.get('adult_count', 2) or 2)
            child_count = int(alloc.get('child_count', 0) or 0)
            base_occ = getattr(unit_type, 'base_occupancy', 2) or 2
            extra_adults = max(0, adult_count - base_occ)
            extra_children = max(0, child_count)

            rate_plan_id = alloc.get('rate_plan_id')
            extra_adult_rate = Decimal('0.00')
            extra_child_rate = Decimal('0.00')

            if rate_plan_id and unit_type and hasattr(unit_type, 'id'):
                try:
                    from apps.features.rates.models import RatePlanInventoryType
                    rpi = RatePlanInventoryType.objects.filter(
                        rate_plan_id=rate_plan_id,
                        inventory_unit_type_id=unit_type.id,
                        tenant=tenant
                    ).first()
                    if rpi:
                        extra_adult_rate = rpi.extra_adult_rate or Decimal('0.00')
                        extra_child_rate = rpi.extra_child_rate or Decimal('0.00')
                except Exception:
                    pass

            if extra_adult_rate == Decimal('0.00') and unit_type:
                extra_adult_rate = Decimal(str(
                    getattr(unit_type, 'extra_adult_charge', None) or 
                    getattr(unit_type, 'extra_adult_price', None) or 
                    getattr(unit_type, 'extra_bed_price', None) or 
                    getattr(unit_type, 'extra_bed_charge', None) or 0
                ))
            if extra_child_rate == Decimal('0.00') and unit_type:
                extra_child_rate = Decimal(str(
                    getattr(unit_type, 'extra_child_charge', None) or 
                    getattr(unit_type, 'extra_child_price', None) or 0
                ))

            extra_adult_total = Decimal(str(extra_adults)) * extra_adult_rate * Decimal(str(night_count))
            extra_child_total = Decimal(str(extra_children)) * extra_child_rate * Decimal(str(night_count))
            custom_extra_input = Decimal(str(alloc.get('extra_charge', 0) or 0)) * Decimal(str(night_count))

            # If rate wasn't found in DB, but custom_extra_input was provided for extra adults
            if extra_adult_total == Decimal('0.00') and extra_adults > 0 and custom_extra_input > Decimal('0.00'):
                extra_adult_total = custom_extra_input
                custom_extra_input = Decimal('0.00')

            # Prevent double-counting: custom_extra_input from room card usually includes extra adult/child charges
            remaining_custom_extra = max(Decimal('0.00'), custom_extra_input - (extra_adult_total + extra_child_total))

            # Room discount handling
            alloc_disc_pct = Decimal(str(alloc.get('discount_percent', 0) or 0))
            alloc_disc_amt = Decimal('0.00')
            if alloc_disc_pct > Decimal('0.00'):
                alloc_disc_amt = (alloc_total * alloc_disc_pct) / Decimal('100.0')

            # Combined taxable base for this room allocation
            room_taxable_total = max(
                Decimal('0.00'),
                alloc_total - alloc_disc_amt + extra_adult_total + extra_child_total + remaining_custom_extra
            )
            per_night_tariff = room_taxable_total / Decimal(str(night_count))
            guest_cnt = alloc.get('adult_count', 2) + alloc.get('child_count', 0)

            # Check if allocation has custom tax percentage from room selection
            alloc_tax_pct = alloc.get('tax_percent')
            if alloc_tax_pct is not None and str(alloc_tax_pct).strip() != '' and str(alloc_tax_pct).strip().lower() != 'none':
                try:
                    pct = Decimal(str(alloc_tax_pct))
                    alloc_tax = (room_taxable_total * pct) / Decimal('100.0')
                    tax_lbl = f"GST {pct:.0f}%" if pct == pct.to_integral() else f"GST {pct}%"
                except Exception:
                    alloc_tax, tax_lbl = calculate_item_tax(
                        tenant=tenant,
                        item_price=room_taxable_total,
                        per_night_tariff=per_night_tariff,
                        guests_count=guest_cnt
                    )
            else:
                alloc_tax, tax_lbl = calculate_item_tax(
                    tenant=tenant,
                    item_price=room_taxable_total,
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

            if alloc_disc_amt > Decimal('0.00'):
                breakdown.append({
                    'label': "Room Discount",
                    'amount': float(-alloc_disc_amt)
                })
                total_amount -= alloc_disc_amt

            if extra_adult_total > 0:
                breakdown.append({
                    'label': f"Extra Adult charges ({extra_adults} Adult{'s' if extra_adults > 1 else ''})",
                    'amount': float(extra_adult_total)
                })
                total_amount += extra_adult_total

            if extra_child_total > 0:
                breakdown.append({
                    'label': f"Extra Child charges ({extra_children} Child{'ren' if extra_children > 1 else ''})",
                    'amount': float(extra_child_total)
                })
                total_amount += extra_child_total

            if remaining_custom_extra > 0:
                breakdown.append({
                    'label': "Extra Guest Charges",
                    'amount': float(remaining_custom_extra)
                })
                total_amount += remaining_custom_extra
            
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

        # Consolidate breakdown items by label
        consolidated_breakdown = []
        breakdown_map = {}
        for item in breakdown:
            lbl = item['label']
            amt = float(item['amount'])
            if lbl in breakdown_map:
                breakdown_map[lbl]['amount'] = round(breakdown_map[lbl]['amount'] + amt, 2)
            else:
                entry = {'label': lbl, 'amount': round(amt, 2)}
                breakdown_map[lbl] = entry
                consolidated_breakdown.append(entry)
        
        return {
            'breakdown': consolidated_breakdown,
            'base_amount': float(total_amount),
            'tax_amount': float(tax_amount),
            'coupon_discount': float(discount_amount),
            'total_price': float(total_price)
        }

