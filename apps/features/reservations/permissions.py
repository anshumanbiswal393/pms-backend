from rest_framework import permissions
from apps.core.rbac.utils import check_user_permission

class HasReservationPermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for reservations under the tenant/property context.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        if view.action in ['list', 'retrieve', 'search', 'timeline']:
            return ['reservations.view', 'reservations:view']
        elif view.action == 'create':
            return ['reservations.create', 'reservations:create']
        elif view.action in ['update', 'partial_update', 'modify_remarks']:
            return ['reservations.edit', 'reservations:edit', 'reservations:update']
        elif view.action == 'destroy':
            return ['reservations.delete', 'reservations:delete']
        elif view.action in ['assign_room', 'check_in', 'check_out', 'cancel']:
            return ['reservations.edit', 'reservations.view', 'reservations.create', 'reservations:checkin', 'reservations:checkout']
        
        return ['reservations.view', 'reservations:view']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False):
            return True

        # Tenant Owner / Director has full master access
        if request.user.role and getattr(request.user.role, 'code', '') in ['owner', 'tenant_owner', 'super_admin']:
            return True

        tenant = getattr(request.user, 'tenant', None) or getattr(request, 'tenant', None)
        if not tenant:
            return False

        perm_codes = self.get_required_permission(request, view)

        # Property ID context
        property_id = request.headers.get('X-Property-ID') or (getattr(request, 'query_params', {}).get('property_id') if hasattr(request, 'query_params') else None)
        if not property_id:
            property_id = view.kwargs.get('property_id')

        return check_user_permission(request.user, tenant, perm_codes, property_id=property_id)
