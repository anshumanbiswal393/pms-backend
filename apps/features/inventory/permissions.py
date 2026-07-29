from rest_framework import permissions
from apps.core.rbac.utils import check_user_permission

class HasInventoryPermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for inventory, rooms, and attributes.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        if view.action in ['list', 'retrieve']:
            return ['inventory.view', 'rooms.view']
        elif view.action == 'create':
            return ['inventory.create', 'rooms.create']
        elif view.action in ['update', 'partial_update']:
            return ['inventory.edit', 'rooms.edit']
        elif view.action == 'destroy':
            return ['inventory.delete', 'rooms.delete']
        
        return ['inventory.view', 'rooms.view']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        perm_codes = self.get_required_permission(request, view)

        property_id = None
        if request.method in ['POST', 'PUT', 'PATCH'] and hasattr(request.data, 'get'):
            property_id = request.data.get('property_id') or request.data.get('property')
            
        if not property_id:
            property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')
        if not property_id:
            property_id = view.kwargs.get('property_id')

        return check_user_permission(request.user, tenant, perm_codes, property_id=property_id)



class IsAmenityManager(HasInventoryPermission):
    def get_required_permission(self, request, view):
        return 'amenity.manage'


class IsAttributeManager(HasInventoryPermission):
    def get_required_permission(self, request, view):
        return 'attribute.manage'


class CanCloneInventoryType(HasInventoryPermission):
    def get_required_permission(self, request, view):
        return 'inventory_type.clone'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        pk = view.kwargs.get('pk')
        if not pk:
            return False

        from apps.features.inventory.models import InventoryUnitType
        try:
            source = InventoryUnitType.objects.all_with_deleted().get(id=pk)
            if source.tenant != tenant:
                return False
            property_id = source.property_id
        except Exception:
            return False

        user_property_role = UserPropertyRole.objects.filter(
            user=request.user,
            property_id=property_id,
            tenant=tenant
        ).first()

        if not user_property_role:
            return False

        return user_property_role.role.permissions.filter(permission__code='inventory_type.clone').exists()
