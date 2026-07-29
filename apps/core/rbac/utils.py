from django.db.models import Q
from apps.core.rbac.models import UserPropertyRole
from apps.core.accounts.models import UserAssignment

def check_user_permission(user, tenant, perm_codes, property_id=None):
    """
    Unified permission checking algorithm across the entire PMS platform.
    Validates if `user` has any of `perm_codes` under `tenant` (and optional `property_id`).
    
    Order of Evaluation:
    1. Superuser / Platform Staff / Tenant Owner / Tenant Admin -> ALWAYS Granted (True).
    2. User's direct assigned role (user.role).
    3. UserAssignment records.
    4. UserPropertyRole records.
    """
    if not user or not user.is_authenticated:
        return False

    # 1. Superuser / Platform Staff
    if user.is_superuser or user.is_staff:
        return True

    # Get role string regardless of string vs object
    role_str = ""
    if hasattr(user, 'role') and user.role:
        if isinstance(user.role, str):
            role_str = user.role.lower()
        elif hasattr(user.role, 'code') and user.role.code:
            role_str = str(user.role.code).lower()
        elif hasattr(user.role, 'name') and user.role.name:
            role_str = str(user.role.name).lower()

    # 2. Tenant Owner / Admin Check -> ALWAYS Granted
    if role_str in ['owner', 'tenant_owner', 'admin', 'super_admin', 'superadmin', 'manager'] or 'owner' in role_str or 'admin' in role_str:
        return True

    if isinstance(perm_codes, str):
        perm_codes = [perm_codes]

    # Include wildcard and fallback permissions
    extended_codes = set(perm_codes)
    extended_codes.add("*:*")
    for pc in perm_codes:
        if pc.endswith('.view'):
            extended_codes.add('settings.view')
        elif pc.endswith('.create') or pc.endswith('.edit') or pc.endswith('.delete') or pc.endswith('.manage'):
            extended_codes.add('settings.edit')

    # 3. Direct role on user
    if user.role:
        if user.role.code in ['owner', 'tenant_owner', 'admin', 'super_admin'] or 'owner' in user.role.name.lower():
            return True
        if user.role.permissions.filter(permission__code__in=extended_codes).exists():
            return True

    # 4. UserAssignment check
    uas = UserAssignment.objects.filter(user=user, tenant=tenant)
    if property_id:
        uas = uas.filter(Q(property_id=property_id) | Q(property_id__isnull=True))
    for ua in uas:
        if ua.role:
            if ua.role.code in ['owner', 'tenant_owner', 'admin', 'super_admin'] or 'owner' in ua.role.name.lower():
                return True
            if ua.role.permissions.filter(permission__code__in=extended_codes).exists():
                return True

    # 5. UserPropertyRole check
    uprs = UserPropertyRole.objects.filter(user=user, tenant=tenant)
    if property_id:
        uprs = uprs.filter(Q(property_id=property_id) | Q(property_id__isnull=True))
    for upr in uprs:
        if upr.role:
            if upr.role.code in ['owner', 'tenant_owner', 'admin', 'super_admin'] or 'owner' in upr.role.name.lower():
                return True
            if upr.role.permissions.filter(permission__code__in=extended_codes).exists():
                return True

    return False
