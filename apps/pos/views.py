from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from apps.POS.models import (
    Outlet,
    FloorSection,
    RestaurantTable,
    POSRegister,
    DeviceMapping,
    TaxProfile,
    MenuCategory,
    MenuItem,
    ModifierGroup,
    SpecialNote,
    POSOrder,
    POSRecipe,
)
from apps.POS.serializers import (
    OutletSerializer,
    OutletLiveFloorMapSerializer,
    FloorSectionSerializer,
    RestaurantTableSerializer,
    TableStatusUpdateSerializer,
    TableTransferSerializer,
    POSRegisterSerializer,
    DeviceMappingSerializer,
    OccupiedRoomsResponseSerializer,
    TaxProfileSerializer,
    MenuCategorySerializer,
    MenuItemWriteSerializer,
    MenuItemUISerializer,
    ModifierGroupSerializer,
    SpecialNoteSerializer,
    BulkPlatformUpdateSerializer,
    POSOrderCreateSerializer,
    POSOrderUpdateSerializer,
    POSOrderSettleSerializer,
    POSDueSettleSerializer,
)
from apps.POS.services.occupancy import OccupancyService
from apps.POS.services.menu import MenuCatalogService
from apps.POS.services.orders import OrderService
from apps.POS.services.dues import DueLedgerService, DayCloseService, ExportService
from apps.POS.services.stock import (
    StockService,
    ReportService,
    AggregatorWebhookService,
)
from apps.POS.services.reports import SalesAnalyticsService, parse_iso_date
from apps.POS.services.production import ProductionService
from apps.POS.services.purchases import PurchaseService
from rest_framework.exceptions import ValidationError
from django.http import HttpResponse
from datetime import datetime
from decimal import Decimal

@extend_schema_view(
    list=extend_schema(tags=['POS - Outlets & Floor Plan'], description="List all POS dining outlets with optional property filter."),
    retrieve=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Retrieve a specific POS outlet details."),
    create=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Create a new physical or virtual POS dining outlet."),
    update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Update an existing POS dining outlet."),
    partial_update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Partially update an existing POS dining outlet."),
    destroy=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Soft-delete a POS dining outlet."),
)
class OutletViewSet(viewsets.ModelViewSet):
    serializer_class = OutletSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # UI create must not stall on JWT/session/CSRF

    def get_queryset(self):
        qs = Outlet.objects.filter(deleted_at__isnull=True)
        property_id = self.request.query_params.get('property_id') or self.request.headers.get('X-Property-ID')
        tenant_id = self.request.query_params.get('tenant_id') or self.request.headers.get('X-Tenant-ID')
        outlet_type = self.request.query_params.get('outlet_type')
        is_active = self.request.query_params.get('is_active')

        if property_id:
            qs = qs.filter(property_id=property_id)
        elif hasattr(self.request.user, 'properties') and self.request.user.is_authenticated:
            # Multi-property scope if authenticated
            user_props = self.request.user.properties.all()
            if user_props.exists():
                qs = qs.filter(property__in=user_props)

        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        elif hasattr(self.request.user, 'tenant') and self.request.user.is_authenticated and self.request.user.tenant:
            qs = qs.filter(tenant=self.request.user.tenant)

        if outlet_type:
            qs = qs.filter(outlet_type=outlet_type.upper())
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1'])

        return qs.select_related('property', 'tenant').prefetch_related('sections')

    def create(self, request, *args, **kwargs):
        """Create outlet with one DB reconnect retry (remote Postgres blips)."""
        from django.db import close_old_connections, connection
        from django.db.utils import OperationalError, InterfaceError

        close_old_connections()
        try:
            return super().create(request, *args, **kwargs)
        except (OperationalError, InterfaceError):
            connection.close()
            close_old_connections()
            return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    @extend_schema(
        tags=['POS - Outlets & Floor Plan'],
        responses={200: OutletLiveFloorMapSerializer},
        description="Retrieve complete live floor plan with sections and colored tables in a single optimized payload."
    )
    @action(detail=True, methods=['get'], url_path='live-floor-map')
    def live_floor_map(self, request, pk=None):
        outlet = self.get_object()
        serializer = OutletLiveFloorMapSerializer(outlet, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        tags=['POS - Outlets & Floor Plan'],
        description="Get operational summary metrics (vacant/occupied tables count, total PAX seated) for this outlet."
    )
    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        outlet = self.get_object()
        tables = RestaurantTable.objects.filter(section__outlet=outlet, is_active=True, deleted_at__isnull=True)
        
        total_tables = tables.count()
        vacant_tables = tables.filter(status='VACANT').count()
        occupied_tables = tables.filter(status='OCCUPIED').count()
        billed_tables = tables.filter(status='BILLED').count()
        dirty_tables = tables.filter(status='DIRTY').count()
        reserved_tables = tables.filter(status='RESERVED').count()
        
        total_capacity = sum(t.capacity for t in tables)
        occupied_capacity = sum(t.capacity for t in tables.filter(status='OCCUPIED'))
        
        registers = POSRegister.objects.filter(outlet=outlet, is_active=True, deleted_at__isnull=True)
        online_devices = DeviceMapping.objects.filter(register__outlet=outlet, status='ONLINE', is_authorized=True).count()

        return Response({
            "outlet_id": outlet.id,
            "outlet_name": outlet.name,
            "outlet_type": outlet.outlet_type,
            "currency": outlet.currency,
            "tables": {
                "total": total_tables,
                "vacant": vacant_tables,
                "occupied": occupied_tables,
                "billed": billed_tables,
                "dirty": dirty_tables,
                "reserved": reserved_tables,
                "occupancy_rate_percentage": round((occupied_tables / total_tables * 100), 2) if total_tables > 0 else 0.0,
            },
            "pax": {
                "total_capacity": total_capacity,
                "seated_capacity": occupied_capacity,
            },
            "hardware": {
                "total_registers": registers.count(),
                "online_devices": online_devices,
            }
        })


@extend_schema_view(
    list=extend_schema(tags=['POS - Outlets & Floor Plan'], description="List floor sections with optional outlet_id filter."),
    retrieve=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Retrieve a specific floor section."),
    create=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Create a new floor section (e.g., AC Hall, Terrace Lounge)."),
    update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Update a floor section."),
    partial_update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Partially update a floor section."),
    destroy=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Soft-delete a floor section."),
)
class FloorSectionViewSet(viewsets.ModelViewSet):
    serializer_class = FloorSectionSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = FloorSection.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id') or self.request.headers.get('X-Outlet-ID')
        is_active = self.request.query_params.get('is_active')

        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1'])

        return qs.select_related('outlet').prefetch_related('tables')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)


@extend_schema_view(
    list=extend_schema(tags=['POS - Outlets & Floor Plan'], description="List dining tables with section, outlet, or status filter."),
    retrieve=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Retrieve a specific dining table."),
    create=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Create a new dining table."),
    update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Update a dining table configuration."),
    partial_update=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Partially update a dining table."),
    destroy=extend_schema(tags=['POS - Outlets & Floor Plan'], description="Soft-delete a dining table."),
)
class RestaurantTableViewSet(viewsets.ModelViewSet):
    serializer_class = RestaurantTableSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = RestaurantTable.objects.filter(deleted_at__isnull=True)
        section_id = self.request.query_params.get('section_id')
        outlet_id = self.request.query_params.get('outlet_id') or self.request.headers.get('X-Outlet-ID')
        status_param = self.request.query_params.get('status')
        is_active = self.request.query_params.get('is_active')

        if section_id:
            qs = qs.filter(section_id=section_id)
        if outlet_id:
            qs = qs.filter(section__outlet_id=outlet_id)
        if status_param:
            qs = qs.filter(status=status_param.upper())
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1'])

        return qs.select_related('section', 'section__outlet')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    @extend_schema(
        tags=['POS - Outlets & Floor Plan'],
        request=TableStatusUpdateSerializer,
        responses={200: RestaurantTableSerializer},
        description="Update the live operational state of a dining table (VACANT, OCCUPIED, BILLED, DIRTY, RESERVED)."
    )
    @action(detail=True, methods=['patch', 'post'], url_path='status')
    def update_status(self, request, pk=None):
        table = self.get_object()
        serializer = TableStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data['status']
        table.status = new_status

        if 'notes' in serializer.validated_data:
            table.notes = serializer.validated_data['notes']
        if 'active_waiter_name' in serializer.validated_data:
            table.active_waiter_name = serializer.validated_data['active_waiter_name']
        if 'active_order_id' in serializer.validated_data:
            table.active_order_id = serializer.validated_data['active_order_id']

        # Clear session if table is released back to VACANT
        if new_status == 'VACANT':
            table.active_order_id = None
            table.active_waiter_name = None

        user = request.user if request.user.is_authenticated else None
        table.updated_by = user
        table.save(update_fields=['status', 'notes', 'active_waiter_name', 'active_order_id', 'updated_by', 'updated_at'])

        return Response(RestaurantTableSerializer(table, context={'request': request}).data)

    @extend_schema(
        tags=['POS - Outlets & Floor Plan'],
        request=TableTransferSerializer,
        description="Transfer dining session from a source table to a destination table."
    )
    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer(self, request):
        serializer = TableTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        src_id = serializer.validated_data['source_table_id']
        dest_id = serializer.validated_data['destination_table_id']
        reason = serializer.validated_data.get('reason', 'Guest table transfer')

        try:
            src_table = RestaurantTable.objects.get(id=src_id, deleted_at__isnull=True)
            dest_table = RestaurantTable.objects.get(id=dest_id, deleted_at__isnull=True)
        except RestaurantTable.DoesNotExist:
            return Response({"error": "Source or destination table does not exist."}, status=status.HTTP_404_NOT_FOUND)

        if dest_table.status != 'VACANT':
            return Response({"error": f"Destination table {dest_table.table_number} is not vacant (status: {dest_table.status})."}, status=status.HTTP_400_BAD_REQUEST)

        # Transfer active attributes
        dest_table.status = src_table.status
        dest_table.active_order_id = src_table.active_order_id
        dest_table.active_waiter_name = src_table.active_waiter_name
        dest_table.notes = f"{dest_table.notes or ''} [Transferred from {src_table.table_number}: {reason}]".strip()
        dest_table.save()

        # Free source table to DIRTY
        src_table.status = 'DIRTY'
        src_table.active_order_id = None
        src_table.active_waiter_name = None
        src_table.notes = f"{src_table.notes or ''} [Transferred to {dest_table.table_number}]".strip()
        src_table.save()

        return Response({
            "message": f"Successfully transferred table {src_table.table_number} to {dest_table.table_number}.",
            "source_table": RestaurantTableSerializer(src_table, context={'request': request}).data,
            "destination_table": RestaurantTableSerializer(dest_table, context={'request': request}).data
        })

    @extend_schema(
        tags=['POS - Outlets & Floor Plan'],
        parameters=[OpenApiParameter(name='token', description='Table QR Code UUID Token', required=True, type=str)],
        responses={200: RestaurantTableSerializer},
        description="Lookup table metadata by its QR Code token for scan-and-order guest menu."
    )
    @action(detail=False, methods=['get'], url_path='by-qr-token')
    def by_qr_token(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({"error": "token query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            table = RestaurantTable.objects.select_related('section', 'section__outlet').get(qr_code_token=token, is_active=True, deleted_at__isnull=True)
        except (RestaurantTable.DoesNotExist, ValueError):
            return Response({"error": "Invalid or inactive QR code token."}, status=status.HTTP_404_NOT_FOUND)

        return Response(RestaurantTableSerializer(table, context={'request': request}).data)


@extend_schema_view(
    list=extend_schema(tags=['POS - Hardware & Terminals'], description="List all POS billing registers."),
    retrieve=extend_schema(tags=['POS - Hardware & Terminals'], description="Retrieve a specific POS register."),
    create=extend_schema(tags=['POS - Hardware & Terminals'], description="Create a new POS register."),
    update=extend_schema(tags=['POS - Hardware & Terminals'], description="Update a POS register."),
    partial_update=extend_schema(tags=['POS - Hardware & Terminals'], description="Partially update a POS register."),
    destroy=extend_schema(tags=['POS - Hardware & Terminals'], description="Soft-delete a POS register."),
)
class POSRegisterViewSet(viewsets.ModelViewSet):
    serializer_class = POSRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = POSRegister.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id') or self.request.headers.get('X-Outlet-ID')
        register_type = self.request.query_params.get('register_type')
        is_active = self.request.query_params.get('is_active')

        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if register_type:
            qs = qs.filter(register_type=register_type.upper())
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1'])

        return qs.select_related('outlet').prefetch_related('devices')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)


@extend_schema_view(
    list=extend_schema(tags=['POS - Hardware & Terminals'], description="List mapped physical devices."),
    retrieve=extend_schema(tags=['POS - Hardware & Terminals'], description="Retrieve a specific device mapping."),
    create=extend_schema(tags=['POS - Hardware & Terminals'], description="Pair and authorize a new hardware device."),
    update=extend_schema(tags=['POS - Hardware & Terminals'], description="Update device mapping."),
    partial_update=extend_schema(tags=['POS - Hardware & Terminals'], description="Partially update device mapping."),
    destroy=extend_schema(tags=['POS - Hardware & Terminals'], description="Unpair/delete device mapping."),
)
class DeviceMappingViewSet(viewsets.ModelViewSet):
    serializer_class = DeviceMappingSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = DeviceMapping.objects.filter(deleted_at__isnull=True)
        register_id = self.request.query_params.get('register_id')
        platform = self.request.query_params.get('platform')
        status_param = self.request.query_params.get('status')

        if register_id:
            qs = qs.filter(register_id=register_id)
        if platform:
            qs = qs.filter(platform=platform.upper())
        if status_param:
            qs = qs.filter(status=status_param.upper())

        return qs.select_related('register', 'register__outlet')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    @extend_schema(
        tags=['POS - Hardware & Terminals'],
        description="Register device heartbeat ping to maintain online connectivity status."
    )
    @action(detail=True, methods=['post'], url_path='heartbeat')
    def heartbeat(self, request, pk=None):
        device = self.get_object()
        device.last_heartbeat = timezone.now()
        device.status = 'ONLINE'
        device.save(update_fields=['last_heartbeat', 'status', 'updated_at'])
        return Response({"status": "ONLINE", "last_heartbeat": device.last_heartbeat})


class OccupiedRoomsAPIView(APIView):
    """
    Part 1 — POS Integrations: list PMS in-house (CHECKED_IN) rooms for Room Service.

    Read-only. Does not mutate reservations, rooms, or folios.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["POS - Integrations"],
        parameters=[
            OpenApiParameter(
                name="property_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Property UUID (also accepted via X-Property-ID header).",
            ),
            OpenApiParameter(
                name="tenant_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tenant UUID (also accepted via X-Tenant-ID header).",
            ),
            OpenApiParameter(
                name="X-Property-ID",
                type=str,
                location=OpenApiParameter.HEADER,
                required=False,
            ),
            OpenApiParameter(
                name="X-Tenant-ID",
                type=str,
                location=OpenApiParameter.HEADER,
                required=False,
            ),
        ],
        responses={200: OccupiedRoomsResponseSerializer},
        description=(
            "Return currently occupied hotel rooms (reservation status CHECKED_IN) "
            "with guest, pax, and open GuestFolio details for POS Room Service / Room Charge."
        ),
    )
    def get(self, request):
        property_id = (
            request.query_params.get("property_id")
            or request.headers.get("X-Property-ID")
        )
        tenant_id = (
            request.query_params.get("tenant_id")
            or request.headers.get("X-Tenant-ID")
        )

        if not property_id and not tenant_id:
            return Response(
                {
                    "detail": "property_id or tenant_id is required "
                    "(query param or X-Property-ID / X-Tenant-ID header).",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        rooms = OccupancyService.list_occupied_rooms(
            property_id=property_id,
            tenant_id=tenant_id,
        )
        payload = {"count": len(rooms), "rooms": rooms}
        serializer = OccupiedRoomsResponseSerializer(payload)
        return Response(serializer.data, status=status.HTTP_200_OK)


def _request_outlet_id(request):
    return (
        request.query_params.get("outlet_id")
        or request.query_params.get("outletId")
        or request.data.get("outlet_id")
        or request.data.get("outletId")
        or request.headers.get("X-Outlet-ID")
    )


@extend_schema_view(
    list=extend_schema(tags=["POS - Menu"], description="List POS tax profiles."),
    retrieve=extend_schema(tags=["POS - Menu"]),
    create=extend_schema(tags=["POS - Menu"]),
    update=extend_schema(tags=["POS - Menu"]),
    partial_update=extend_schema(tags=["POS - Menu"]),
    destroy=extend_schema(tags=["POS - Menu"]),
)
class TaxProfileViewSet(viewsets.ModelViewSet):
    serializer_class = TaxProfileSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = TaxProfile.objects.filter(deleted_at__isnull=True)
        tenant_id = self.request.query_params.get("tenant_id") or self.request.headers.get(
            "X-Tenant-ID"
        )
        property_id = self.request.query_params.get("property_id") or self.request.headers.get(
            "X-Property-ID"
        )
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


@extend_schema_view(
    list=extend_schema(tags=["POS - Menu"], description="List menu categories for an outlet."),
    retrieve=extend_schema(tags=["POS - Menu"]),
    create=extend_schema(tags=["POS - Menu"]),
    update=extend_schema(tags=["POS - Menu"]),
    partial_update=extend_schema(tags=["POS - Menu"]),
    destroy=extend_schema(tags=["POS - Menu"]),
)
class MenuCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = MenuCategorySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        outlet_id = _request_outlet_id(self.request)
        active = self.request.query_params.get("is_active")
        qs = MenuCatalogService.category_queryset(outlet_id=outlet_id)
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("true", "1"))
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(updated_by=user)


@extend_schema_view(
    list=extend_schema(
        tags=["POS - Menu"],
        description="List menu items (UI-shaped camelCase payload).",
        responses={200: MenuItemUISerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["POS - Menu"],
        responses={200: MenuItemUISerializer},
    ),
    create=extend_schema(tags=["POS - Menu"], request=MenuItemWriteSerializer),
    update=extend_schema(tags=["POS - Menu"], request=MenuItemWriteSerializer),
    partial_update=extend_schema(tags=["POS - Menu"], request=MenuItemWriteSerializer),
    destroy=extend_schema(tags=["POS - Menu"]),
)
class MenuItemViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        outlet_id = _request_outlet_id(self.request)
        active_only = self.request.query_params.get("active_only", "").lower() in (
            "true",
            "1",
        )
        return MenuCatalogService.item_queryset(
            outlet_id=outlet_id, active_only=active_only
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return MenuItemWriteSerializer
        return MenuItemUISerializer

    def list(self, request, *args, **kwargs):
        outlet_id = _request_outlet_id(request)
        active_only = request.query_params.get("active_only", "").lower() in ("true", "1")
        search = request.query_params.get("search") or request.query_params.get("q")
        category = request.query_params.get("category") or request.query_params.get(
            "category_id"
        )
        data = MenuCatalogService.list_items_ui(
            outlet_id=outlet_id,
            active_only=active_only,
            search=search,
            category=category,
        )
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        item = self.get_object()
        return Response(MenuCatalogService.serialize_item_ui(item))

    def create(self, request, *args, **kwargs):
        serializer = MenuItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        item = serializer.save(created_by=user, updated_by=user)
        return Response(
            MenuCatalogService.serialize_item_ui(item),
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        item = self.get_object()
        serializer = MenuItemWriteSerializer(item, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        item = serializer.save(updated_by=user)
        # Refresh with prefetches
        item = MenuCatalogService.item_queryset().filter(pk=item.pk).first()
        return Response(MenuCatalogService.serialize_item_ui(item))

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        instance.delete()

    @extend_schema(tags=["POS - Menu"], description="Toggle Active/Inactive status.")
    @action(detail=True, methods=["patch"], url_path="status")
    def toggle_status(self, request, pk=None):
        item = self.get_object()
        item.status = "INACTIVE" if item.status == "ACTIVE" else "ACTIVE"
        if item.status == "ACTIVE":
            item.next_available_at = None
        item.save(update_fields=["status", "next_available_at", "updated_at"])
        item = MenuCatalogService.item_queryset().filter(pk=item.pk).first()
        return Response(MenuCatalogService.serialize_item_ui(item))

    @extend_schema(
        tags=["POS - Menu"],
        description="Toggle channel flag: zomato|swiggy|direct|baseMenu|base_menu.",
    )
    @action(
        detail=True,
        methods=["patch"],
        url_path=r"platform/(?P<platform>[^/.]+)",
    )
    def toggle_platform(self, request, pk=None, platform=None):
        item = self.get_object()
        key = (platform or "").strip()
        mapping = {
            "zomato": "zomato",
            "swiggy": "swiggy",
            "direct": "direct",
            "basemenu": "base_menu",
            "base_menu": "base_menu",
            "baseMenu": "base_menu",
        }
        field = mapping.get(key) or mapping.get(key.lower())
        if not field:
            return Response(
                {"detail": "platform must be zomato, swiggy, direct, or baseMenu"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        setattr(item, field, not getattr(item, field))
        item.save(update_fields=[field, "updated_at"])
        item = MenuCatalogService.item_queryset().filter(pk=item.pk).first()
        return Response(MenuCatalogService.serialize_item_ui(item))

    @extend_schema(
        tags=["POS - Menu"],
        request=BulkPlatformUpdateSerializer,
        description="Bulk update platform availability flags.",
    )
    @action(detail=False, methods=["post"], url_path="bulk-platforms")
    def bulk_platforms(self, request):
        serializer = BulkPlatformUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data["ids"]
        updates = serializer.validated_data["updates"]
        field_map = {
            "zomato": "zomato",
            "swiggy": "swiggy",
            "direct": "direct",
            "baseMenu": "base_menu",
            "base_menu": "base_menu",
        }
        clean = {}
        for k, v in updates.items():
            if k in field_map and isinstance(v, bool):
                clean[field_map[k]] = v
        if not clean:
            return Response(
                {"detail": "No valid boolean platform updates provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = MenuItem.objects.filter(id__in=ids, deleted_at__isnull=True).update(
            **clean
        )
        return Response({"updated": updated})

    @extend_schema(tags=["POS - Menu"], description="Replace item images JSON array.")
    @action(detail=True, methods=["put", "patch"], url_path="images")
    def images(self, request, pk=None):
        item = self.get_object()
        images = request.data.get("images", request.data)
        if not isinstance(images, list):
            return Response(
                {"detail": "images must be a list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item.images = images
        item.save(update_fields=["images", "updated_at"])
        item = MenuCatalogService.item_queryset().filter(pk=item.pk).first()
        return Response(MenuCatalogService.serialize_item_ui(item))


@extend_schema_view(
    list=extend_schema(tags=["POS - Menu"]),
    retrieve=extend_schema(tags=["POS - Menu"]),
    create=extend_schema(tags=["POS - Menu"]),
    update=extend_schema(tags=["POS - Menu"]),
    partial_update=extend_schema(tags=["POS - Menu"]),
    destroy=extend_schema(tags=["POS - Menu"]),
)
class ModifierGroupViewSet(viewsets.ModelViewSet):
    serializer_class = ModifierGroupSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = ModifierGroup.objects.filter(deleted_at__isnull=True).prefetch_related(
            "options"
        )
        outlet_id = _request_outlet_id(self.request)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs


@extend_schema_view(
    list=extend_schema(tags=["POS - Menu"]),
    retrieve=extend_schema(tags=["POS - Menu"]),
    create=extend_schema(tags=["POS - Menu"]),
    update=extend_schema(tags=["POS - Menu"]),
    partial_update=extend_schema(tags=["POS - Menu"]),
    destroy=extend_schema(tags=["POS - Menu"]),
)
class SpecialNoteViewSet(viewsets.ModelViewSet):
    serializer_class = SpecialNoteSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = SpecialNote.objects.filter(deleted_at__isnull=True)
        outlet_id = _request_outlet_id(self.request)
        tenant_id = self.request.query_params.get("tenant_id") or self.request.headers.get(
            "X-Tenant-ID"
        )
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return qs


class BillingMenuCatalogAPIView(APIView):
    """Active billing catalog: categories + items for an outlet."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["POS - Menu"],
        description="Billing screen catalog (active items only).",
    )
    def get(self, request):
        outlet_id = _request_outlet_id(request)
        if not outlet_id:
            return Response(
                {"detail": "outlet_id (or outletId) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(MenuCatalogService.billing_catalog(outlet_id=outlet_id))


def _request_scope(request):
    scope = {
        "property_id": request.query_params.get("property_id")
        or request.headers.get("X-Property-ID")
        or (getattr(request, "data", {}) or {}).get("property_id")
        or (getattr(request, "data", {}) or {}).get("propertyId"),
        "tenant_id": request.query_params.get("tenant_id")
        or request.headers.get("X-Tenant-ID"),
        "outlet_id": _request_outlet_id(request),
    }
    if scope["outlet_id"] and not scope["property_id"]:
        row = (
            Outlet.objects.filter(id=scope["outlet_id"])
            .values("property_id", "tenant_id")
            .first()
        )
        if row:
            scope["property_id"] = row["property_id"]
            if not scope["tenant_id"]:
                scope["tenant_id"] = row["tenant_id"]
    return scope


def _report_dates(request):
    start = (
        request.query_params.get("start_date")
        or request.query_params.get("startDate")
        or request.query_params.get("from")
        or request.query_params.get("fromDate")
    )
    end = (
        request.query_params.get("end_date")
        or request.query_params.get("endDate")
        or request.query_params.get("to")
        or request.query_params.get("toDate")
    )
    try:
        return parse_iso_date(start), parse_iso_date(end)
    except ValueError:
        return None, None


@extend_schema_view(
    list=extend_schema(tags=["POS - Orders"], description="List POS orders."),
    retrieve=extend_schema(tags=["POS - Orders"]),
    create=extend_schema(
        tags=["POS - Orders"],
        request=POSOrderCreateSerializer,
        description="Create order and optionally send first KOT.",
    ),
    partial_update=extend_schema(
        tags=["POS - Orders"],
        request=POSOrderUpdateSerializer,
        description="Edit open order items (generates modified KOT).",
    ),
    destroy=extend_schema(tags=["POS - Orders"], description="Cancel an open order."),
)
class POSOrderViewSet(viewsets.ViewSet):
    """Part 3 — Orders + KOT lifecycle APIs."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def list(self, request):
        scope = _request_scope(request)
        status_filter = request.query_params.get("status")
        if status_filter and status_filter.upper() in ("PLACED", "PREPARED"):
            return Response(
                OrderService.list_current(
                    property_id=scope["property_id"],
                    outlet_id=scope["outlet_id"],
                    tenant_id=scope["tenant_id"],
                )
            )
        return Response(
            OrderService.list_history(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
                status=status_filter,
                search=request.query_params.get("search")
                or request.query_params.get("q"),
            )
        )

    def retrieve(self, request, pk=None):
        order = OrderService.order_queryset().filter(pk=pk).first()
        if not order:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(OrderService.serialize_order(order))

    def create(self, request):
        serializer = POSOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = OrderService.create_order(
                {**request.data, **serializer.validated_data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        serializer = POSOrderUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            payload = OrderService.update_order_items(
                pk, {**request.data, **serializer.validated_data}, user=request.user
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    def destroy(self, request, pk=None):
        try:
            payload = OrderService.cancel_order(
                pk, note=request.data.get("note", ""), user=request.user
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @extend_schema(tags=["POS - Orders"], description="Open orders (Current Orders).")
    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        scope = _request_scope(request)
        return Response(
            OrderService.list_current(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
            )
        )

    @extend_schema(tags=["POS - Orders"], description="Settled / cancelled order history.")
    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        scope = _request_scope(request)
        return Response(
            OrderService.list_history(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
                status=request.query_params.get("status"),
                search=request.query_params.get("search")
                or request.query_params.get("q"),
            )
        )

    @extend_schema(tags=["POS - Orders"], description="Live / current orders summary.")
    @action(detail=False, methods=["get"], url_path="live")
    def live(self, request):
        scope = _request_scope(request)
        return Response(
            OrderService.live_summary(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
            )
        )

    @extend_schema(
        tags=["POS - Orders"],
        description="Alias of history for UI `/api/pos/orders/all`.",
    )
    @action(detail=False, methods=["get"], url_path="all")
    def all_orders(self, request):
        return self.history(request)

    @extend_schema(tags=["POS - Orders"], description="Send / re-send KOT for an order.")
    @action(detail=True, methods=["post"], url_path="kot")
    def kot(self, request, pk=None):
        try:
            payload = OrderService.send_kot(
                pk, notes=request.data.get("notes"), user=request.user
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["POS - Orders"],
        description="Advance PLACED → PREPARED (KDS / Current Orders).",
    )
    @action(detail=True, methods=["post"], url_path="advance-stage")
    def advance_stage(self, request, pk=None):
        try:
            payload = OrderService.advance_stage(pk, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @extend_schema(
        tags=["POS - Orders"],
        request=POSOrderSettleSerializer,
        description=(
            "Settle order with CASH/CARD/UPI/ROOM_CHARGE/SPLIT/DUE. "
            "ROOM_CHARGE posts to PMS GuestFolio (idempotent)."
        ),
    )
    @action(detail=True, methods=["post"], url_path="settle")
    def settle(self, request, pk=None):
        serializer = POSOrderSettleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = OrderService.settle_order(
                pk, {**request.data, **serializer.validated_data}, user=request.user
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @extend_schema(
        tags=["POS - Orders"],
        description="Pending Payments / due settlement list.",
    )
    @action(detail=False, methods=["get"], url_path="due-settlement")
    def due_settlement(self, request):
        scope = _request_scope(request)
        rows = DueLedgerService.list_dues(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
            include_settled=request.query_params.get("include_settled", "").lower()
            in ("1", "true"),
        )
        return Response(
            {
                "success": True,
                "count": len(rows),
                "totalDue": float(sum(r["dueAmount"] for r in rows)),
                "bills": rows,
            }
        )

    @extend_schema(
        tags=["POS - Orders"],
        request=POSDueSettleSerializer,
        description="Collect payment against a due bill.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path=r"due-settlement/(?P<bill_id>[^/.]+)/settle",
    )
    def settle_due_bill(self, request, bill_id=None):
        serializer = POSDueSettleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = DueLedgerService.settle_due(
                bill_id,
                {**request.data, **serializer.validated_data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True, "settledBill": payload, **payload})

    @extend_schema(tags=["POS - Orders"], description="CSV export of order history.")
    @action(detail=False, methods=["get"], url_path="history/export")
    def history_export(self, request):
        scope = _request_scope(request)
        csv_data = ExportService.orders_history_csv(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
        )
        resp = HttpResponse(csv_data, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="pos_order_history.csv"'
        return resp

    @extend_schema(tags=["POS - Orders"], description="CSV export of open due bills.")
    @action(detail=False, methods=["get"], url_path="due-settlement/export")
    def due_export(self, request):
        scope = _request_scope(request)
        csv_data = ExportService.dues_csv(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
        )
        resp = HttpResponse(csv_data, content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="pos_due_settlement.csv"'
        return resp


class KOTListAPIView(APIView):
    """Kitchen display list of open KOT tickets."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["POS - Orders"], description="List active KOT tickets.")
    def get(self, request):
        scope = _request_scope(request)
        return Response(
            OrderService.list_kot(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                status=request.query_params.get("status"),
            )
        )


class KOTTicketReadyAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["POS - Orders"], description="Chef marks a KOT ticket ready.")
    def post(self, request, pk=None):
        try:
            payload = OrderService.mark_ticket_ready(pk, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class KOTTicketServedAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(tags=["POS - Orders"], description="Waiter marks a KOT ticket served.")
    def post(self, request, pk=None):
        try:
            payload = OrderService.mark_ticket_served(pk, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class DayEndSummaryAPIView(APIView):
    """Part 5 — day-end summary list / detail."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Reports"], description="Day-end summary by date.")
    def get(self, request):
        scope = _request_scope(request)
        start = request.query_params.get("start_date") or request.query_params.get(
            "startDate"
        )
        end = request.query_params.get("end_date") or request.query_params.get("endDate")
        business_date = request.query_params.get("business_date") or request.query_params.get(
            "businessDate"
        )

        def _parse(d):
            if not d:
                return None
            return datetime.strptime(d, "%Y-%m-%d").date()

        if business_date:
            detail = DayCloseService.day_detail(
                business_date=_parse(business_date),
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
            )
            return Response(detail)

        payload = DayCloseService.summarize_range(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
            start_date=_parse(start),
            end_date=_parse(end),
        )
        return Response(payload)


class DayEndCloseAPIView(APIView):
    """Close a business date and store snapshot."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Reports"], description="Close POS day and store totals.")
    def post(self, request):
        scope = _request_scope(request)
        business_date = request.data.get("business_date") or request.data.get(
            "businessDate"
        )
        if not business_date:
            return Response(
                {"detail": "business_date is required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not scope["property_id"]:
            return Response(
                {"detail": "property_id or outlet_id is required to close the day."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            d = datetime.strptime(business_date, "%Y-%m-%d").date()
            payload = DayCloseService.close_day(
                business_date=d,
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"]
                or request.data.get("outlet_id")
                or request.data.get("outletId"),
                tenant_id=scope["tenant_id"],
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response(
                {"detail": "business_date must be YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_201_CREATED)


class StockItemAPIView(APIView):
    """Part 6 — list / create POS stock SKUs."""

    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Stock"], description="List stock items.")
    def get(self, request):
        scope = _request_scope(request)
        return Response(
            {
                "success": True,
                "items": StockService.list_stock(
                    property_id=scope["property_id"],
                    outlet_id=scope["outlet_id"],
                    tenant_id=scope["tenant_id"],
                    search=request.query_params.get("search"),
                    item_kind=request.query_params.get("itemKind") or request.query_params.get("item_kind"),
                    category=request.query_params.get("category"),
                ),
            }
        )

    @extend_schema(tags=["POS - Stock"], description="Create or update stock item by code.")
    def post(self, request):
        try:
            payload = StockService.upsert_stock(
                {**_request_scope(request), **request.data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class StockItemDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Stock"], description="Get one stock SKU.")
    def get(self, request, pk=None):
        try:
            return Response(StockService.get_item(pk))
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(tags=["POS - Stock"], description="Update a stock SKU.")
    def patch(self, request, pk=None):
        try:
            return Response(
                StockService.update_item(pk, {**_request_scope(request), **request.data}, user=request.user)
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(tags=["POS - Stock"], description="Soft-delete a stock SKU.")
    def delete(self, request, pk=None):
        if not StockService.delete_item(pk, user=request.user):
            return Response({"detail": "Stock item not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True})


class StockAdjustAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Stock"], description="Adjust / in / out / wastage stock.")
    def post(self, request, pk=None):
        movement = (
            request.data.get("movement_type")
            or request.data.get("movementType")
            or "ADJUST"
        ).upper()
        qty = request.data.get("quantity")
        if qty is None:
            return Response(
                {"detail": "quantity is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            payload = StockService.adjust_stock(
                pk,
                quantity=Decimal(str(qty)),
                movement_type=movement,
                notes=request.data.get("notes") or "",
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class RecipeListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Stock"], description="List dish recipes.")
    def get(self, request):
        scope = _request_scope(request)
        recipes = StockService.list_recipes(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
            search=request.query_params.get("search"),
        )
        return Response({"success": True, "recipes": recipes})

    @extend_schema(tags=["POS - Stock"], description="Create a dish recipe BOM.")
    def post(self, request):
        try:
            payload = StockService.save_recipe(
                {**_request_scope(request), **request.data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class RecipeAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Stock"], description="Get recipe BOM by recipe id or menu item id.")
    def get(self, request, menu_item_id=None):
        try:
            return Response(StockService.get_recipe(menu_item_id))
        except ValidationError:
            return Response({"detail": "Recipe not found."}, status=status.HTTP_404_NOT_FOUND)

    @extend_schema(tags=["POS - Stock"], description="Create/replace recipe BOM.")
    def put(self, request, menu_item_id=None):
        data = {**_request_scope(request), **request.data}
        try:
            existing = StockService.get_recipe(menu_item_id)
            data["id"] = existing["id"]
        except ValidationError:
            data["menuItemId"] = str(menu_item_id)
        try:
            payload = StockService.save_recipe(data, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @extend_schema(tags=["POS - Stock"], description="Delete a dish recipe.")
    def delete(self, request, menu_item_id=None):
        if not StockService.delete_recipe(menu_item_id, user=request.user):
            return Response({"detail": "Recipe not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True})


class SalesReportAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["POS - Reports"],
        description="Settled sales reports. kind=items|overview|daywise|hourly|payments|invoices|biller|channels|discounts|category|customers|gst|dashboard.",
    )
    def get(self, request):
        scope = _request_scope(request)
        start, end = _report_dates(request)
        kind = (
            request.query_params.get("kind")
            or request.query_params.get("reportId")
            or "items"
        )
        try:
            limit = int(request.query_params.get("limit") or 200)
        except (TypeError, ValueError):
            limit = 200
        return Response(
            SalesAnalyticsService.run(
                kind=kind,
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
                start_date=start,
                end_date=end,
                limit=limit,
            )
        )


class StockReportAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Reports"], description="Stock on-hand + low-stock list.")
    def get(self, request):
        scope = _request_scope(request)
        return Response(
            ReportService.stock_report(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
            )
        )


class ConsumptionReportAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Reports"], description="Stock consumed via order settles.")
    def get(self, request):
        scope = _request_scope(request)
        start, end = _report_dates(request)
        return Response(
            ReportService.consumption_report(
                property_id=scope["property_id"],
                outlet_id=scope["outlet_id"],
                tenant_id=scope["tenant_id"],
                start_date=start,
                end_date=end,
            )
        )


class AggregatorWebhookAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        tags=["POS - Integrations"],
        description="Stub webhook receiver for Zomato/Swiggy (audit log only).",
    )
    def post(self, request):
        payload = AggregatorWebhookService.receive(
            {**request.data, **_request_scope(request)},
            user=request.user,
        )
        return Response(payload, status=status.HTTP_202_ACCEPTED)


class ProductionRecipeListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Food Preparation"], description="List food preparation / production recipes.")
    def get(self, request):
        scope = _request_scope(request)
        category = request.query_params.get("category")
        search = request.query_params.get("search")
        recipes = ProductionService.list_recipes(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
            category=category,
            search=search,
        )
        return Response({"success": True, "recipes": recipes})

    @extend_schema(tags=["POS - Food Preparation"], description="Create new food preparation recipe.")
    def post(self, request):
        scope = _request_scope(request)
        try:
            payload = ProductionService.save_recipe(
                {**scope, **request.data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class ProductionRecipeDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Food Preparation"], description="Update food preparation recipe.")
    def put(self, request, pk=None):
        scope = _request_scope(request)
        try:
            payload = ProductionService.save_recipe(
                {**scope, **request.data, "id": str(pk)},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @extend_schema(tags=["POS - Food Preparation"], description="Delete food preparation recipe.")
    def delete(self, request, pk=None):
        deleted = ProductionService.delete_recipe(pk, user=request.user)
        if not deleted:
            return Response({"detail": "Recipe not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True, "detail": "Recipe deleted successfully."})


class ProductionBatchListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Food Preparation"], description="List food preparation batches.")
    def get(self, request):
        scope = _request_scope(request)
        status_val = request.query_params.get("status")
        search = request.query_params.get("search")
        batches = ProductionService.list_batches(
            property_id=scope["property_id"],
            outlet_id=scope["outlet_id"],
            tenant_id=scope["tenant_id"],
            status=status_val,
            search=search,
        )
        return Response({"success": True, "batches": batches})

    @extend_schema(tags=["POS - Food Preparation"], description="Log and execute new food preparation batch.")
    def post(self, request):
        scope = _request_scope(request)
        try:
            payload = ProductionService.create_batch(
                {**scope, **request.data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class ProductionBatchDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Food Preparation"], description="Update food preparation batch status.")
    def patch(self, request, pk=None):
        new_status = request.data.get("status")
        if not new_status:
            return Response({"detail": "status is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = ProductionService.update_batch_status(
                pk,
                status=new_status,
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class PurchaseListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Purchases"], description="List purchases with date range and payment status.")
    def get(self, request):
        scope = _request_scope(request)
        start_date = request.query_params.get("start_date") or request.query_params.get("startDate")
        end_date = request.query_params.get("end_date") or request.query_params.get("endDate")
        vendor = request.query_params.get("vendor")
        payment_status = request.query_params.get("payment_status") or request.query_params.get("paymentStatus")
        search = request.query_params.get("search")

        purchases = PurchaseService.list_purchases(
            property_id=scope["property_id"],
            tenant_id=scope["tenant_id"],
            outlet_id=scope["outlet_id"],
            start_date=start_date,
            end_date=end_date,
            vendor=vendor,
            payment_status=payment_status,
            search=search,
        )
        return Response({"success": True, "purchases": purchases})

    @extend_schema(tags=["POS - Purchases"], description="Record incoming purchase bill and adjust inventory.")
    def post(self, request):
        scope = _request_scope(request)
        try:
            payload = PurchaseService.create_purchase(
                {**scope, **request.data},
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class PurchaseDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Purchases"], description="Delete / cancel purchase invoice.")
    def delete(self, request, pk=None):
        deleted = PurchaseService.delete_purchase(pk, user=request.user)
        if not deleted:
            return Response({"detail": "Purchase invoice not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True, "detail": "Purchase invoice deleted."})


class PurchaseRecordPaymentAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Purchases"], description="Record payment for a purchase invoice.")
    def post(self, request, pk=None):
        amount = request.data.get("amount")
        if not amount:
            return Response({"detail": "amount is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = PurchaseService.record_payment(
                pk,
                amount=amount,
                payment_method=request.data.get("paymentMethod") or request.data.get("payment_method") or "CASH",
                reference_no=request.data.get("referenceNo") or request.data.get("reference_no") or "",
                notes=request.data.get("notes") or "",
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class POSVendorListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Purchases"], description="List all vendors or suppliers.")
    def get(self, request):
        scope = _request_scope(request)
        search = request.query_params.get("search") or request.query_params.get("q")
        vendors = PurchaseService.list_vendors(
            property_id=scope["property_id"],
            tenant_id=scope["tenant_id"],
            search=search,
        )
        return Response({"success": True, "vendors": vendors})

    @extend_schema(tags=["POS - Purchases"], description="Create a new vendor or supplier.")
    def post(self, request):
        scope = _request_scope(request)
        try:
            vendor = PurchaseService.create_vendor(
                request.data,
                property_id=scope["property_id"],
                tenant_id=scope["tenant_id"],
                user=request.user,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True, "vendor": vendor}, status=status.HTTP_201_CREATED)


class POSVendorDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(tags=["POS - Purchases"], description="Remove / delete a vendor.")
    def delete(self, request, pk=None):
        deleted = PurchaseService.delete_vendor(pk, user=request.user)
        if not deleted:
            return Response({"detail": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True, "detail": "Vendor removed."})


class StockMovementListAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response(
            {
                "success": True,
                "movements": StockService.list_movements(
                    property_id=scope["property_id"],
                    outlet_id=scope["outlet_id"],
                    tenant_id=scope["tenant_id"],
                    stock_item_id=request.query_params.get("stockItemId") or request.query_params.get("stock_item_id"),
                    movement_type=request.query_params.get("type") or request.query_params.get("movement_type"),
                    start_date=request.query_params.get("from") or request.query_params.get("startDate"),
                    end_date=request.query_params.get("to") or request.query_params.get("endDate"),
                ),
            }
        )


class StockOverviewAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response(StockService.overview(**scope))


class StockAlertsAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "alerts": StockService.alerts(**scope)})


class StockSettingsAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "settings": StockService.get_inventory_settings(scope["outlet_id"])})

    def put(self, request):
        scope = _request_scope(request)
        try:
            settings = StockService.save_inventory_settings(
                {**request.data},
                outlet_id=scope["outlet_id"] or request.data.get("outletId"),
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True, "settings": settings})


class StockUnitListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "units": StockService.list_units(property_id=scope["property_id"], tenant_id=scope["tenant_id"])})

    def post(self, request):
        try:
            return Response(
                StockService.save_unit({**_request_scope(request), **request.data}, user=request.user),
                status=status.HTTP_201_CREATED,
            )
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)


class StockUnitDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def patch(self, request, pk=None):
        try:
            return Response(StockService.save_unit({**_request_scope(request), **request.data, "id": str(pk)}, user=request.user))
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk=None):
        if not StockService.delete_unit(pk):
            return Response({"detail": "Unit not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True})


class WastageListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "items": StockService.list_wastage(**scope)})

    def post(self, request):
        try:
            payload = StockService.create_wastage({**_request_scope(request), **request.data}, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class WastageDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk=None):
        if not StockService.delete_wastage(pk, user=request.user):
            return Response({"detail": "Wastage entry not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True})


class ClosingStockAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        raw = request.query_params.get("date") or request.query_params.get("business_date")
        if not raw:
            raw = timezone.now().date().isoformat()
        try:
            d = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return Response({"detail": "date must be YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockService.get_closing(business_date=d, **scope))

    def post(self, request):
        try:
            payload = StockService.save_closing({**_request_scope(request), **request.data}, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class PurchaseOrderListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "purchaseOrders": PurchaseService.list_purchase_orders(**scope)})

    def post(self, request):
        try:
            payload = PurchaseService.create_purchase_order({**_request_scope(request), **request.data}, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class PurchaseOrderDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk=None):
        try:
            if not PurchaseService.delete_purchase_order(pk):
                return Response({"detail": "Purchase order not found."}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response({"success": True})


class PurchaseOrderReceiveAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, pk=None):
        try:
            payload = PurchaseService.receive_purchase_order(pk, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


class PurchaseReturnListCreateAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        scope = _request_scope(request)
        return Response({"success": True, "purchaseReturns": PurchaseService.list_purchase_returns(**scope)})

    def post(self, request):
        try:
            payload = PurchaseService.create_purchase_return({**_request_scope(request), **request.data}, user=request.user)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_201_CREATED)


class PurchaseReturnDetailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def delete(self, request, pk=None):
        if not PurchaseService.delete_purchase_return(pk, user=request.user):
            return Response({"detail": "Purchase return not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"success": True})

