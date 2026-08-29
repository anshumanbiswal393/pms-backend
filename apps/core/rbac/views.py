from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from django.db.models import Q
from apps.core.rbac.models import Permission, Role, RolePermission, UserPropertyRole
from apps.core.rbac.serializers import PermissionSerializer, RoleSerializer, RolePermissionSerializer, UserPropertyRoleSerializer

class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for Permission catalog.
    """
    queryset = Permission.objects.all().order_by('category', 'code')
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

class RoleViewSet(viewsets.ModelViewSet):
    """
    CRUD Viewset for Roles. Displays tenant-specific roles (or global templates).
    """
    serializer_class = RoleSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        is_super = getattr(user, 'is_superuser', False) or (user.role and getattr(user.role, 'code', '') == 'super_admin')
        
        if is_super:
            tenant_param = self.request.query_params.get('tenant') or self.request.headers.get('X-Tenant-ID')
            if tenant_param:
                return Role.objects.filter(tenant_id=tenant_param)
            return Role.objects.all()
            
        if not tenant:
            return Role.objects.filter(tenant__isnull=True).exclude(code__in=['super_admin', 'owner'])
            
        # Return tenant's own custom roles
        tenant_roles = Role.objects.filter(tenant=tenant).exclude(code__in=['super_admin', 'owner'])
        if tenant_roles.exists():
            return tenant_roles
            
        # Fallback to global roles only if tenant has no roles yet
        return Role.objects.filter(tenant__isnull=True).exclude(code__in=['super_admin', 'owner'])

    def perform_create(self, serializer):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)

from rest_framework.decorators import action
from django.db import transaction

class RolePermissionViewSet(viewsets.ModelViewSet):
    """
    CRUD Viewset linking Permissions to Roles.
    """
    serializer_class = RolePermissionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        role_id = self.request.query_params.get('role')
        qs = RolePermission.objects.all()
        if tenant:
            qs = qs.filter(Q(role__tenant=tenant) | Q(role__tenant__isnull=True))
        else:
            qs = qs.filter(role__tenant__isnull=True)
        if role_id:
            qs = qs.filter(role_id=role_id)
        return qs

    def create(self, request, *args, **kwargs):
        role_id = request.data.get('role')
        perm_id = request.data.get('permission')
        if not role_id or not perm_id:
            return super().create(request, *args, **kwargs)
        
        instance, created = RolePermission.objects.get_or_create(
            role_id=role_id,
            permission_id=perm_id
        )
        serializer = self.get_serializer(instance)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

    @action(detail=False, methods=['post'], url_path='bulk-sync')
    def bulk_sync(self, request):
        """
        Instantly syncs, assigns, or revokes a role's permissions in a single atomic SQL transaction.
        Payload: { "role": "<role_id>", "permission_ids": ["uuid1", ...], "action": "assign" | "revoke" | "sync" }
        """
        role_id = request.data.get('role')
        if not role_id:
            return Response({"error": "Role ID is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            role = Role.objects.get(id=role_id)
        except Role.DoesNotExist:
            return Response({"error": "Role not found"}, status=status.HTTP_404_NOT_FOUND)

        permission_ids = request.data.get('permission_ids', [])
        action_type = request.data.get('action', 'assign')

        with transaction.atomic():
            if action_type == 'assign':
                objs = [
                    RolePermission(role=role, permission_id=pid)
                    for pid in permission_ids
                ]
                RolePermission.objects.bulk_create(objs, ignore_conflicts=True)
            elif action_type == 'revoke':
                RolePermission.objects.filter(role=role, permission_id__in=permission_ids).delete()
            elif action_type == 'sync':
                RolePermission.objects.filter(role=role).delete()
                objs = [
                    RolePermission(role=role, permission_id=pid)
                    for pid in permission_ids
                ]
                RolePermission.objects.bulk_create(objs, ignore_conflicts=True)
        
        # Fast direct dict response for ONLY this role (0ms query)
        qs = RolePermission.objects.filter(role=role).select_related('permission')
        data = [
            {
                "id": str(rp.id),
                "role": str(rp.role_id),
                "permission": str(rp.permission_id),
                "permission_code": rp.permission.code
            }
            for rp in qs
        ]
        return Response(data, status=status.HTTP_200_OK)

class UserPropertyRoleViewSet(viewsets.ModelViewSet):
    """
    CRUD Viewset for assigning Roles to Users per Property scope.
    """
    serializer_class = UserPropertyRoleSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return UserPropertyRole.objects.none()
        return UserPropertyRole.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)
