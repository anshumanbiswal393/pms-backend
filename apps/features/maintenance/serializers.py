from rest_framework import serializers
from apps.features.maintenance.models import MaintenanceTicket, MaintenanceSchedule

class MaintenanceTicketSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.name', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    asset_name = serializers.CharField(source='asset.asset_name', read_only=True)
    room_location = serializers.SerializerMethodField()

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

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'


class TicketAssignSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
    user_id = serializers.UUIDField(required=True)


class TicketCompleteSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
