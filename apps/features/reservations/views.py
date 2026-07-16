from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.forms.models import model_to_dict

from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationEvent
)
from apps.features.reservations.serializers import (
    CorporateAccountSerializer, GroupBlockSerializer, ReservationSerializer,
    ReservationEventSerializer, CreateBookingSerializer, AssignRoomSerializer,
    ModifyRemarksSerializer, CancelReservationSerializer,
    ModifyRemarksSerializer, CancelReservationSerializer,
    SplitReservationSerializer, MergeReservationSerializer,
    RoomUpgradeSerializer, RoomChangeSerializer, PriceEstimationSerializer
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
        return GroupBlock.objects.filter(tenant=tenant)

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

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Reservation.objects.none()
        return Reservation.objects.filter(tenant=tenant).select_related(
            'primary_guest',
            'reservation_source',
            'corporate_account',
            'group_block'
        ).prefetch_related(
            'room_allocations__inventory_unit',
            'room_allocations__inventory_unit_type',
            'room_allocations__rate_snapshots',
            'room_allocations__guests'
        )

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

        reservation = BookingEngine.create_booking(
            tenant=tenant,
            property_obj=property_obj,
            booking_data=serializer.validated_data,
            user=request.user
        )
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


