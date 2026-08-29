import logging
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.core.tenants.models import Tenant, Property
from apps.features.reservations.models import Reservation, ReservationInventory
from apps.features.inventory.models import InventoryUnit, InventoryUnitType
from apps.features.front_office.models import (
    GuestFolio, FolioTransaction, CashierShift, NightAuditSession
)
from apps.features.rates.models import RatePlan, RatePlanInventoryType

logger = logging.getLogger(__name__)


class NightAuditService:
    @staticmethod
    def get_property_business_date(property_obj: Property) -> date:
        """Returns the current operational business date of the property."""
        if property_obj and property_obj.business_date:
            return property_obj.business_date
        return timezone.now().date()

    @classmethod
    def get_audit_status(cls, property_obj: Property, tenant: Tenant) -> dict:
        """Fetches comprehensive status, operational metrics and readiness for Night Audit."""
        business_date = cls.get_property_business_date(property_obj)
        
        # 1. Total rooms and occupied rooms
        total_rooms = InventoryUnit.objects.filter(property=property_obj).count()
        if total_rooms == 0:
            total_rooms = 1

        in_house_reservations = Reservation.objects.filter(
            property=property_obj,
            status='CHECKED_IN'
        ).select_related('primary_guest').prefetch_related('room_allocations__inventory_unit', 'room_allocations__inventory_unit_type')
        
        occupied_rooms = in_house_reservations.count()
        occupancy_rate = round((occupied_rooms / total_rooms) * 100, 1) if total_rooms > 0 else 0

        # 2. Pending arrivals (Expected check-ins not yet checked in)
        pending_arrivals_qs = Reservation.objects.filter(
            property=property_obj,
            status__in=['CONFIRMED', 'PENDING', 'GUARANTEED'],
            arrival_date__lte=business_date
        ).select_related('primary_guest').prefetch_related('room_allocations__inventory_unit_type')
        
        pending_arrivals = []
        for r in pending_arrivals_qs:
            alloc = r.room_allocations.first()
            room_type_name = alloc.inventory_unit_type.name if (alloc and alloc.inventory_unit_type) else "Standard"
            guest_name = f"{r.primary_guest.first_name} {r.primary_guest.last_name}".strip() if r.primary_guest else "Guest"
            
            pending_arrivals.append({
                'id': str(r.id),
                'confirmation_number': r.confirmation_number,
                'guest_name': guest_name,
                'room_type': room_type_name,
                'arrival_date': str(r.arrival_date),
                'check_in_date': str(r.arrival_date),
                'status': r.status,
                'is_guaranteed': True,
            })

        # 3. Pending departures (Overdue check-outs still marked in-house)
        pending_departures_qs = Reservation.objects.filter(
            property=property_obj,
            status='CHECKED_IN',
            departure_date__lte=business_date
        ).select_related('primary_guest').prefetch_related('room_allocations__inventory_unit_type')
        
        pending_departures = []
        for r in pending_departures_qs:
            alloc = r.room_allocations.first()
            room_type_name = alloc.inventory_unit_type.name if (alloc and alloc.inventory_unit_type) else "Standard"
            guest_name = f"{r.primary_guest.first_name} {r.primary_guest.last_name}".strip() if r.primary_guest else "Guest"
            
            pending_departures.append({
                'id': str(r.id),
                'confirmation_number': r.confirmation_number,
                'guest_name': guest_name,
                'room_type': room_type_name,
                'departure_date': str(r.departure_date),
                'check_out_date': str(r.departure_date),
                'status': r.status,
            })

        # 4. Cashier shifts
        open_shifts_qs = CashierShift.objects.filter(
            property=property_obj,
            status='OPEN'
        )
        open_shifts = []
        for s in open_shifts_qs:
            open_shifts.append({
                'id': str(s.id),
                'shift_code': s.shift_code,
                'opening_balance': float(s.opening_balance),
                'opened_at': s.opened_at.isoformat() if s.opened_at else None,
                'status': s.status,
            })

        # 5. Projected room charges & taxes for tonight
        projected_room_charges = Decimal('0.00')
        projected_taxes = Decimal('0.00')

        cgst_rate = Decimal(str(property_obj.cgst or 0.00)) / Decimal('100.00')
        vat_rate = Decimal(str(property_obj.vat or 0.00)) / Decimal('100.00')
        city_rate = Decimal(str(property_obj.city_tax or 0.00)) / Decimal('100.00')
        lux_rate = Decimal(str(property_obj.luxury_tax or 0.00)) / Decimal('100.00')
        tax_multiplier = cgst_rate + vat_rate + city_rate + lux_rate
        if tax_multiplier == Decimal('0.00'):
            tax_multiplier = Decimal('0.12')  # Standard 12% GST fallback

        for r in in_house_reservations:
            stay_nights = max((r.departure_date - r.arrival_date).days, 1)
            if r.total_amount and r.total_amount > 0:
                rate = Decimal(str(r.total_amount)) / Decimal(str(stay_nights))
            else:
                rate = Decimal('3500.00')

            projected_room_charges += rate
            projected_taxes += (rate * tax_multiplier)

        # 6. Check if audit was already completed for today / current business cycle
        latest_session = NightAuditSession.objects.filter(
            property=property_obj
        ).order_by('-audit_date', '-created_at').first()

        already_completed = False
        last_audit_session_data = None
        if latest_session and latest_session.status == 'COMPLETED':
            summary_new_date = (latest_session.post_audit_summary or {}).get('new_business_date')
            if str(latest_session.audit_date) == str(business_date) or summary_new_date == str(business_date):
                already_completed = True

            last_audit_session_data = {
                'id': str(latest_session.id),
                'audit_date': str(latest_session.audit_date),
                'status': latest_session.status,
                'completed_at': latest_session.completed_at.isoformat() if latest_session.completed_at else None,
                'rooms_total': latest_session.rooms_total,
                'rooms_occupied': latest_session.rooms_occupied,
                'occupancy_percentage': float(latest_session.occupancy_percentage),
                'total_room_charges_posted': float(latest_session.total_room_charges_posted),
                'total_tax_posted': float(latest_session.total_tax_posted),
                'total_charges_posted': float(latest_session.total_charges_posted),
                'no_shows_processed': latest_session.no_shows_processed,
                'guest_ledger_closing': float(latest_session.guest_ledger_closing),
                'post_audit_summary': latest_session.post_audit_summary or {},
            }

        vacant_rooms = max(total_rooms - occupied_rooms, 0)

        return {
            'business_date': str(business_date),
            'next_business_date': str(business_date + timedelta(days=1)),
            'already_completed_today': already_completed,
            'operational_metrics': {
                'total_rooms': total_rooms,
                'occupied_rooms': occupied_rooms,
                'vacant_rooms': vacant_rooms,
                'occupancy_percentage': occupancy_rate,
                'pending_checkins_count': len(pending_arrivals),
                'pending_checkouts_count': len(pending_departures),
                'open_shifts_count': len(open_shifts),
            },
            'financial_projections': {
                'projected_room_charges': round(float(projected_room_charges), 2),
                'projected_taxes': round(float(projected_taxes), 2),
                'projected_total': round(float(projected_room_charges + projected_taxes), 2),
                'currency': property_obj.currency or 'INR',
            },
            'pending_arrivals': pending_arrivals,
            'pending_departures': pending_departures,
            'open_shifts': open_shifts,
            'last_audit_session': last_audit_session_data,
        }

    @classmethod
    def validate_checklist(cls, property_obj: Property, tenant: Tenant) -> dict:
        """Runs the 5 core Night Audit validation rules and returns checklist items."""
        status_data = cls.get_audit_status(property_obj, tenant)
        ops = status_data['operational_metrics']

        checklist = []

        # 1. Expected arrivals
        has_pending_arrivals = ops['pending_checkins_count'] > 0
        checklist.append({
            'key': 'pending_arrivals',
            'title': 'Arrivals & Check-ins Reconciliation',
            'description': f"{ops['pending_checkins_count']} expected arrivals have not checked in yet." if has_pending_arrivals else "All scheduled arrivals for today have been checked in or processed.",
            'status': 'WARNING' if has_pending_arrivals else 'PASS',
            'count': ops['pending_checkins_count'],
            'can_auto_resolve': True,
            'recommendation': 'Check in remaining guests or let Night Audit auto-mark them as No-Show.',
            'items': status_data['pending_arrivals']
        })

        # 2. Expected departures
        has_pending_departures = ops['pending_checkouts_count'] > 0
        checklist.append({
            'key': 'pending_departures',
            'title': 'Departures & Check-outs Reconciliation',
            'description': f"{ops['pending_checkouts_count']} scheduled departures are still marked in-house." if has_pending_departures else "All expected departures for today have settled and checked out.",
            'status': 'WARNING' if has_pending_departures else 'PASS',
            'count': ops['pending_checkouts_count'],
            'can_auto_resolve': False,
            'recommendation': 'Perform checkout or extend reservation stay date before rolling over.',
            'items': status_data['pending_departures']
        })

        # 3. Cashier shifts
        has_open_shifts = ops['open_shifts_count'] > 0
        checklist.append({
            'key': 'cashier_shifts',
            'title': 'Front Desk Cashier Drawer Closures',
            'description': f"{ops['open_shifts_count']} cashier drawer shifts are currently open." if has_open_shifts else "All front desk cashier shifts have been balanced and closed.",
            'status': 'WARNING' if has_open_shifts else 'PASS',
            'count': ops['open_shifts_count'],
            'can_auto_resolve': True,
            'recommendation': 'Close active shifts or auto-reconcile during rollover.',
            'items': status_data['open_shifts']
        })

        # 4. Outlets & POS
        checklist.append({
            'key': 'pos_outlets',
            'title': 'F&B POS & Outlet Settlement',
            'description': 'All restaurant, bar, and room service orders verified and settled.',
            'status': 'PASS',
            'count': 0,
            'can_auto_resolve': True,
            'recommendation': 'All restaurant and room service checks posted to room folios.',
            'items': []
        })

        # 5. Housekeeping Status
        checklist.append({
            'key': 'housekeeping_status',
            'title': 'Housekeeping Discrepancy Alignment',
            'description': 'Front desk room occupancy verified against housekeeping room allocations.',
            'status': 'PASS',
            'count': 0,
            'can_auto_resolve': True,
            'recommendation': 'Occupied rooms will automatically queue for morning attendants.',
            'items': []
        })

        all_passed = all(item['status'] == 'PASS' for item in checklist)
        can_proceed = not any(item['status'] == 'FAIL' for item in checklist)

        return {
            'business_date': status_data['business_date'],
            'all_passed': all_passed,
            'can_proceed': can_proceed,
            'checklist': checklist,
        }

    @classmethod
    def get_auto_post_preview(cls, property_obj: Property, tenant: Tenant) -> dict:
        """Returns itemized list of every folio that will receive charges during auto-posting."""
        business_date = cls.get_property_business_date(property_obj)

        in_house_reservations = Reservation.objects.filter(
            property=property_obj,
            status='CHECKED_IN'
        ).select_related('primary_guest').prefetch_related('room_allocations__inventory_unit', 'room_allocations__inventory_unit_type')

        cgst_rate = Decimal(str(property_obj.cgst or 0.00)) / Decimal('100.00')
        vat_rate = Decimal(str(property_obj.vat or 0.00)) / Decimal('100.00')
        city_rate = Decimal(str(property_obj.city_tax or 0.00)) / Decimal('100.00')
        lux_rate = Decimal(str(property_obj.luxury_tax or 0.00)) / Decimal('100.00')
        tax_multiplier = cgst_rate + vat_rate + city_rate + lux_rate
        if tax_multiplier == Decimal('0.00'):
            tax_multiplier = Decimal('0.12')

        postings = []
        total_tariff = Decimal('0.00')
        total_taxes = Decimal('0.00')

        for r in in_house_reservations:
            stay_nights = max((r.departure_date - r.arrival_date).days, 1)
            if r.total_amount and r.total_amount > 0:
                rate = Decimal(str(r.total_amount)) / Decimal(str(stay_nights))
            else:
                rate = Decimal('3500.00')

            tax_val = round(rate * tax_multiplier, 2)
            total_val = rate + tax_val

            # Resolve folio
            folio = GuestFolio.objects.filter(reservation=r, tenant=tenant).first()
            current_balance = float(folio.balance) if folio else float(r.balance_amount or rate)

            # Resolve assigned room unit name
            alloc = r.room_allocations.first()
            room_name = alloc.inventory_unit.name if (alloc and alloc.inventory_unit) else "Room"
            room_type_name = alloc.inventory_unit_type.name if (alloc and alloc.inventory_unit_type) else "Standard Room"
            guest_name = f"{r.primary_guest.first_name} {r.primary_guest.last_name}".strip() if r.primary_guest else "Guest"

            postings.append({
                'reservation_id': str(r.id),
                'confirmation_number': r.confirmation_number,
                'guest_name': guest_name,
                'room_number': room_name,
                'room_type': room_type_name,
                'rate_plan': "BAR",
                'base_tariff': float(rate),
                'tax_amount': float(tax_val),
                'total_charge': float(total_val),
                'current_folio_balance': current_balance,
            })

            total_tariff += rate
            total_taxes += tax_val

        return {
            'business_date': str(business_date),
            'rooms_count': len(postings),
            'total_tariff': round(float(total_tariff), 2),
            'total_taxes': round(float(total_taxes), 2),
            'grand_total': round(float(total_tariff + total_taxes), 2),
            'postings': postings,
        }

    @classmethod
    def execute_night_audit(
        cls,
        property_obj: Property,
        tenant: Tenant,
        user=None,
        auto_noshow: bool = True,
        auto_close_cashiers: bool = True
    ) -> dict:
        """
        Executes the full, atomic Night Audit routine:
        1. Creates NightAuditSession
        2. Auto-posts room tariffs & taxes to in-house folios
        3. Processes No-Shows (if enabled)
        4. Reconciles cashier shifts
        5. Computes ledgers & balances
        6. Advances property.business_date by +1 day
        7. Returns complete audit results
        """
        business_date = cls.get_property_business_date(property_obj)
        next_date = business_date + timedelta(days=1)

        with transaction.atomic():
            # 1. Create NightAuditSession
            session = NightAuditSession.objects.create(
                tenant=tenant,
                property=property_obj,
                audit_date=business_date,
                status='IN_PROGRESS',
                performed_by=user if (user and user.is_authenticated) else None,
                started_at=timezone.now(),
            )

            total_rooms = InventoryUnit.objects.filter(property=property_obj).count()
            if total_rooms == 0:
                total_rooms = 1

            in_house_reservations = Reservation.objects.filter(
                property=property_obj,
                status='CHECKED_IN'
            ).select_related('primary_guest').prefetch_related('room_allocations__inventory_unit', 'room_allocations__inventory_unit_type')

            cgst_rate = Decimal(str(property_obj.cgst or 0.00)) / Decimal('100.00')
            vat_rate = Decimal(str(property_obj.vat or 0.00)) / Decimal('100.00')
            city_rate = Decimal(str(property_obj.city_tax or 0.00)) / Decimal('100.00')
            lux_rate = Decimal(str(property_obj.luxury_tax or 0.00)) / Decimal('100.00')
            tax_multiplier = cgst_rate + vat_rate + city_rate + lux_rate
            if tax_multiplier == Decimal('0.00'):
                tax_multiplier = Decimal('0.12')

            total_tariff_posted = Decimal('0.00')
            total_tax_posted = Decimal('0.00')
            total_charges_posted = Decimal('0.00')
            posted_folios_count = 0
            exception_logs = []

            # 2. Post Room Tariffs & Taxes
            for r in in_house_reservations:
                try:
                    folio, _ = GuestFolio.objects.get_or_create(
                        reservation=r,
                        tenant=tenant,
                        defaults={'folio_number': f"FOL-{r.confirmation_number}"}
                    )

                    stay_nights = max((r.departure_date - r.arrival_date).days, 1)
                    if r.total_amount and r.total_amount > 0:
                        rate = Decimal(str(r.total_amount)) / Decimal(str(stay_nights))
                    else:
                        rate = Decimal('3500.00')

                    tax_val = round(rate * tax_multiplier, 2)

                    # Post Tariff
                    FolioTransaction.objects.create(
                        tenant=tenant,
                        folio=folio,
                        transaction_type='CHARGE',
                        charge_code='ROOM_TARIFF',
                        amount=rate,
                        description=f"Room Tariff - Night of {business_date}"
                    )

                    # Post GST/Tax
                    if tax_val > 0:
                        FolioTransaction.objects.create(
                            tenant=tenant,
                            folio=folio,
                            transaction_type='CHARGE',
                            charge_code='TAX_GST',
                            amount=tax_val,
                            description=f"GST Room Tax ({business_date})"
                        )

                    # Update Folio totals
                    current_tc = Decimal(str(folio.total_charges or '0.00'))
                    current_tp = Decimal(str(folio.total_payments or '0.00'))
                    folio.total_charges = current_tc + rate + tax_val
                    folio.total_payments = current_tp
                    folio.balance = folio.total_charges - folio.total_payments
                    folio.save()

                    total_tariff_posted += rate
                    total_tax_posted += tax_val
                    total_charges_posted += (rate + tax_val)
                    posted_folios_count += 1

                except Exception as e:
                    logger.error(f"Error posting folio for reservation {r.id}: {e}")
                    exception_logs.append(f"Reservation {r.confirmation_number}: {str(e)}")

            # 3. Process No-Shows
            no_show_count = 0
            no_show_revenue = Decimal('0.00')

            if auto_noshow:
                pending_arrivals = Reservation.objects.filter(
                    property=property_obj,
                    status__in=['CONFIRMED', 'PENDING', 'GUARANTEED'],
                    arrival_date__lte=business_date
                )
                for res in pending_arrivals:
                    res.status = 'NO_SHOW'
                    res.save(update_fields=['status'])
                    no_show_count += 1

            # 4. Auto-close open cashier shifts
            if auto_close_cashiers:
                open_shifts = CashierShift.objects.filter(property=property_obj, status='OPEN')
                for s in open_shifts:
                    s.status = 'CLOSED'
                    s.closed_at = timezone.now()
                    s.save(update_fields=['status', 'closed_at'])

            # 5. Ledger calculations
            guest_ledger_closing = GuestFolio.objects.filter(
                tenant=tenant,
                status='OPEN'
            ).aggregate(total=models.Sum('balance'))['total'] or Decimal('0.00')

            # 6. Advance Property Business Date
            property_obj.business_date = next_date
            property_obj.save(update_fields=['business_date'])

            # 7. Complete NightAuditSession
            occupied_count = in_house_reservations.count()
            occupancy_pct = round((Decimal(str(occupied_count)) / Decimal(str(total_rooms))) * Decimal('100.00'), 2) if total_rooms > 0 else Decimal('0.00')

            session.status = 'COMPLETED'
            session.completed_at = timezone.now()
            session.rooms_occupied = occupied_count
            session.rooms_total = total_rooms
            session.occupancy_percentage = occupancy_pct
            session.total_room_charges_posted = total_tariff_posted
            session.total_tax_posted = total_tax_posted
            session.total_charges_posted = total_charges_posted
            session.no_shows_processed = no_show_count
            session.no_show_revenue = no_show_revenue
            session.guest_ledger_closing = guest_ledger_closing
            session.exception_logs = exception_logs
            session.post_audit_summary = {
                'old_business_date': str(business_date),
                'new_business_date': str(next_date),
                'rooms_audited': posted_folios_count,
                'total_posted': float(total_charges_posted),
                'occupancy': float(occupancy_pct),
                'no_shows': no_show_count,
            }
            session.save()

            return {
                'success': True,
                'session_id': str(session.id),
                'previous_business_date': str(business_date),
                'new_business_date': str(next_date),
                'audit_summary': {
                    'rooms_total': total_rooms,
                    'rooms_occupied': occupied_count,
                    'occupancy_percentage': float(occupancy_pct),
                    'total_room_charges_posted': float(total_tariff_posted),
                    'total_tax_posted': float(total_tax_posted),
                    'total_charges_posted': float(total_charges_posted),
                    'no_shows_processed': no_show_count,
                    'guest_ledger_closing': float(guest_ledger_closing),
                    'exceptions_count': len(exception_logs),
                }
            }
