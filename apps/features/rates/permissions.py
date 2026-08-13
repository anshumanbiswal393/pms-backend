from rest_framework import permissions
from apps.core.rbac.utils import check_user_permission

class HasRatePermission(permissions.BasePermission):
    """
    DRF permission class that validates if the authenticated user
    has the required permission for rates, packages, and services.
    """
    def __init__(self, required_permission=None):
        super().__init__()
        self.required_permission = required_permission

    def get_required_permission(self, request, view):
        if self.required_permission:
            return self.required_permission
        
        if view.action in ['list', 'retrieve', 'calendar', 'property_calendar']:
            return ['rates.view', 'rate.view', 'packages.view', 'services.view']
        elif view.action in ['create', 'rebuild']:
            return ['rates.create', 'rate.create', 'packages.create', 'services.create']
        elif view.action in ['update', 'partial_update']:
            return ['rates.edit', 'rate.edit', 'packages.edit', 'services.edit']
        elif view.action == 'destroy':
            return ['rates.delete', 'rate.delete', 'packages.delete', 'services.delete']
        
        return ['rates.view', 'rate.view', 'packages.view', 'services.view']

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user_role = str(getattr(request.user, 'role', '') or '').lower()
        if getattr(request.user, 'is_superuser', False) or getattr(request.user, 'is_staff', False) or user_role in ['super_admin', 'superadmin', 'owner', 'tenant_admin', 'hotel_owner', 'admin']:
            return True

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return False

        perm_codes = self.get_required_permission(request, view)

        # Property ID context
        property_id = request.headers.get('X-Property-ID') or request.query_params.get('property_id')
        if not property_id:
            property_id = view.kwargs.get('property_id')
        if not property_id and hasattr(request.data, 'get'):
            property_id = request.data.get('property_id') or request.data.get('property')

        return check_user_permission(request.user, tenant, perm_codes, property_id=property_id)


class IsRateCalendarManager(HasRatePermission):
    def get_required_permission(self, request, view):
        return ['rate.calendar.manage', 'rates.view', 'rates.edit']


class IsPolicyManager(HasRatePermission):
    def get_required_permission(self, request, view):
        return ['policy.manage', 'rates.view', 'settings.view']


class IsPackageManager(HasRatePermission):
    def get_required_permission(self, request, view):
        if view.action in ['list', 'retrieve']:
            return ['packages.view', 'services.view', 'rates.view', 'package.manage']
        elif view.action == 'create':
            return ['packages.create', 'services.create', 'rates.create', 'package.manage']
        elif view.action in ['update', 'partial_update']:
            return ['packages.edit', 'services.edit', 'rates.edit', 'package.manage']
        elif view.action == 'destroy':
            return ['packages.delete', 'services.delete', 'rates.delete', 'package.manage']
        return ['packages.view', 'services.view', 'rates.view', 'package.manage']

