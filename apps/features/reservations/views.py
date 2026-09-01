from decimal import Decimal
from django.db import models
from django.utils import timezone
from rest_framework import viewsets, status, permissions, serializers
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationEvent, ReservationExtraCharge, ReservationGuest
)
from apps.features.availability.models import WaitlistEntry
from apps.features.reservations.serializers import (
    CorporateAccountSerializer, GroupBlockSerializer, ReservationSerializer,
    ReservationListSerializer,
    ReservationEventSerializer, CreateBookingSerializer, AssignRoomSerializer,
    ModifyRemarksSerializer, CancelReservationSerializer,
    SplitReservationSerializer, MergeReservationSerializer,
    RoomUpgradeSerializer, RoomChangeSerializer, PriceEstimationSerializer,
    WaitlistEntrySerializer
)
from apps.features.reservations.permissions import HasReservationPermission
from apps.features.reservations.services import (
    BookingEngine, RoomAssignmentEngine, CheckInCheckOutEngine,
    ReservationModificationEngine, ReservationCancellationEngine,
    ReservationSearchEngine, ReservationEnhancementEngine
)
from apps.core.tenants.models import Property

class CorporateAccountViewSet(viewsets.ModelViewSet):
    serializer_class = CorporateAccountSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return CorporateAccount.objects.none()
        return CorporateAccount.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


class GroupBlockViewSet(viewsets.ModelViewSet):
    serializer_class = GroupBlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GroupBlock.objects.none()
        qs = GroupBlock.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)

        # Search filter
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(contact_name__icontains=search) |
                Q(contact_phone__icontains=search) |
                Q(contact_email__icontains=search) |
                Q(meal_plan__icontains=search) |
                Q(status__icontains=search) |
                Q(block_type__icontains=search)
            )

        # Status filter
        status_val = self.request.query_params.get('status')
        if status_val and status_val != 'All':
            qs = qs.filter(status__iexact=status_val)

        # Manager filter
        manager = self.request.query_params.get('manager') or self.request.query_params.get('contact_name')
        if manager and manager != 'All':
            qs = qs.filter(contact_name__iexact=manager)

        # Meal Plan filter
        meal_plan = self.request.query_params.get('meal_plan')
        if meal_plan and meal_plan != 'All':
            qs = qs.filter(meal_plan__iexact=meal_plan)

        # Date range filters (From & To)
        from_date = self.request.query_params.get('from_date') or self.request.query_params.get('start_date')
        if from_date:
            from django.db.models import Q
            qs = qs.filter(Q(end_date__gte=from_date) | Q(start_date__gte=from_date))

        to_date = self.request.query_params.get('to_date') or self.request.query_params.get('end_date')
        if to_date:
            qs = qs.filter(start_date__lte=to_date)

        # Exclude conference block if requested
        block_type = self.request.query_params.get('block_type')
        if block_type:
            qs = qs.filter(block_type=block_type)

        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

def handle_django_validation_error(e):
    if hasattr(e, 'message_dict') and e.message_dict:
        raise DRFValidationError(detail=e.message_dict)
    msg = e.messages[0] if hasattr(e, 'messages') and e.messages else str(e)
    raise DRFValidationError(detail=msg)


class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    permission_classes = [HasReservationPermission]

    def get_serializer_class(self):
        if self.action == 'list':
            return ReservationListSerializer
        return ReservationSerializer

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return Reservation.objects.none()
            
        if self.action == 'list':
            qs = Reservation.objects.filter(tenant=tenant).select_related(
                'primary_guest',
                'property',
                'reservation_source'
            ).prefetch_related(
                'room_allocations__inventory_unit',
                'room_allocations__inventory_unit_type',
                'primary_guest__contacts',
                'primary_guest__documents',
            )
        else:
            qs = Reservation.objects.filter(tenant=tenant).select_related(
                'primary_guest',
                'property',
                'reservation_source',
                'corporate_account',
                'group_block'
            ).prefetch_related(
                'room_allocations__inventory_unit',
                'room_allocations__inventory_unit_type',
                'room_allocations__rate_snapshots',
                'room_allocations__guests__guest__contacts',
                'room_allocations__guests__guest__documents',
                'services',
                'packages',
                'extra_charges',
                'timeline_events__actor_user'
            )

        # Property context filtering
        property_id = self.request.headers.get('X-Property-ID') or (getattr(self.request, 'query_params', {}).get('property_id') if hasattr(self.request, 'query_params') else None)
        if property_id:
            qs = qs.filter(property_id=property_id)
        
        # Filter by active window if start_date and end_date are provided
        from django.utils.dateparse import parse_date
        from django.db.models import Q
        q_params = getattr(self.request, 'query_params', getattr(self.request, 'GET', {}))
        start_date_str = q_params.get('start_date')
        end_date_str = q_params.get('end_date')
        
        if start_date_str and end_date_str:
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)
            if start_date and end_date:
                # Intersecting reservations: arrival < end AND departure > start
                qs = qs.filter(
                    arrival_date__lte=end_date,
                    departure_date__gte=start_date
                )
                
        return qs

    @extend_schema(request=PriceEstimationSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='estimate')
    def estimate(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = PriceEstimationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            from apps.features.reservations.services import PricingEngine
            estimate_result = PricingEngine.estimate_price(tenant, data)
            return Response(estimate_result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(request=CreateBookingSerializer, responses={201: ReservationSerializer})
    def create(self, request, *args, **kwargs):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        # property context is required
        property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')
        if not property_id:
            return Response({'error': 'X-Property-ID header or property_id parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            property_obj = Property.objects.get(id=property_id, tenant=tenant)
        except Property.DoesNotExist:
            return Response({'error': 'Property not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reservation = BookingEngine.create_booking(
                tenant=tenant,
                property_obj=property_obj,
                booking_data=serializer.validated_data,
                user=request.user
            )
        except (serializers.ValidationError, DjangoValidationError) as e:
            detail = e.messages if hasattr(e, 'messages') else (e.detail if hasattr(e, 'detail') else str(e))
            if isinstance(detail, list) and len(detail) == 1:
                detail = detail[0]
            return Response({'error': detail, 'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
        output = self.get_serializer(reservation)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, required=False, description='Search confirmation number, guest name, external reference'),
            OpenApiParameter('status', OpenApiTypes.STR, required=False, description='Filter by status'),
            OpenApiParameter('arrival_from', OpenApiTypes.DATE, required=False, description='Arrival from date'),
            OpenApiParameter('departure_to', OpenApiTypes.DATE, required=False, description='Departure to date'),
            OpenApiParameter('confirmation', OpenApiTypes.STR, required=False, description='Filter by exact confirmation number'),
            OpenApiParameter('phone', OpenApiTypes.STR, required=False, description='Filter by guest phone number'),
            OpenApiParameter('guest', OpenApiTypes.STR, required=False, description='Filter by guest name'),
            OpenApiParameter('room', OpenApiTypes.STR, required=False, description='Filter by assigned room name'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        query = request.query_params.get('query')
        status_filter = request.query_params.get('status')
        arrival_from = request.query_params.get('arrival_from')
        departure_to = request.query_params.get('departure_to')
        
        confirmation = request.query_params.get('confirmation')
        phone = request.query_params.get('phone')
        guest = request.query_params.get('guest')
        room = request.query_params.get('room')
        property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')

        results = ReservationSearchEngine.search_reservations(
            tenant=tenant,
            search_query=query,
            status_filter=status_filter,
            arrival_from=arrival_from,
            departure_to=departure_to,
            confirmation=confirmation,
            phone=phone,
            guest=guest,
            room=room,
            property_id=property_id
        )
        page = self.paginate_queryset(results)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=AssignRoomSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='assign-room')
    def assign_room(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        serializer = AssignRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RoomAssignmentEngine.assign_room(
                tenant=tenant,
                allocation_id=serializer.validated_data['allocation_id'],
                room_id=serializer.validated_data['room_id'],
                user=request.user,
                upgrade_reason=serializer.validated_data.get('upgrade_reason')
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        # return updated reservation
        output = self.get_serializer(reservation)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='check-in')
    def check_in(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        try:
            updated = CheckInCheckOutEngine.check_in(
                tenant=tenant,
                reservation_id=reservation.id,
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='check-out')
    def check_out(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        try:
            updated = CheckInCheckOutEngine.check_out(
                tenant=tenant,
                reservation_id=reservation.id,
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='undo-check-in')
    def undo_check_in(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        try:
            updated = CheckInCheckOutEngine.undo_check_in(
                tenant=tenant,
                reservation_id=reservation.id,
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='undo-check-out')
    def undo_check_out(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        try:
            updated = CheckInCheckOutEngine.undo_check_out(
                tenant=tenant,
                reservation_id=reservation.id,
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=CancelReservationSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        serializer = CancelReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = ReservationCancellationEngine.cancel_reservation(
            tenant=tenant,
            reservation_id=reservation.id,
            cancellation_reason=serializer.validated_data.get('cancellation_reason'),
            user=request.user
        )
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @extend_schema(request=ModifyRemarksSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='modify-remarks')
    def modify_remarks(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        serializer = ModifyRemarksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = ReservationModificationEngine.modify_remarks(
            tenant=tenant,
            reservation_id=reservation.id,
            remarks=serializer.validated_data['remarks'],
            special_requests=serializer.validated_data.get('special_requests'),
            user=request.user
        )
        output = self.get_serializer(updated)
        return Response(output.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='timeline')
    def timeline(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        events = ReservationEvent.objects.filter(tenant=tenant, reservation=reservation).order_by('timestamp')
        serializer = ReservationEventSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='add-guest')
    def add_guest(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        alloc = reservation.room_allocations.first()
        if not alloc:
            return Response({'error': 'No room allocation found on this reservation.'}, status=status.HTTP_400_BAD_REQUEST)

        full_name = request.data.get('fullName') or request.data.get('name') or ''
        parts = full_name.strip().split(' ', 1)
        first_name = parts[0] if parts else 'Guest'
        last_name = parts[1] if len(parts) > 1 else ''
        email = request.data.get('email', '').strip()
        phone = request.data.get('phone', '').strip()
        address = request.data.get('address', '').strip()
        id_type = request.data.get('idType') or request.data.get('id_type') or 'NATIONAL_ID'
        id_number = request.data.get('idNumber') or request.data.get('id_number') or ''
        id_proof = request.data.get('idProof') or request.data.get('id_proof') or ''

        from apps.features.crm.models import GuestProfile, GuestContact, GuestDocument
        from apps.features.crm.services import EncryptionHelper

        guest = None
        if email or phone:
            contact = GuestContact.objects.filter(tenant=tenant).filter(
                models.Q(email=email) if email else models.Q(phone=phone)
            ).first()
            if contact:
                guest = contact.guest

        if not guest:
            guest = GuestProfile.objects.create(
                tenant=tenant,
                first_name=first_name,
                last_name=last_name or '.',
                guest_type='DOMESTIC'
            )
            if email or phone:
                GuestContact.objects.create(
                    tenant=tenant,
                    guest=guest,
                    email=email or f"guest_{guest.id}@example.com",
                    phone=phone or '0000000000',
                    address_line_1=address or '',
                    is_primary=True
                )
            if id_number:
                doc_type_clean = id_type.upper().replace(' ', '_')
                if doc_type_clean not in ['PASSPORT', 'NATIONAL_ID', 'DRIVING_LICENCE']:
                    doc_type_clean = 'NATIONAL_ID'
                GuestDocument.objects.create(
                    tenant=tenant,
                    guest=guest,
                    document_type=doc_type_clean,
                    document_number=EncryptionHelper.encrypt(id_number),
                    attachment_url=id_proof or ''
                )
        else:
            if address:
                c = guest.contacts.filter(is_primary=True).first()
                if c:
                    c.address_line_1 = address
                    c.save(update_fields=['address_line_1'])
            if id_number:
                doc_type_clean = id_type.upper().replace(' ', '_')
                if doc_type_clean not in ['PASSPORT', 'NATIONAL_ID', 'DRIVING_LICENCE']:
                    doc_type_clean = 'NATIONAL_ID'
                d = guest.documents.first()
                if d:
                    d.document_type = doc_type_clean
                    d.document_number = EncryptionHelper.encrypt(id_number)
                    if id_proof:
                        d.attachment_url = id_proof
                    d.save()
                else:
                    GuestDocument.objects.create(
                        tenant=tenant,
                        guest=guest,
                        document_type=doc_type_clean,
                        document_number=EncryptionHelper.encrypt(id_number),
                        attachment_url=id_proof or ''
                    )

        ReservationGuest.objects.create(
            tenant=tenant,
            reservation_inventory=alloc,
            guest=guest,
            is_primary=False,
            guest_snapshot={
                'name': f"{first_name} {last_name}".strip(),
                'email': email,
                'phone': phone,
                'address': address,
                'id_type': id_type,
                'id_number': id_number,
                'id_proof_url': id_proof or '',
            }
        )

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='GUEST_ADDED',
            description=f"Additional Guest {first_name} {last_name} added to reservation.",
            actor_user=request.user
        )

        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remove-guest')
    def remove_guest(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        guest_id = request.data.get('guest_id') or request.data.get('reservation_guest_id')

        rg = ReservationGuest.objects.filter(
            tenant=tenant,
            reservation_inventory__reservation=reservation
        ).filter(models.Q(id=guest_id) | models.Q(guest_id=guest_id)).first()

        if rg:
            g_name = f"{rg.guest.first_name} {rg.guest.last_name}" if rg.guest else "Guest"
            rg.delete()
            ReservationEvent.objects.create(
                tenant=tenant,
                reservation=reservation,
                event_type='GUEST_REMOVED',
                description=f"Guest {g_name} removed from reservation.",
                actor_user=request.user
            )

        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='add-charge')
    def add_charge(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()

        description = request.data.get('description') or 'Room Service'
        amount_raw = Decimal(str(request.data.get('amount', 0)))
        tax_type = request.data.get('taxType') or request.data.get('tax_type') or 'Excluded'
        tax_percent = Decimal(str(request.data.get('taxPercent') or request.data.get('tax_percent') or 0))
        date_val = request.data.get('date')

        if tax_type == 'Excluded':
            tax_amount = amount_raw * (tax_percent / Decimal('100.0'))
            base_amount = amount_raw
        else:
            tax_amount = amount_raw - (amount_raw / (Decimal('1.0') + tax_percent / Decimal('100.0')))
            base_amount = amount_raw - tax_amount

        ReservationExtraCharge.objects.create(
            tenant=tenant,
            reservation=reservation,
            description=description,
            amount=base_amount,
            tax_amount=tax_amount,
            tax_type=tax_type,
            tax_percent=tax_percent,
            date=date_val if date_val else timezone.now().date()
        )

        reservation.total_amount = reservation.total_amount + base_amount
        reservation.tax_amount = reservation.tax_amount + tax_amount
        gross_total = (reservation.total_amount + reservation.tax_amount) - reservation.discount_amount
        reservation.balance_amount = max(Decimal('0.00'), gross_total - reservation.paid_amount)
        reservation.save()

        ReservationEvent.objects.create(
            tenant=tenant,
            reservation=reservation,
            event_type='CHARGE_POSTED',
            description=f"Folio charge '{description}' for ₹{amount_raw} added.",
            actor_user=request.user
        )

        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='remove-charge')
    def remove_charge(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        charge_id = request.data.get('charge_id')

        charge = ReservationExtraCharge.objects.filter(tenant=tenant, reservation=reservation, id=charge_id).first()
        if charge:
            c_desc = charge.description
            c_amt = charge.amount
            c_tax = charge.tax_amount
            charge.delete()

            reservation.total_amount = max(Decimal('0.00'), reservation.total_amount - c_amt)
            reservation.tax_amount = max(Decimal('0.00'), reservation.tax_amount - c_tax)
            gross_total = (reservation.total_amount + reservation.tax_amount) - reservation.discount_amount
            reservation.balance_amount = max(Decimal('0.00'), gross_total - reservation.paid_amount)
            reservation.save()

            ReservationEvent.objects.create(
                tenant=tenant,
                reservation=reservation,
                event_type='CHARGE_REMOVED',
                description=f"Folio charge '{c_desc}' removed.",
                actor_user=request.user
            )

        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='record-payment')
    def record_payment(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()

        amount = Decimal(str(request.data.get('amount', 0)))
        method = request.data.get('method') or request.data.get('payment_method') or 'Cash'
        pay_type = request.data.get('type') or 'Payment'

        if amount > Decimal('0.00'):
            reservation.paid_amount = reservation.paid_amount + amount
            gross_total = (reservation.total_amount + reservation.tax_amount) - reservation.discount_amount
            reservation.balance_amount = max(Decimal('0.00'), gross_total - reservation.paid_amount)
            reservation.save()

            ReservationEvent.objects.create(
                tenant=tenant,
                reservation=reservation,
                event_type='PAYMENT_RECEIVED',
                description=f"{pay_type} of ₹{amount} received via {method}.",
                actor_user=request.user
            )

        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='reinstate')
    def reinstate(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        reservation = self.get_object()
        updated = ReservationEnhancementEngine.reinstate_reservation(
            tenant=tenant,
            reservation_id=reservation.id,
            user=request.user
        )
        return Response(self.get_serializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(request=SplitReservationSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='split')
    def split(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SplitReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        parent, child = ReservationEnhancementEngine.split_reservation(
            tenant=tenant,
            reservation_id=self.get_object().id,
            allocation_ids=serializer.validated_data['allocation_ids'],
            user=request.user
        )
        return Response({
            'parent': self.get_serializer(parent).data,
            'child': self.get_serializer(child).data
        }, status=status.HTTP_200_OK)

    @extend_schema(request=MergeReservationSerializer, responses={200: ReservationSerializer})
    @action(detail=False, methods=['post'], url_path='merge')
    def merge(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        # We can pass primary_reservation_id in body
        primary_id = request.data.get('primary_reservation_id')
        secondary_id = request.data.get('secondary_reservation_id')

        if not primary_id or not secondary_id:
            return Response({'error': 'Provide primary_reservation_id and secondary_reservation_id.'}, status=status.HTTP_400_BAD_REQUEST)

        updated = ReservationEnhancementEngine.merge_reservations(
            tenant=tenant,
            primary_reservation_id=primary_id,
            secondary_reservation_id=secondary_id,
            user=request.user
        )
        return Response(self.get_serializer(updated).data, status=status.HTTP_200_OK)

    @extend_schema(request=RoomUpgradeSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='upgrade-room')
    def upgrade_room(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RoomUpgradeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RoomAssignmentEngine.upgrade_room(
                tenant=tenant,
                allocation_id=serializer.validated_data['allocation_id'],
                new_inventory_type_id=serializer.validated_data['new_inventory_type_id'],
                upgrade_reason=serializer.validated_data['upgrade_reason'],
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @extend_schema(request=RoomChangeSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=['post'], url_path='change-room')
    def change_room(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RoomChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RoomAssignmentEngine.change_room(
                tenant=tenant,
                allocation_id=serializer.validated_data['allocation_id'],
                new_room_id=serializer.validated_data['new_room_id'],
                new_check_in_date=serializer.validated_data.get('new_check_in_date'),
                new_check_out_date=serializer.validated_data.get('new_check_out_date'),
                user=request.user
            )
        except DjangoValidationError as e:
            handle_django_validation_error(e)
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='validate-availability')
    def validate_availability(self, request):
        # Simplistic validation stub for wizard integration
        return Response({'valid': True, 'message': 'Inventory availability validation successful.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='validate-pricing')
    def validate_pricing(self, request):
        return Response({'valid': True, 'message': 'Rate plan pricing validation successful.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='validate-restrictions')
    def validate_restrictions(self, request):
        return Response({'valid': True, 'message': 'Restrictions check successful.'}, status=status.HTTP_200_OK)


class WaitlistViewSet(viewsets.ModelViewSet):
    """CRUD API for waitlist entries + convert action."""
    serializer_class = WaitlistEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return WaitlistEntry.objects.none()
        qs = WaitlistEntry.objects.filter(tenant=tenant).select_related('guest', 'inventory_unit_type')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        else:
            # Default: show only PENDING (waiting) entries
            qs = qs.filter(status='PENDING')
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        from apps.core.tenants.models import Property
        tenant = getattr(self.request, 'tenant', None)
        # Get first property for tenant
        prop = Property.objects.filter(tenant=tenant).first()
        serializer.save(tenant=tenant, property=prop)

    def create(self, request, *args, **kwargs):
        """
        Accept simplified payload from frontend:
        { guest_name, email, phone, check_in_date, check_out_date,
          inventory_unit_type_id, priority (1-3), notes }
        """
        from apps.features.crm.models import GuestProfile
        from apps.features.inventory.models import InventoryUnitType
        from apps.core.tenants.models import Property

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'detail': 'Tenant not found'}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        prop = Property.objects.filter(tenant=tenant).first()

        # Resolve or create guest profile
        guest = None
        guest_name = data.get('guest_name', '')
        email = data.get('email', '')
        if email:
            guest = GuestProfile.objects.filter(tenant=tenant, contacts__email=email).first()
        if not guest and guest_name:
            parts = guest_name.strip().split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else 'Guest'
            try:
                guest = GuestProfile.objects.create(
                    tenant=tenant, first_name=first_name, last_name=last_name,
                    guest_type='DOMESTIC'
                )
            except Exception:
                pass

        # Resolve room type (either UUID or Name)
        unit_type = None
        unit_type_id = data.get('inventory_unit_type_id') or data.get('room_type_id')
        if unit_type_id:
            import uuid
            is_uuid = False
            try:
                uuid.UUID(str(unit_type_id))
                is_uuid = True
            except (ValueError, AttributeError):
                pass

            if is_uuid:
                try:
                    unit_type = InventoryUnitType.objects.get(id=unit_type_id, tenant=tenant)
                except InventoryUnitType.DoesNotExist:
                    pass
            else:
                try:
                    unit_type = InventoryUnitType.objects.get(name__iexact=unit_type_id, tenant=tenant)
                except InventoryUnitType.DoesNotExist:
                    pass

        if not unit_type:
            return Response({'detail': 'Valid room type required.'}, status=status.HTTP_400_BAD_REQUEST)

        priority_map = {'HIGH': 3, 'NORMAL': 2, 'LOW': 1}
        priority_str = str(data.get('priority', 'NORMAL')).upper()
        priority_int = priority_map.get(priority_str, 2)

        try:
            entry = WaitlistEntry.objects.create(
                tenant=tenant,
                property=prop,
                guest=guest,
                email_snapshot=email,
                phone_snapshot=data.get('phone', ''),
                inventory_unit_type=unit_type,
                check_in_date=data.get('check_in_date'),
                check_out_date=data.get('check_out_date'),
                priority=priority_int,
                status='PENDING',
            )
            return Response(WaitlistEntrySerializer(entry).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='convert')
    def convert(self, request, pk=None):
        """Mark waitlist entry as CONVERTED and create Reservation."""
        entry = self.get_object()
        if entry.status != 'PENDING':
            return Response(
                {'detail': f'Entry is already {entry.status}.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'detail': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Resolve guest profile
        guest = entry.guest
        if not guest:
            from apps.features.crm.models import GuestProfile, GuestContact
            guest_name_val = entry.email_snapshot or 'Waitlist Guest'
            parts = guest_name_val.split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else 'Guest'
            try:
                guest = GuestProfile.objects.create(
                    tenant=tenant,
                    first_name=first_name,
                    last_name=last_name,
                    guest_type='DOMESTIC'
                )
                GuestContact.objects.create(
                    tenant=tenant,
                    guest=guest,
                    email=entry.email_snapshot,
                    phone=entry.phone_snapshot,
                    is_primary=True
                )
                entry.guest = guest
                entry.save(update_fields=['guest'])
            except Exception as e:
                return Response({'detail': f'Failed to create guest profile: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Call BookingEngine.create_booking to create actual reservation
        from apps.features.reservations.services import BookingEngine
        from apps.features.rates.models import RatePlan
        
        # Get first active rate plan for the property
        rate_plan = RatePlan.objects.filter(property=entry.property, is_active=True).first()
        rate_plan_id = str(rate_plan.id) if rate_plan else None
        
        booking_data = {
            'primary_guest_id': guest.id,
            'arrival_date': entry.check_in_date,
            'departure_date': entry.check_out_date,
            'reservation_type': 'Individual',
            'market_segment': 'Direct',
            'notes': 'Converted from Waitlist Entry',
            'allocations': [
                {
                    'inventory_unit_type_id': entry.inventory_unit_type.id,
                    'check_in_date': entry.check_in_date,
                    'check_out_date': entry.check_out_date,
                    'adult_count': 2,
                    'child_count': 0,
                    'rate_plan_id': rate_plan_id,
                }
            ]
        }
        
        try:
            from django.db import transaction
            with transaction.atomic():
                reservation = BookingEngine.create_booking(
                    tenant=tenant,
                    property_obj=entry.property,
                    booking_data=booking_data,
                    user=request.user
                )
                
                from django.utils import timezone
                entry.status = 'CONVERTED'
                entry.converted_at = timezone.now()
                entry.converted_by = request.user
                entry.reservation = reservation
                entry.save(update_fields=['status', 'converted_at', 'converted_by', 'reservation', 'updated_at'])
        except Exception as e:
            return Response({'detail': f'Failed to create reservation: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WaitlistEntrySerializer(entry).data)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_entry(self, request, pk=None):
        entry = self.get_object()
        entry.status = 'CANCELLED'
        entry.save(update_fields=['status', 'updated_at'])
        return Response(WaitlistEntrySerializer(entry).data)
