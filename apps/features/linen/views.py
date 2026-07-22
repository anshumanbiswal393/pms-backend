from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Sum
from apps.features.linen.models import LinenItem, LinenAssignment, LaundryRecord, GuestLaundryOrder, GuestLaundryOrderItem, LaundryMachine
from apps.features.linen.serializers import (
    LinenItemSerializer, LinenAssignmentSerializer, LaundryRecordSerializer,
    GuestLaundryOrderSerializer, GuestLaundryOrderItemSerializer, LaundryMachineSerializer
)


class LinenItemViewSet(viewsets.ModelViewSet):
    serializer_class = LinenItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return LinenItem.objects.none()
        
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        qs = LinenItem.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='adjust-stock')
    def adjust_stock(self, request, pk=None):
        item = self.get_object()
        quantity = request.data.get('quantity')
        
        if quantity is None:
            return Response({'error': 'quantity field is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            qty_int = int(quantity)
        except ValueError:
            return Response({'error': 'quantity must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
            
        item.total_qty += qty_int
        if item.total_qty < 0:
            return Response({'error': 'Resulting total quantity cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
            
        item.save()
        return Response(LinenItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='update-stock')
    def update_stock(self, request, pk=None):
        item = self.get_object()
        total_qty = request.data.get('total_qty')
        in_use_qty = request.data.get('in_use_qty')
        in_wash_qty = request.data.get('in_wash_qty')
        damaged_qty = request.data.get('damaged_qty')
        location = request.data.get('location')

        if total_qty is not None:
            item.total_qty = int(total_qty)
        if in_use_qty is not None:
            item.in_use_qty = int(in_use_qty)
        if in_wash_qty is not None:
            item.in_wash_qty = int(in_wash_qty)
        if damaged_qty is not None:
            item.damaged_qty = int(damaged_qty)
        if location:
            item.location = location

        item.save()
        return Response(LinenItemSerializer(item).data, status=status.HTTP_200_OK)


class LinenAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = LinenAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return LinenAssignment.objects.none()
        return LinenAssignment.objects.filter(tenant=tenant)


class LaundryRecordViewSet(viewsets.ModelViewSet):
    serializer_class = LaundryRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return LaundryRecord.objects.none()
            
        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        qs = LaundryRecord.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='receive-laundry')
    def receive_laundry(self, request, pk=None):
        record = self.get_object()
        quantity = request.data.get('quantity')
        is_lost = request.data.get('is_lost', False)
        
        if quantity is None:
            return Response({'error': 'quantity field is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            qty_int = int(quantity)
        except ValueError:
            return Response({'error': 'quantity must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if qty_int < 0:
            return Response({'error': 'quantity cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if record.quantity_returned + qty_int > record.quantity_sent:
            return Response({'error': 'Total returned quantity cannot exceed quantity sent.'}, status=status.HTTP_400_BAD_REQUEST)
            
        record.quantity_returned += qty_int
        if record.quantity_returned == record.quantity_sent:
            record.status = 'RETURNED'
        else:
            record.status = 'LOST' if is_lost else 'PARTIALLY_RETURNED'
            
        record.save()
        return Response(LaundryRecordSerializer(record).data, status=status.HTTP_200_OK)


class GuestLaundryOrderViewSet(viewsets.ModelViewSet):
    serializer_class = GuestLaundryOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestLaundryOrder.objects.none()

        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        order_status = self.request.query_params.get('status')
        is_posted = self.request.query_params.get('is_posted_to_folio')

        qs = GuestLaundryOrder.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if order_status:
            qs = qs.filter(status=order_status)
        if is_posted is not None:
            qs = qs.filter(is_posted_to_folio=is_posted.lower() in ['true', '1'])
        return qs.order_by('-created_at')

    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        qs = self.get_queryset()
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        pending_pickups = qs.filter(status='PICKUP_REQUESTED').count()
        in_washing = qs.filter(status='WASHING').count()
        ready_for_delivery = qs.filter(status='READY_FOR_DELIVERY').count()

        today_revenue_agg = qs.filter(created_at__gte=today_start).aggregate(total=Sum('total_amount'))
        today_revenue = float(today_revenue_agg['total'] or 0.00)

        recent_orders = GuestLaundryOrderSerializer(qs[:5], many=True).data

        return Response({
            'pending_pickups': pending_pickups,
            'in_washing': in_washing,
            'ready_for_delivery': ready_for_delivery,
            'today_revenue': today_revenue,
            'recent_orders': recent_orders
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')
        valid_statuses = [choice[0] for choice in GuestLaundryOrder.STATUS_CHOICES]

        if not new_status or new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

        order.status = new_status
        order.save()
        return Response(GuestLaundryOrderSerializer(order).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='post-to-folio')
    def post_to_folio(self, request, pk=None):
        order = self.get_object()
        if order.is_posted_to_folio:
            return Response({'error': 'Order has already been posted to folio.'}, status=status.HTTP_400_BAD_REQUEST)

        order.is_posted_to_folio = True
        order.posted_at = timezone.now()
        order.save()
        return Response(GuestLaundryOrderSerializer(order).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='receipt')
    def receipt(self, request, pk=None):
        order = self.get_object()
        serializer = GuestLaundryOrderSerializer(order)
        receipt_data = serializer.data
        receipt_data['receipt_generated_at'] = timezone.now().isoformat()
        return Response(receipt_data, status=status.HTTP_200_OK)


class LaundryMachineViewSet(viewsets.ModelViewSet):
    serializer_class = LaundryMachineSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return LaundryMachine.objects.none()

        property_id = self.request.query_params.get('property_id') or self.request.query_params.get('property')
        qs = LaundryMachine.objects.filter(tenant=tenant)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_status(self, request, pk=None):
        machine = self.get_object()
        new_status = request.data.get('status')
        valid_statuses = [choice[0] for choice in LaundryMachine.STATUS_CHOICES]

        if not new_status or new_status not in valid_statuses:
            return Response({'error': f'Invalid status. Must be one of {valid_statuses}'}, status=status.HTTP_400_BAD_REQUEST)

        machine.status = new_status
        machine.save()
        return Response(LaundryMachineSerializer(machine).data, status=status.HTTP_200_OK)
