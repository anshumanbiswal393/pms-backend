from rest_framework import permissions
from apps.core.rbac.utils import check_user_permission

class HasAvailabilityPermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for room availability and holds.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        if view.action in ['list', 'retrieve', 'calendar']:
            return ['availability.view', 'reservations.view', 'rooms.view']
        elif view.action in ['create', 'bulk_update']:
            return ['availability.create', 'reservations.create']
        elif view.action in ['update', 'partial_update']:
            return ['availability.edit', 'reservations.edit']
        elif view.action == 'destroy':
            return ['availability.delete', 'reservations.delete']
        
        return ['availability.view', 'reservations.view', 'rooms.view']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        perm_codes = self.get_required_permission(request, view)

        property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')
        if not property_id:
            property_id = view.kwargs.get('property_id')
        if not property_id and isinstance(request.data, dict):
            property_id = request.data.get('property_id') or request.data.get('property')

        return check_user_permission(request.user, tenant, perm_codes, property_id=property_id)



class IsRestrictionManager(HasAvailabilityPermission):
    def get_required_permission(self, request, view):
        # Map to rates.edit or settings.edit since restrictions are set on rates/inventory
        return 'rates.edit'


class IsHoldManager(HasAvailabilityPermission):
    def get_required_permission(self, request, view):
        # Map to reservations.create/edit since holds block inventory for reservations
        return 'reservations.create'
