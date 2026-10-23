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
        instance = getattr(self, 'instance', None)

        prop = data.get('property') or (getattr(instance, 'property', None) if instance else None)
        unit = data.get('inventory_unit') or (getattr(instance, 'inventory_unit', None) if instance else None)

        if not prop and unit and getattr(unit, 'property', None):
            prop = unit.property
            data['property'] = prop

        if prop and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        
        location = data.get('location') or (getattr(instance, 'location', None) if instance else None)
        if not unit and not location:
            raise serializers.ValidationError("Either a room (inventory unit) or a location must be specified.")

        if unit and prop and unit.property != prop:
            raise serializers.ValidationError("Inventory unit must belong to the target property.")

        # Ensure start_date and end_date are resolved and checked for conflicts
        start_date = data.get('start_date') or (getattr(instance, 'start_date', None) if instance else None)
        end_date = data.get('end_date') or (getattr(instance, 'end_date', None) if instance else None)

        if not start_date or not end_date:
            import re
            desc = data.get('description', '') or ''
            match = re.search(r'from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', desc, re.IGNORECASE)
            if match:
                from datetime import datetime
                try:
                    if not start_date:
                        start_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                        data['start_date'] = start_date
                    if not end_date:
                        end_date = datetime.strptime(match.group(2), '%Y-%m-%d').date()
                        data['end_date'] = end_date
                except Exception:
                    pass

        if not start_date or not end_date:
            from django.utils import timezone
            from datetime import timedelta
            today = timezone.localdate() if hasattr(timezone, 'localdate') else timezone.now().date()
            if not start_date:
                start_date = today
                data['start_date'] = start_date
            if not end_date:
                end_date = today + timedelta(days=1)
                data['end_date'] = end_date

        if unit:
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
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        start_date = validated_data.get('start_date')
        end_date = validated_data.get('end_date')
        if start_date and end_date:
            import re
            desc = validated_data.get('description') or ''
            if not re.search(r'from\s+\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}', desc, re.IGNORECASE):
                validated_data['description'] = f"{desc} from {start_date} to {end_date}".strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        start_date = validated_data.get('start_date', instance.start_date)
        end_date = validated_data.get('end_date', instance.end_date)
        if start_date and end_date:
            import re
            desc = validated_data.get('description', instance.description) or ''
            if not re.search(r'from\s+\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}', desc, re.IGNORECASE):
                validated_data['description'] = f"{desc} from {start_date} to {end_date}".strip()
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Ensure start_date and end_date are string dates in the output representation
        if not ret.get('start_date') or not ret.get('end_date'):
            if instance.start_date and instance.end_date:
                ret['start_date'] = instance.start_date.isoformat()
                ret['end_date'] = instance.end_date.isoformat()
            else:
                import re
                search_txt = f"{instance.title or ''} {instance.description or ''}"
                match = re.search(r'from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', search_txt, re.IGNORECASE)
                if match:
                    ret['start_date'] = match.group(1)
                    ret['end_date'] = match.group(2)
                elif instance.created_at:
                    from datetime import timedelta
                    ret['start_date'] = instance.created_at.date().isoformat()
                    ret['end_date'] = (instance.created_at.date() + timedelta(days=3)).isoformat()
                else:
                    from django.utils import timezone
                    from datetime import timedelta
                    today = timezone.localdate() if hasattr(timezone, 'localdate') else timezone.now().date()
                    ret['start_date'] = today.isoformat()
                    ret['end_date'] = (today + timedelta(days=3)).isoformat()

        if instance.inventory_unit:
            ret['inventory_unit_name'] = instance.inventory_unit.name
        return ret


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'


class TicketAssignSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
    user_id = serializers.UUIDField(required=True)


class TicketCompleteSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField(required=True)
