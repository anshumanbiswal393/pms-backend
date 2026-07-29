from rest_framework import permissions
from apps.core.rbac.utils import check_user_permission

class HasGuestPermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for guest profiles and CRM data.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        if view.action in ['list', 'retrieve', 'search', 'activities', 'active']:
            return ['guests.view', 'reservations.view']
        elif view.action == 'create':
            return ['guests.create', 'reservations.create']
        elif view.action in ['update', 'partial_update']:
            return ['guests.edit', 'reservations.edit']
        elif view.action == 'destroy':
            return ['guests.delete', 'reservations.delete']
        
        return ['guests.view', 'reservations.view']

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

        return check_user_permission(request.user, tenant, perm_codes, property_id=property_id)



class IsMergeManager(HasGuestPermission):
    def get_required_permission(self, request, view):
        return 'guest.merge'


class IsVerifyDocumentManager(HasGuestPermission):
    def get_required_permission(self, request, view):
        return 'guest.verify_document'


class IsLoyaltyManager(HasGuestPermission):
    def get_required_permission(self, request, view):
        return 'guest.manage_loyalty'


class IsTagManager(HasGuestPermission):
    def get_required_permission(self, request, view):
        return 'guest.manage_tags'
