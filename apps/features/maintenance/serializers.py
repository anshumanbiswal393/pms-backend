from rest_framework import serializers
from apps.features.maintenance.models import MaintenanceTicket, MaintenanceSchedule

class MaintenanceTicketSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.name', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    asset_name = serializers.CharField(source='asset.asset_name', read_only=True)
    room_location = serializers.SerializerMethodField()
    start_date = serializers.DateField(required=False, write_only=True)
    end_date = serializers.DateField(required=False, write_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'reference_number', 'created_at', 'updated_at')

    def get_room_location(self, obj):
        if obj.inventory_unit:
            name = obj.inventory_unit.name
            if name.lower().startswith('room'):
                return name
            return f"Room {name}"
        return obj.location or "Unknown Location"

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        
        unit = data.get('inventory_unit')
        location = data.get('location')
        if not unit and not location:
            raise serializers.ValidationError("Either a room (inventory unit) or a location must be specified.")

        if unit and unit.property != prop:
            raise serializers.ValidationError("Inventory unit must belong to the target property.")

        # Check for confirmed guest reservation conflicts when blocking/servicing a room
        if unit:
            start_date = data.get('start_date')
            end_date = data.get('end_date')

            if not start_date or not end_date:
                import re
                desc = data.get('description', '') or ''
                match = re.search(r'from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', desc)
                if match:
                    from datetime import datetime
                    try:
                        start_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                        end_date = datetime.strptime(match.group(2), '%Y-%m-%d').date()
                    except Exception:
                        pass

            if not start_date or not end_date:
                from django.utils import timezone
                from datetime import timedelta
                today = timezone.localdate() if hasattr(timezone, 'localdate') else timezone.now().date()
                start_date = today
                end_date = today + timedelta(days=1)

            from apps.features.reservations.models import ReservationInventory
            conflicting_allocations = ReservationInventory.objects.filter(
                tenant=tenant,
                inventory_unit=unit,
                check_in_date__lt=end_date,
                check_out_date__gt=start_date,
            ).exclude(
                reservation__status__in=['CANCELLED', 'NO_SHOW']
            ).exclude(
                status__in=['CANCELLED', 'CHECKED_OUT']
            )

            if conflicting_allocations.exists():
                conflict = conflicting_allocations.select_related('reservation', 'reservation__primary_guest').first()
                res = conflict.reservation
                guest_name = f"{res.primary_guest.first_name} {res.primary_guest.last_name}".strip() if res.primary_guest else "Guest"
                conf_no = res.confirmation_number or res.booking_reference or "N/A"
                res_status = res.status.replace('_', ' ').title()
                dates_str = f"{conflict.check_in_date} to {conflict.check_out_date}"
                raise serializers.ValidationError(
                    f"Room {unit.name} cannot be blocked: it has a confirmed/active reservation ({conf_no} - {guest_name}, Status: {res_status}) from {dates_str}."
                )

        return data

    def create(self, validated_data):
        validated_data.pop('start_date', None)
        validated_data.pop('end_date', None)
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop('start_date', None)
        validated_data.pop('end_date', None)
        return super().update(instance, validated_data)


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'


class TicketAssignSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
    user_id = serializers.UUIDField(required=True)


class TicketCompleteSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
