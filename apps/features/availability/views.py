from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from apps.features.availability.models import (
    InventoryAvailability, InventoryRestriction, InventoryHold,
    GroupBlock, GroupBlockAllocation, Channel, ChannelAllocation,
    DynamicAvailabilityRule, WaitlistEntry,
    InventorySharedPool, InventorySharedPoolUnitType
)
from apps.features.availability.serializers import (
    InventoryAvailabilitySerializer,
    InventoryRestrictionSerializer,
    InventoryHoldSerializer,
    BulkAvailabilityUpdateSerializer,
    GroupBlockSerializer, GroupBlockAllocationSerializer,
    ChannelSerializer, ChannelAllocationSerializer,
    DynamicAvailabilityRuleSerializer,
    WaitlistEntrySerializer, InventorySharedPoolSerializer,
    InventorySharedPoolUnitTypeSerializer
)
from apps.features.availability.permissions import HasAvailabilityPermission, IsRestrictionManager, IsHoldManager
from apps.features.availability.services import (
    AvailabilityCalendarService,
    HoldService
)
from django.utils import timezone

class InventoryAvailabilityViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryAvailabilitySerializer
    permission_classes = [HasAvailabilityPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryAvailability.objects.none()
        qs = InventoryAvailability.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter('property_id', OpenApiTypes.UUID, required=True, description='Property ID context'),
            OpenApiParameter('start_date', OpenApiTypes.DATE, required=True, description='Start date (YYYY-MM-DD)'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, required=True, description='End date (YYYY-MM-DD)'),
            OpenApiParameter('inventory_unit_type_id', OpenApiTypes.UUID, required=False, description='Optional Unit Type filter'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='calendar')
    def get_calendar(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)
        
        property_id = request.query_params.get('property_id')
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        unit_type_id = request.query_params.get('inventory_unit_type_id')

        if not property_id or not start_date_str or not end_date_str:
            return Response({'error': 'Missing required parameters: property_id, start_date, end_date.'}, status=status.HTTP_400_BAD_REQUEST)

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        if not start_date or not end_date:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        calendar_data = AvailabilityCalendarService.get_calendar(
            tenant=tenant,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            unit_type_id=unit_type_id
        )
        return Response(calendar_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        serializer = BulkAvailabilityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        property_id = serializer.validated_data['property_id']
        updates = serializer.validated_data['updates']

        created_count = 0
        for update in updates:
            date_val = update['date']
            unit_type_id = update['inventory_unit_type_id']
            
            avail_record, _ = InventoryAvailability.objects.update_or_create(
                tenant=tenant,
                property_id=property_id,
                date=date_val,
                inventory_unit_type_id=unit_type_id,
                defaults={
                    'allocated_count': update.get('allocated_count', 0),
                    'sold_count': update.get('sold_count', 0),
                    'blocked_count': update.get('blocked_count', 0),
                    'overbooking_limit': update.get('overbooking_limit', 0),
                }
            )
            created_count += 1

        return Response({'status': 'success', 'created_records': created_count}, status=status.HTTP_200_OK)


from apps.core.common.mixins import RedisCacheMixin

class InventoryRestrictionViewSet(RedisCacheMixin, viewsets.ModelViewSet):
    serializer_class = InventoryRestrictionSerializer
    permission_classes = [IsRestrictionManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryRestriction.objects.none()
        qs = InventoryRestriction.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Bulk create or update restrictions over a date range"
    )
    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        property_id = request.data.get('property_id')
        if not property_id:
            from apps.core.tenants.models import Property
            propObj = Property.objects.filter(tenant=tenant).first()
            if propObj:
                property_id = propObj.id
            else:
                return Response({'error': 'property_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        start_date_str = request.data.get('start_date')
        end_date_str = request.data.get('end_date')
        inventory_unit_type_id = request.data.get('inventory_unit_type')
        restriction_type = request.data.get('restriction_type')
        restriction_value = request.data.get('restriction_value')

        if not start_date_str or not end_date_str or not restriction_type:
            return Response({'error': 'start_date, end_date, and restriction_type are required'}, status=status.HTTP_400_BAD_REQUEST)

        import datetime
        try:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        if start_date > end_date:
            return Response({'error': 'start_date cannot be after end_date'}, status=status.HTTP_400_BAD_REQUEST)

        created_count = 0
        current_date = start_date
        while current_date <= end_date:
            InventoryRestriction.objects.update_or_create(
                tenant=tenant,
                property_id=property_id,
                date=current_date,
                inventory_unit_type_id=inventory_unit_type_id if inventory_unit_type_id and inventory_unit_type_id != "All Room Types" else None,
                restriction_type=restriction_type,
                defaults={
                    'restriction_value': int(restriction_value) if restriction_value is not None else None
                }
            )
            created_count += 1
            current_date += datetime.timedelta(days=1)

        return Response({'status': 'success', 'created_records': created_count}, status=status.HTTP_200_OK)


class InventoryHoldViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryHoldSerializer
    permission_classes = [IsHoldManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryHold.objects.none()
        qs = InventoryHold.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='release')
    def release_hold(self, request, pk=None):
        hold = self.get_object()
        updated_hold = HoldService.release_hold(hold)
        return Response(InventoryHoldSerializer(updated_hold).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='convert')
    def convert_hold(self, request, pk=None):
        hold = self.get_object()
        updated_hold = HoldService.convert_hold(hold)
        return Response(InventoryHoldSerializer(updated_hold).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='expire-all')
    def expire_holds(self, request):
        expired_count = HoldService.expire_holds()
        return Response({'status': 'success', 'expired_count': expired_count}, status=status.HTTP_200_OK)


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

    @action(detail=True, methods=['post'], url_path='release')
    def release_block(self, request, pk=None):
        block = self.get_object()
        block.status = 'RELEASED'
        block.save()
        return Response(GroupBlockSerializer(block).data, status=status.HTTP_200_OK)


class GroupBlockAllocationViewSet(viewsets.ModelViewSet):
    serializer_class = GroupBlockAllocationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GroupBlockAllocation.objects.none()
        return GroupBlockAllocation.objects.filter(group_block__tenant=tenant)


class ChannelViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Channel.objects.none()
        return Channel.objects.filter(tenant=tenant)


class ChannelAllocationViewSet(viewsets.ModelViewSet):
    serializer_class = ChannelAllocationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return ChannelAllocation.objects.none()
        qs = ChannelAllocation.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class DynamicAvailabilityRuleViewSet(viewsets.ModelViewSet):
    serializer_class = DynamicAvailabilityRuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return DynamicAvailabilityRule.objects.none()
        qs = DynamicAvailabilityRule.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class WaitlistEntryViewSet(viewsets.ModelViewSet):
    serializer_class = WaitlistEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return WaitlistEntry.objects.none()
        qs = WaitlistEntry.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='convert')
    def convert_to_reservation(self, request, pk=None):
        entry = self.get_object()
        entry.status = 'CONVERTED'
        entry.converted_by = request.user if request and request.user.is_authenticated else None
        entry.converted_at = timezone.now()
        
        reservation_id = request.data.get('reservation_id')
        if reservation_id:
            entry.reservation_id = reservation_id
            
        entry.save()
        return Response(WaitlistEntrySerializer(entry).data, status=status.HTTP_200_OK)


class InventorySharedPoolViewSet(viewsets.ModelViewSet):
    serializer_class = InventorySharedPoolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventorySharedPool.objects.none()
        qs = InventorySharedPool.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class InventorySharedPoolUnitTypeViewSet(viewsets.ModelViewSet):
    serializer_class = InventorySharedPoolUnitTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventorySharedPoolUnitType.objects.none()
        return InventorySharedPoolUnitType.objects.filter(pool__tenant=tenant)
