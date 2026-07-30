from functools import wraps
from django.http import JsonResponse
from apps.core.rbac.models import UserPropertyRole

def check_property_access(user, tenant, property_id):
    """
    Checks if a user has access to a specific property.
    Superusers, Staff, Admins, Tenant Owners, and unrestricted tenant users bypass property restriction checking.
    """
    if not user or not user.is_authenticated:
        return False
        
    # 1. Superusers & Staff (Master Platform Developer Control)
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True

    if hasattr(user, 'role') and user.role:
        role_code = getattr(user.role, 'code', '') or (user.role if isinstance(user.role, str) else '')
        if role_code in ['super_admin', 'superadmin']:
            return True

    from django.db.models import Q
    from apps.core.accounts.models import UserAssignment
    # 3. If user has no specific property assignments under this tenant, they have full tenant-wide property access
    has_any_restrictions = UserAssignment.objects.filter(user=user, tenant=tenant, property__isnull=False).exists() or UserPropertyRole.objects.filter(user=user, tenant=tenant, property__isnull=False).exists()
    if not has_any_restrictions:
        return True
        
    # 4. Check if user is linked to the property (or has tenant-wide assignment property_id=None)
    has_assignment = UserAssignment.objects.filter(
        user=user,
        tenant=tenant
    ).filter(
        Q(property_id=property_id) | Q(property_id__isnull=True)
    ).exists()
    if has_assignment:
        return True

    return UserPropertyRole.objects.filter(
        user=user,
        tenant=tenant
    ).filter(
        Q(property_id=property_id) | Q(property_id__isnull=True)
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
