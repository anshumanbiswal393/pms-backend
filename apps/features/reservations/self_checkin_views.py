import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from apps.features.reservations.models import Reservation, ReservationEvent, ReservationGuest
from apps.features.reservations.services import CheckInCheckOutEngine

logger = logging.getLogger(__name__)


class PublicSelfCheckInVerifyView(APIView):
    """
    Public endpoint for arriving guests to verify and load their reservation
    before completing self check-in.
    Bypasses tenant auth headers.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return self._process_verification(request)

    def post(self, request):
        return self._process_verification(request)

    def _process_verification(self, request):
        params = request.query_params if request.method == 'GET' else request.data
        booking_id = params.get('id') or params.get('booking_id')
        confirmation = params.get('confirmation') or params.get('confirmation_number')

        if not booking_id and not confirmation:
            return Response(
                {"valid": False, "error": "Reservation ID or Confirmation Number is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = Reservation.objects.select_related('primary_guest', 'property').prefetch_related(
            'room_allocations__inventory_unit',
            'room_allocations__inventory_unit_type',
            'timeline_events'
        )

        res = None
        if booking_id:
            res = qs.filter(id=booking_id).first()
        if not res and confirmation:
            res = qs.filter(confirmation_number__iexact=confirmation.strip()).first()

        if not res:
            return Response(
                {
                    "valid": False,
                    "error": "No booking found matching the provided confirmation details. Please check your reservation information or contact the hotel front desk."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # Check reservation status
        if res.status == 'CANCELLED':
            return Response(
                {
                    "valid": False,
                    "error": "This reservation has been cancelled. Please reach out to our team if this was in error."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if res.status == 'CHECKED_IN':
            return Response(
                {
                    "valid": True,
                    "already_checked_in": True,
                    "message": "You are already checked in. We hope you enjoy your stay!",
                    "confirmation_number": res.confirmation_number,
                    "guest_name": f"{res.primary_guest.first_name} {res.primary_guest.last_name}".strip() if res.primary_guest else "Valued Guest"
                },
                status=status.HTTP_200_OK
            )

        if res.status == 'CHECKED_OUT':
            return Response(
                {
                    "valid": False,
                    "error": "This stay has already concluded."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Operational date check:
        # Business requirement: Guest can only check in on the arrival date.
        today_local = timezone.localdate()
        prop_date = res.property.business_date if (res.property and res.property.business_date) else today_local
        if prop_date < today_local:
            prop_date = today_local
            if res.property and res.property.business_date and res.property.business_date < today_local:
                res.property.business_date = today_local
                res.property.save(update_fields=['business_date'])

        is_arrival_date = (prop_date >= res.arrival_date)
        is_early = (prop_date < res.arrival_date)
        days_until_arrival = (res.arrival_date - prop_date).days if is_early else 0

        # Primary guest details
        guest = res.primary_guest
        guest_name = ""
        guest_phone = ""
        guest_email = ""
        if guest:
            guest_name = f"{getattr(guest, 'salutation', '') or ''} {guest.first_name} {guest.last_name}".strip()
            primary_contact = guest.contacts.filter(is_primary=True).first() or guest.contacts.first()
            if primary_contact:
                guest_phone = getattr(primary_contact, 'phone', '') or ''
                guest_email = getattr(primary_contact, 'email', '') or ''

        # Rooms info
        allocations = list(res.room_allocations.all())
        room_types = list(set([a.inventory_unit_type.name for a in allocations if a.inventory_unit_type]))
        assigned_units = [a.inventory_unit.name for a in allocations if a.inventory_unit]

        # Check existing submission
        submitted_event = res.timeline_events.filter(event_type='SELF_CHECKIN_SUBMITTED').last()
        is_already_submitted = submitted_event is not None
        submitted_data = submitted_event.payload_diff if submitted_event else None

        arrival_str = res.arrival_date.strftime('%d-%b-%Y')
        departure_str = res.departure_date.strftime('%d-%b-%Y')

        status_message = ""
        if is_early:
            status_message = f"Your reservation is confirmed! Self check-in will open on your arrival date: {res.arrival_date.strftime('%d-%b-%Y')}."
        elif is_already_submitted:
            status_message = "Your self check-in details have been submitted. Our front desk will have your keys and registration ready upon arrival."
        else:
            status_message = "Today is your arrival date! Please complete your check-in details below."

        return Response({
            "valid": True,
            "id": str(res.id),
            "confirmation_number": res.confirmation_number,
            "status": res.status,
            "can_checkin": is_arrival_date and not is_already_submitted,
            "is_early": is_early,
            "is_arrival_date": is_arrival_date,
            "is_submitted": is_already_submitted,
            "days_until_arrival": days_until_arrival,
            "current_hotel_date": str(prop_date),
            "arrival_date": str(res.arrival_date),
            "departure_date": str(res.departure_date),
            "arrival_display": f"{res.arrival_date.strftime('%d-%b')} {res.check_in_time or '12:00 PM'}",
            "departure_display": f"{res.departure_date.strftime('%d-%b')} {res.check_out_time or '10:00 AM'}",
            "check_in_time": res.check_in_time or "12:00 PM",
            "check_out_time": res.check_out_time or "10:00 AM",
            "status_message": status_message,
            "property": {
                "name": res.property.name if res.property else "Hotel",
                "phone": getattr(res.property, 'contact_phone', '') or "",
                "email": getattr(res.property, 'contact_email', '') or "",
                "address": f"{getattr(res.property, 'address_line_1', '')} {getattr(res.property, 'city', '')}".strip() if res.property else "",
                "logo": getattr(res.property, 'website_logo', '') or "",
            },
            "guest": {
                "name": guest_name or "Guest",
                "phone": guest_phone,
                "email": guest_email,
            },
            "stay": {
                "rooms_count": len(allocations) or 1,
                "room_types": ", ".join(room_types) or "Standard Room",
                "assigned_rooms": ", ".join(assigned_units) if assigned_units else "To be assigned at front desk",
                "total_amount": float(res.total_amount or 0),
                "paid_amount": float(res.paid_amount or 0),
                "balance_amount": float(res.balance_amount or 0),
            },
            "submitted_data": submitted_data
        }, status=status.HTTP_200_OK)


class PublicSelfCheckInSubmitView(APIView):
    """
    Public endpoint for guests to submit digital self check-in details.
    Enforces that checkin is only permitted on the arrival date.
    Verifies reservation existence against database.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = request.data
        booking_id = data.get('id') or data.get('booking_id')
        confirmation = data.get('confirmation') or data.get('confirmation_number')

        if not booking_id and not confirmation:
            return Response(
                {"error": "Booking ID or confirmation number required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = Reservation.objects.select_related('primary_guest', 'property', 'tenant')
        res = None
        if booking_id:
            res = qs.filter(id=booking_id).first()
        if not res and confirmation:
            res = qs.filter(confirmation_number__iexact=confirmation.strip()).first()

        if not res:
            return Response(
                {"error": "No booked reservation exists for this confirmation."},
                status=status.HTTP_404_NOT_FOUND
            )

        if res.status in ['CANCELLED', 'NO_SHOW']:
            return Response(
                {"error": f"Reservation cannot be checked in because it is {res.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # STRICT ARRIVAL DATE VERIFICATION
        today_local = timezone.localdate()
        prop_date = res.property.business_date if (res.property and res.property.business_date) else today_local
        if prop_date < today_local:
            prop_date = today_local
            if res.property and res.property.business_date and res.property.business_date < today_local:
                res.property.business_date = today_local
                res.property.save(update_fields=['business_date'])

        if prop_date < res.arrival_date:
            return Response(
                {
                    "error": f"Self check-in can only be submitted on your arrival date ({res.arrival_date.strftime('%d-%b-%Y')}). Please return on your arrival day."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract submitted verification data
        guest_name = data.get('guest_name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        id_type = data.get('id_type', 'Passport').strip()
        id_number = data.get('id_number', '').strip()
        id_document_url = data.get('id_document_url', '')
        address = data.get('address', '').strip()
        eta = data.get('eta', '').strip()
        special_requests = data.get('special_requests', '').strip()

        submission_payload = {
            "guest_name": guest_name,
            "phone": phone,
            "email": email,
            "id_type": id_type,
            "id_number": id_number,
            "id_document_url": id_document_url,
            "address": address,
            "eta": eta,
            "special_requests": special_requests,
            "submitted_at": timezone.now().isoformat()
        }

        # Record timeline event in database
        ReservationEvent.objects.create(
            tenant=res.tenant,
            reservation=res,
            event_type='SELF_CHECKIN_SUBMITTED',
            description=f"Guest {guest_name or 'Arriving Guest'} submitted self check-in details with {id_type} ending in {id_number[-4:] if len(id_number) >= 4 else id_number}",
            payload_diff=submission_payload
        )

        # Optionally update special requests if provided
        if special_requests and not res.special_requests:
            res.special_requests = special_requests
            res.save(update_fields=['special_requests'])

        logger.info(f"[SELF-CHECKIN] Successfully submitted self check-in for reservation {res.confirmation_number}")

        return Response({
            "success": True,
            "message": "Self check-in submitted successfully! Your hotel front desk has received your verification details.",
            "confirmation_number": res.confirmation_number,
            "submitted_data": submission_payload
        }, status=status.HTTP_200_OK)
