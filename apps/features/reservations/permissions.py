from rest_framework import permissions
from apps.core.rbac.models import UserPropertyRole

class HasReservationPermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for the resolved property context.
    Superusers bypass checking.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        # Fallback mapping based on standard REST framework view actions
        if view.action in ['list', 'retrieve', 'search', 'timeline']:
            return 'reservations.view'
        elif view.action == 'create':
            return 'reservations.create'
        elif view.action in ['update', 'partial_update', 'modify_remarks']:
            return 'reservations.edit'
        elif view.action == 'destroy':
            return 'reservations.delete'
        elif view.action == 'assign_room':
            return 'reservations.assign_room'
        elif view.action == 'check_in':
            return 'reservations.check_in'
        elif view.action == 'check_out':
            return 'reservations.check_out'
        elif view.action == 'cancel':
            return 'reservations.cancel'
        
        return 'reservations.view'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        perm_code = self.get_required_permission(request, view)
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        # Check for property ID in request context
        property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')
        if not property_id:
            property_id = view.kwargs.get('property_id')
        
        # If no property context is given, allow operations if authorized for ANY property under the tenant
        if not property_id:
            user_roles = UserPropertyRole.objects.filter(user=request.user, tenant=tenant)
            for ur in user_roles:
                if 'owner' in ur.role.name.lower():
                    return True
                if ur.role.permissions.filter(permission__code=perm_code).exists():
                    return True
            return False

        # Specific property checks
        user_property_role = UserPropertyRole.objects.filter(
            user=request.user,
            property_id=property_id,
            tenant=tenant
        ).first()

        if not user_property_role:
            return False

        if 'owner' in user_property_role.role.name.lower():
            return True

        return user_property_role.role.permissions.filter(permission__code=perm_code).exists()
