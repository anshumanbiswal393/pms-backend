from django.db.models import Q
from apps.core.rbac.models import UserPropertyRole, Role
from apps.core.accounts.models import UserAssignment

def check_user_permission(user, tenant, perm_codes, property_id=None):
    """
    Unified permission checking algorithm across the entire PMS platform.
    Validates if `user` has any of `perm_codes` under `tenant` (and optional `property_id`).
    
    Order of Evaluation:
    1. Superuser / Master Platform Staff / Hotel Owner (`is_superuser`, `is_staff`, or `role in ['super_admin', 'owner', 'tenant_admin']`) -> True.
    2. User's direct assigned role (`user.role`). Evaluated via database RolePermission records.
    3. `UserAssignment` records. Evaluated via database RolePermission records.
    4. `UserPropertyRole` records. Evaluated via database RolePermission records.
    """
    if not user or not user.is_authenticated:
        return False

    # 1. Superuser / Master Platform Staff / Hotel Owner Role Bypass
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True

    if hasattr(user, 'role') and user.role:
        role_code = getattr(user.role, 'code', '') or (user.role if isinstance(user.role, str) else '')
        role_code = str(role_code).lower()
        if role_code in ['super_admin', 'superadmin', 'owner', 'tenant_admin', 'hotel_owner', 'admin']:
            return True

    if isinstance(perm_codes, str):
        perm_codes = [perm_codes]

    # Include wildcard and dot/colon notation translations
    extended_codes = set(perm_codes)
    extended_codes.add("*:*")
    extended_codes.add("*")
    
    for pc in perm_codes:
        if "." in pc:
            prefix = pc.split(".")[0]
            extended_codes.add(f"{prefix}.manage")
            extended_codes.add(f"{prefix}:manage")
            extended_codes.add(pc.replace(".", ":"))
            if pc.endswith('.edit'):
                extended_codes.add(pc.replace('.edit', '.manage'))
                extended_codes.add(pc.replace('.edit', ':manage'))
                extended_codes.add(pc.replace('.edit', ':update'))
            elif pc.endswith('.create'):
                extended_codes.add(pc.replace('.create', '.manage'))
                extended_codes.add(pc.replace('.create', ':manage'))
            elif pc.endswith('.delete'):
                extended_codes.add(pc.replace('.delete', '.manage'))
                extended_codes.add(pc.replace('.delete', ':manage'))
        if ":" in pc:
            prefix = pc.split(":")[0]
            extended_codes.add(f"{prefix}.manage")
            extended_codes.add(f"{prefix}:manage")
            extended_codes.add(pc.replace(":", "."))
            if pc.endswith(':manage'):
                extended_codes.add(pc.replace(':manage', '.edit'))
                extended_codes.add(pc.replace(':manage', '.create'))
                extended_codes.add(pc.replace(':manage', '.delete'))
                extended_codes.add(pc.replace(':manage', '.manage'))
            elif pc.endswith(':update'):
                extended_codes.add(pc.replace(':update', '.edit'))

    # 2. Direct role on user (Evaluates DB permissions assigned to user.role)
    role_obj = None
    if hasattr(user, 'role') and user.role:
        if isinstance(user.role, str):
            role_obj = Role.objects.filter(Q(code=user.role) | Q(name__iexact=user.role)).filter(Q(tenant=tenant) | Q(tenant__isnull=True)).first()
        else:
            role_obj = user.role

    if role_obj and role_obj.permissions.filter(permission__code__in=extended_codes).exists():
        return True

    # 3. UserAssignment check (Evaluates DB permissions assigned to ua.role)
    uas = UserAssignment.objects.filter(user=user)
    if tenant:
        uas = uas.filter(tenant=tenant)
    if property_id:
        uas = uas.filter(Q(property_id=property_id) | Q(property_id__isnull=True))
    for ua in uas:
        if ua.role and ua.role.permissions.filter(permission__code__in=extended_codes).exists():
            return True

    # 4. UserPropertyRole check (Evaluates DB permissions assigned to upr.role)
    uprs = UserPropertyRole.objects.filter(user=user)
    if tenant:
        uprs = uprs.filter(tenant=tenant)
    if property_id:
        uprs = uprs.filter(Q(property_id=property_id) | Q(property_id__isnull=True))
    for upr in uprs:
        if upr.role and upr.role.permissions.filter(permission__code__in=extended_codes).exists():
            return True

    return False
