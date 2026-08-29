from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from django.utils import timezone
from apps.core.common.models import SystemNotification

class SystemNotificationSerializer(serializers.ModelSerializer):
    time_ago = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = SystemNotification
        fields = [
            'id', 'tenant', 'property', 'property_name', 'category',
            'title', 'message', 'level', 'link_url', 'metadata',
            'is_read', 'read_at', 'created_at', 'time_ago'
        ]
        read_only_fields = ('id', 'tenant', 'created_at', 'read_at')

    def get_time_ago(self, obj):
        if not obj.created_at:
            return "Just now"
        diff = timezone.now() - obj.created_at
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "Just now"
        if seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        days = seconds // 86400
        return f"{days}d ago"


class SystemNotificationViewSet(viewsets.ModelViewSet):
    serializer_class = SystemNotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return SystemNotification.objects.none()

        qs = SystemNotification.objects.filter(tenant=tenant)
        
        # Property filter if provided
        property_id = self.request.headers.get('X-Property-ID') or self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)

        # Category filter if provided
        category = self.request.query_params.get('category')
        if category and category.upper() != 'ALL':
            qs = qs.filter(category__iexact=category)

        # Read / Unread filter
        is_read = self.request.query_params.get('is_read')
        if is_read is not None:
            if is_read.lower() == 'true':
                qs = qs.filter(is_read=True)
            elif is_read.lower() == 'false':
                qs = qs.filter(is_read=False)

        return qs.order_by('-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # Limit to latest 100 entries for fast response
        serializer = self.get_serializer(queryset[:100], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
        return Response({'success': True, 'id': str(notification.id), 'is_read': True})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return Response({'success': False, 'message': 'No tenant context found.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = SystemNotification.objects.filter(tenant=tenant, is_read=False)
        property_id = self.request.headers.get('X-Property-ID') or self.request.query_params.get('property_id') or (self.request.data.get('property_id') if isinstance(self.request.data, dict) else None)
        if property_id:
            qs = qs.filter(property_id=property_id)

        updated_count = qs.update(is_read=True, read_at=timezone.now())
        return Response({'success': True, 'updated_count': updated_count})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        user = self.request.user
        tenant = getattr(user, 'tenant', None) or getattr(self.request, 'tenant', None)
        if not tenant:
            return Response({'unread_count': 0})
        
        qs = SystemNotification.objects.filter(tenant=tenant, is_read=False)
        property_id = self.request.headers.get('X-Property-ID') or self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)

        return Response({'unread_count': qs.count()})
