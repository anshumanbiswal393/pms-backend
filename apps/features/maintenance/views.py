from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from apps.features.maintenance.models import MaintenanceTicket, MaintenanceSchedule
from apps.core.accounts.models import AppUser
from apps.features.maintenance.serializers import (
    MaintenanceTicketSerializer, MaintenanceScheduleSerializer, 
    TicketAssignSerializer, TicketCompleteSerializer
)

@extend_schema(
    parameters=[
        OpenApiParameter(
            name='property',
            type=OpenApiTypes.UUID,
            location=OpenApiParameter.QUERY,
            description='Filter by property UUID',
            required=False
        ),
        OpenApiParameter(
            name='status',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Filter by ticket status',
            required=False,
            enum=['REPORTED', 'IN_PROGRESS', 'WAITING_PARTS', 'RESOLVED']
        ),
        OpenApiParameter(
            name='priority',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Filter by ticket priority',
            required=False,
            enum=['NORMAL', 'HIGH', 'CRITICAL']
        ),
        OpenApiParameter(
            name='category',
            type=str,
            location=OpenApiParameter.QUERY,
            description='Filter by ticket category',
            required=False,
            enum=['HVAC', 'PLUMBING', 'ELECTRICAL', 'FURNITURE', 'GENERAL']
        ),
    ]
)
class MaintenanceTicketViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceTicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return MaintenanceTicket.objects.none()
        
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        status_filter = self.request.query_params.get('status')
        priority_filter = self.request.query_params.get('priority')
        category_filter = self.request.query_params.get('category')
        search_query = self.request.query_params.get('search')
        
        qs = MaintenanceTicket.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if priority_filter:
            qs = qs.filter(priority=priority_filter)
        if category_filter:
            qs = qs.filter(category=category_filter)
        if search_query:
            qs = qs.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(reference_number__icontains=search_query)
            )
        return qs

    @action(detail=False, methods=['get'])
    def stats(self, request):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=status.HTTP_400_BAD_REQUEST)
        
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        
        tickets_qs = MaintenanceTicket.objects.filter(tenant=tenant)
        if property_id:
            tickets_qs = tickets_qs.filter(property_id=property_id)
            
        open_statuses = ['REPORTED', 'IN_PROGRESS', 'WAITING_PARTS']
        open_tickets = tickets_qs.filter(status__in=open_statuses)
        open_count = open_tickets.count()
        open_critical_count = open_tickets.filter(priority='CRITICAL').count()
        critical_count = open_critical_count
        
        from apps.features.inventory.models import InventoryUnit
        units_qs = InventoryUnit.objects.filter(tenant=tenant, operational_status__in=['maintenance', 'offline'])
        if property_id:
            units_qs = units_qs.filter(property_id=property_id)
        rooms_ooo_count = units_qs.count()
        
        resolved_tickets = tickets_qs.filter(status='RESOLVED', updated_at__isnull=False)
        total_hours = 0.0
        resolved_count = 0
        for t in resolved_tickets:
            duration = t.updated_at - t.created_at
            total_hours += duration.total_seconds() / 3600.0
            resolved_count += 1
        
        avg_resolution_hours = round(total_hours / resolved_count, 1) if resolved_count > 0 else 0.0
        
        today = timezone.now().date()
        next_week = today + timedelta(days=7)
        pm_qs = MaintenanceSchedule.objects.filter(asset__tenant=tenant, next_due_date__range=[today, next_week])
        if property_id:
            pm_qs = pm_qs.filter(asset__property_id=property_id)
        pm_due_count = pm_qs.count()
        
        return Response({
            'open_work_orders': open_count,
            'open_critical_count': open_critical_count,
            'critical_count': critical_count,
            'rooms_ooo': rooms_ooo_count,
            'avg_resolution': f"{avg_resolution_hours}h",
            'avg_resolution_hours': avg_resolution_hours,
            'pm_due_this_week': pm_due_count,
        }, status=status.HTTP_200_OK)


class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = MaintenanceScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return MaintenanceSchedule.objects.none()
        return MaintenanceSchedule.objects.filter(asset__tenant=tenant)


class TicketAssignView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TicketAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ticket_id = serializer.validated_data['ticket_id']
        user_id = serializer.validated_data['user_id']

        try:
            ticket = MaintenanceTicket.objects.get(id=ticket_id, tenant=tenant)
        except MaintenanceTicket.DoesNotExist:
            return Response({'error': 'Maintenance ticket not found.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = AppUser.objects.get(id=user_id, tenant=tenant)
        except AppUser.DoesNotExist:
            return Response({'error': 'User not found under this tenant.'}, status=status.HTTP_400_BAD_REQUEST)

        ticket.status = 'IN_PROGRESS'
        ticket.assigned_to = user
        ticket.save()

        # Update InventoryUnit maintenance status to 'active'
        unit = ticket.inventory_unit
        if unit:
            unit.maintenance_status = 'active'
            unit.save(update_fields=['maintenance_status', 'updated_at'])

        return Response(MaintenanceTicketSerializer(ticket).data, status=status.HTTP_200_OK)


class TicketCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context is missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TicketCompleteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        ticket_id = serializer.validated_data['ticket_id']

        try:
            ticket = MaintenanceTicket.objects.get(id=ticket_id, tenant=tenant)
        except MaintenanceTicket.DoesNotExist:
            return Response({'error': 'Maintenance ticket not found.'}, status=status.HTTP_400_BAD_REQUEST)

        ticket.status = 'RESOLVED'
        ticket.save()

        # Set InventoryUnit maintenance status to 'none'
        unit = ticket.inventory_unit
        if unit:
            unit.maintenance_status = 'none'
            unit.save(update_fields=['maintenance_status', 'updated_at'])

        return Response(MaintenanceTicketSerializer(ticket).data, status=status.HTTP_200_OK)
