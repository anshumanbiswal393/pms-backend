from rest_framework import viewsets, permissions, pagination
from apps.core.audit.models import AuditLog
from apps.core.audit.serializers import AuditLogSerializer
from django.utils import timezone
from datetime import timedelta

class AuditLogPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Tenant-isolated, read-only viewset for Audit logs.
    """
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        tenant = getattr(self.request.user, 'tenant', getattr(self.request, 'tenant', None))
        if not tenant:
            return AuditLog.objects.none()
        
        queryset = AuditLog.objects.filter(tenant=tenant)
        
        # Filter for last 24 hours if last_24_hours=true
        last_24 = self.request.query_params.get('last_24_hours', 'false').lower() == 'true'
        if last_24:
            cutoff = timezone.now() - timedelta(hours=24)
            queryset = queryset.filter(timestamp__gte=cutoff)
            
        return queryset.order_by('-timestamp')


class SuperadminAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Cross-tenant, read-only viewset for Audit logs (Superadmin only).
    """
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        user = self.request.user
        if not (user and (user.is_superuser or getattr(user, 'role_code', '') == 'super_admin')):
            return AuditLog.objects.none()

        queryset = AuditLog.objects.all()

        # Tenant filter
        tenant_id = self.request.query_params.get('tenant_id')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        # Actor filter
        actor_name = self.request.query_params.get('actor_name')
        if actor_name:
            queryset = queryset.filter(actor_name__icontains=actor_name)

        # Action type filter
        action_type = self.request.query_params.get('action_type')
        if action_type:
            queryset = queryset.filter(action_type__icontains=action_type)

        # Date filters
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(timestamp__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(timestamp__lte=date_to)

        # Search query
        search = self.request.query_params.get('search')
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(actor_name__icontains=search) |
                Q(action_type__icontains=search) |
                Q(target_entity__icontains=search) |
                Q(ip_address__icontains=search)
            )

        # Filter for last 24 hours
        last_24 = self.request.query_params.get('last_24_hours', 'false').lower() == 'true'
        if last_24:
            cutoff = timezone.now() - timedelta(hours=24)
            queryset = queryset.filter(timestamp__gte=cutoff)

        return queryset.order_by('-timestamp')

