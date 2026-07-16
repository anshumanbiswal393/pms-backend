from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from apps.features.inventory.models import (
    InventoryUnitCategory, InventoryUnitType, InventoryUnit,
    InventoryRelationship, AttributeDefinition, InventoryUnitAttribute,
    Amenity, InventoryUnitTypeAmenity, InventoryMedia,
    Building, Floor, FloorPlan
)
from apps.features.inventory.serializers import (
    InventoryUnitCategorySerializer, InventoryUnitTypeSerializer, InventoryUnitSerializer,
    InventoryRelationshipSerializer, AttributeDefinitionSerializer, InventoryUnitAttributeSerializer,
    AmenitySerializer, InventoryUnitTypeAmenitySerializer, InventoryMediaSerializer,
    BuildingSerializer, FloorSerializer, FloorPlanSerializer
)
from apps.features.inventory.filters import (
    InventoryUnitCategoryFilter, InventoryUnitTypeFilter, InventoryUnitFilter,
    InventoryRelationshipFilter, AttributeDefinitionFilter, InventoryUnitAttributeFilter,
    AmenityFilter, InventoryUnitTypeAmenityFilter, InventoryMediaFilter,
    BuildingFilter, FloorFilter, FloorPlanFilter
)
from apps.features.inventory.permissions import (
    HasInventoryPermission, IsAmenityManager, IsAttributeManager, CanCloneInventoryType
)
from apps.core.common.mixins import RedisCacheMixin

class InventoryUnitCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryUnitCategorySerializer
    filterset_class = InventoryUnitCategoryFilter
    search_fields = ['code', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [HasInventoryPermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryUnitCategory.objects.filter(tenant__isnull=True)
        return InventoryUnitCategory.objects.filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class InventoryUnitTypeViewSet(RedisCacheMixin, viewsets.ModelViewSet):
    serializer_class = InventoryUnitTypeSerializer
    filterset_class = InventoryUnitTypeFilter
    search_fields = ['code', 'name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [HasInventoryPermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryUnitType.objects.none()
        return InventoryUnitType.objects.filter(tenant=tenant)

    @action(detail=True, methods=['post'], permission_classes=[CanCloneInventoryType])
    def clone(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=status.HTTP_400_BAD_REQUEST)

        source = InventoryUnitType.objects.all_with_deleted().filter(id=pk, tenant=tenant).first()
        if not source:
            return Response({'error': 'Source inventory type not found.'}, status=status.HTTP_404_NOT_FOUND)

        if source.status != 'ACTIVE':
            return Response({'error': 'Cannot clone inactive inventory type.'}, status=status.HTTP_400_BAD_REQUEST)

        name = request.data.get('name')
        code = request.data.get('code')
        clone_media = request.data.get('clone_media', False)
        if not name or not code:
            return Response({'error': 'name and code are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if InventoryUnitType.objects.filter(property=source.property, code=code).exists():
            return Response({'error': f"Inventory type with code '{code}' already exists in this property."}, status=status.HTTP_400_BAD_REQUEST)

        if InventoryUnitType.objects.filter(property=source.property, name=name).exists():
            return Response({'error': f"Inventory type with name '{name}' already exists in this property."}, status=status.HTTP_400_BAD_REQUEST)

        from apps.features.inventory.services import InventoryTypeCloneService
        try:
            new_type, amenities_copied, attributes_copied, media_copied = InventoryTypeCloneService.clone_inventory_type(source, name, code, clone_media=clone_media)
        except Exception as e:
            return Response({'error': f"Cloning failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate Audit Event INVENTORY_TYPE_CLONED
        from apps.core.audit.models import AuditLog
        from django.utils import timezone
        try:
            from apps.core.rbac.models import UserPropertyRole
            actor_role = 'SYSTEM'
            if request.user.is_superuser:
                actor_role = 'super_admin'
            else:
                upr = UserPropertyRole.objects.filter(user=request.user, property=source.property, tenant=tenant).first()
                if upr:
                    actor_role = upr.role.code

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

            # Calculate clone_depth
            prev_audit = AuditLog.objects.filter(action_type='INVENTORY_TYPE_CLONED', target_id=str(source.id)).first()
            clone_depth = (prev_audit.payload_after.get('clone_depth', 1) + 1) if (prev_audit and prev_audit.payload_after) else 1

            AuditLog.objects.create(
                tenant=tenant,
                property=source.property,
                actor_user=request.user,
                actor_name=request.user.name,
                actor_role_code=actor_role,
                action_type='INVENTORY_TYPE_CLONED',
                target_entity='InventoryUnitType',
                target_id=str(new_type.id),
                payload_after={
                    "source_inventory_type_id": str(source.id),
                    "new_inventory_type_id": str(new_type.id),
                    "source_name": source.name,
                    "new_name": new_type.name,
                    "cloned_by": str(request.user.id),
                    "timestamp": timezone.now().isoformat(),
                    "clone_depth": clone_depth
                },
                ip_address=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
                request_id=getattr(request, 'request_id', None)
            )
        except Exception as e:
            import sys
            print(f"FAILED TO WRITE CLONE AUDIT LOG: {e}", file=sys.stderr)

        return Response({
            'id': str(new_type.id),
            'name': new_type.name,
            'code': new_type.code,
            'amenities_copied': amenities_copied,
            'attributes_copied': attributes_copied,
            'media_copied': media_copied,
            'status': 'ACTIVE'
        }, status=status.HTTP_201_CREATED)


class InventoryUnitViewSet(RedisCacheMixin, viewsets.ModelViewSet):
    serializer_class = InventoryUnitSerializer
    filterset_class = InventoryUnitFilter
    search_fields = ['code', 'name']
    pagination_class = None
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'bulk_update']:
            return [permissions.IsAuthenticated()]
        return [HasInventoryPermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryUnit.objects.none()
        return InventoryUnit.objects.filter(tenant=tenant)


class InventoryRelationshipViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryRelationshipSerializer
    permission_classes = [HasInventoryPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryRelationship.objects.none()
        return InventoryRelationship.objects.filter(tenant=tenant)


class AttributeDefinitionViewSet(viewsets.ModelViewSet):
    serializer_class = AttributeDefinitionSerializer
    permission_classes = [IsAttributeManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return AttributeDefinition.objects.filter(tenant__isnull=True)
        return AttributeDefinition.objects.filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class InventoryUnitAttributeViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryUnitAttributeSerializer
    permission_classes = [IsAttributeManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryUnitAttribute.objects.none()
        return InventoryUnitAttribute.objects.filter(tenant=tenant)


class AmenityViewSet(viewsets.ModelViewSet):
    serializer_class = AmenitySerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsAmenityManager()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Amenity.objects.filter(tenant__isnull=True)
        return Amenity.objects.filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class InventoryMediaViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryMediaSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'upload']:
            return [permissions.IsAuthenticated()]
        return [HasInventoryPermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return InventoryMedia.objects.none()
        return InventoryMedia.objects.filter(tenant=tenant)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=status.HTTP_400_BAD_REQUEST)
        
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file was provided.'}, status=status.HTTP_400_BAD_REQUEST)
            
        unit_type_id = request.data.get('inventory_unit_type')
        if not unit_type_id:
            return Response({'error': 'inventory_unit_type is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        from django.core.files.storage import default_storage
        import os
        import uuid
        
        # Save file to media/inventory/ with a unique name to avoid collision
        ext = os.path.splitext(file_obj.name)[1]
        unique_filename = f"inventory/{uuid.uuid4()}{ext}"
        saved_path = default_storage.save(unique_filename, file_obj)
        file_url = request.build_absolute_uri(default_storage.url(saved_path))
        
        # Create media record (or update existing)
        existing = InventoryMedia.objects.filter(tenant=tenant, inventory_unit_type_id=unit_type_id).first()
        if existing:
            existing.media_url = file_url
            existing.save()
            media = existing
        else:
            media = InventoryMedia.objects.create(
                tenant=tenant,
                inventory_unit_type_id=unit_type_id,
                media_url=file_url,
                media_type='image'
            )
            
        return Response(InventoryMediaSerializer(media, context={'request': request}).data, status=status.HTTP_201_CREATED)


class BuildingViewSet(viewsets.ModelViewSet):
    serializer_class = BuildingSerializer
    permission_classes = [HasInventoryPermission]
    filterset_fields = ['property']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Building.objects.none()
        
        # Optional filter by property
        property_id = self.request.query_params.get('property') or self.request.query_params.get('property_id')
        qs = Building.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs


class FloorViewSet(viewsets.ModelViewSet):
    serializer_class = FloorSerializer
    permission_classes = [HasInventoryPermission]
    filterset_fields = ['building']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Floor.objects.none()

        building_id = self.request.query_params.get('building') or self.request.query_params.get('building_id')
        qs = Floor.objects.filter(building__tenant=tenant)
        if building_id:
            qs = qs.filter(building_id=building_id)
        return qs


class FloorPlanViewSet(viewsets.ModelViewSet):
    serializer_class = FloorPlanSerializer
    permission_classes = [HasInventoryPermission]
    filterset_fields = ['floor']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return FloorPlan.objects.none()

        floor_id = self.request.query_params.get('floor') or self.request.query_params.get('floor_id')
        qs = FloorPlan.objects.filter(floor__building__tenant=tenant)
        if floor_id:
            qs = qs.filter(floor_id=floor_id)
        return qs

