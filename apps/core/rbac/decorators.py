from functools import wraps
from django.http import JsonResponse
from apps.core.rbac.models import UserPropertyRole

def check_property_access(user, tenant, property_id):
    """
    Checks if a user has access to a specific property.
    Superusers and Tenant Owners bypass checking.
    """
    if not user.is_authenticated:
        return False
        
    # Superusers and Tenant Owners bypass property checks
    if user.is_superuser or user.is_staff or (user.role and user.role.code in ['owner', 'tenant_owner', 'admin', 'super_admin']) or (user.role and 'owner' in user.role.name.lower()):
        return True
        
    from apps.core.accounts.models import UserAssignment
    # Check if user is linked to the property via UserAssignment or UserPropertyRole under the tenant
    has_assignment = UserAssignment.objects.filter(
        user=user,
        tenant=tenant,
        property_id=property_id
    ).exists()
    if has_assignment:
        return True

    return UserPropertyRole.objects.filter(
        user=user,
        property_id=property_id,
        tenant=tenant
    ).exists()

def require_property_access(property_id_param='property_id'):
    """
    Decorator for views that checks if the logged-in user has access
    to the property specified in the request.
    It checks URL kwargs, GET parameters, or X-Property-ID header.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({'error': 'Authentication credentials were not provided.'}, status=401)

            # Retrieve property_id
            property_id = kwargs.get(property_id_param)
            if not property_id:
                property_id = request.GET.get(property_id_param)
            if not property_id:
                property_id = request.headers.get('X-Property-ID')

            if not property_id:
                return JsonResponse({'error': 'Property ID context is missing. Provide property_id parameter or X-Property-ID header.'}, status=400)

            # Resolve tenant
            tenant = getattr(request, 'tenant', None)
            if not tenant:
                return JsonResponse({'error': 'Tenant context is missing.'}, status=400)

            # Check access
            if not check_property_access(request.user, tenant, property_id):
                return JsonResponse({'error': f'You do not have access to property with ID {property_id}.'}, status=403)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
