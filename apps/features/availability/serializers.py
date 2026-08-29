from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from apps.features.availability.models import (
    InventoryAvailability, InventoryRestriction, InventoryHold,
    GroupBlock, GroupBlockAllocation, Channel, ChannelAllocation,
    DynamicAvailabilityRule, WaitlistEntry,
    InventorySharedPool, InventorySharedPoolUnitType
)
from apps.features.inventory.models import InventoryUnitType, InventoryUnit

class InventoryAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryAvailability
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.property != prop:
            raise ValidationError("Inventory unit type must belong to the target property.")

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class BulkAvailabilityItemSerializer(serializers.Serializer):
    date = serializers.DateField()
    inventory_unit_type_id = serializers.UUIDField()
    allocated_count = serializers.IntegerField(min_value=0, required=False)
    sold_count = serializers.IntegerField(min_value=0, required=False)
    blocked_count = serializers.IntegerField(min_value=0, required=False)
    overbooking_limit = serializers.IntegerField(min_value=0, required=False)


class BulkAvailabilityUpdateSerializer(serializers.Serializer):
    property_id = serializers.UUIDField()
    updates = serializers.ListField(child=BulkAvailabilityItemSerializer())


class InventoryRestrictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryRestriction
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.property != prop:
            raise ValidationError("Inventory unit type must belong to the target property.")

        restriction_type = data.get('restriction_type')
        restriction_value = data.get('restriction_value')

        if restriction_type in ['MIN_LOS', 'MAX_LOS']:
            if restriction_value is None:
                raise ValidationError({"restriction_value": f"Restriction value is required for restriction type {restriction_type}."})
            if restriction_value < 1:
                raise ValidationError({"restriction_value": "Restriction value must be greater than or equal to 1 for LOS controls."})

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class InventoryHoldSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryHold
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.property != prop:
            raise ValidationError("Inventory unit type must belong to the target property.")

        unit = data.get('inventory_unit')
        if unit:
            if unit.property != prop:
                raise ValidationError("Inventory unit must belong to the target property.")
            if unit.inventory_unit_type != unit_type:
                raise ValidationError("Target inventory unit type must match the specific inventory unit's type.")

        quantity = data.get('quantity', 1)
        if quantity < 1:
            raise ValidationError({"quantity": "Hold quantity must be greater than or equal to 1."})

        if not data.get('expires_at') and not self.instance:
            raise ValidationError({"expires_at": "Expiration timestamp is required."})

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class GroupBlockAllocationSerializer(serializers.ModelSerializer):
    group_block_code = serializers.CharField(source='group_block.code', read_only=True)
    inventory_unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)
    inventory_unit_type_name = serializers.CharField(source='inventory_unit_type.name', read_only=True)

    class Meta:
        model = GroupBlockAllocation
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        block = data.get('group_block')
        if block and block.tenant != tenant:
            raise ValidationError("Group block must belong to the resolved tenant context.")
            
        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        validated_data['created_by'] = user
        return super().create(validated_data)


class GroupBlockSerializer(serializers.ModelSerializer):
    allocations = GroupBlockAllocationSerializer(many=True, read_only=True)
    id_type_name = serializers.SerializerMethodField()
    nationality_name = serializers.SerializerMethodField()
    property_details = serializers.SerializerMethodField()

    class Meta:
        model = GroupBlock
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def get_property_details(self, obj):
        if not obj.property:
            return None
        p = obj.property
        return {
            'id': str(p.id),
            'name': p.name,
            'address_line_1': p.address_line_1 or "",
            'address_line_2': p.address_line_2 or "",
            'city': p.city or "",
            'state': p.state or "",
            'country': p.country or "",
            'postal_code': p.postal_code or "",
            'contact_phone': p.contact_phone or "",
            'contact_email': p.contact_email or "",
            'tax_id': p.tax_id or "",
            'website_logo': p.website_logo or "",
        }

    def get_id_type_name(self, obj):
        if not obj.id_type:
            return ""
        from apps.core.reference.models import DocumentType
        import uuid
        try:
            val = str(obj.id_type).strip()
            if len(val) == 36 and '-' in val:
                doc = DocumentType.objects.filter(id=uuid.UUID(val)).first()
                if doc:
                    return doc.name
            doc = DocumentType.objects.filter(code__iexact=val).first()
            if doc:
                return doc.name
            doc = DocumentType.objects.filter(name__iexact=val).first()
            if doc:
                return doc.name
        except Exception:
            pass
        return str(obj.id_type)

    def get_nationality_name(self, obj):
        if not obj.nationality:
            return "Indian"
        from apps.core.reference.models import Nationality
        import uuid
        try:
            val = str(obj.nationality).strip()
            if len(val) == 36 and '-' in val:
                nat = Nationality.objects.filter(id=uuid.UUID(val)).first()
                if nat:
                    return nat.name
            nat = Nationality.objects.filter(code__iexact=val).first()
            if nat:
                return nat.name
            nat = Nationality.objects.filter(name__iexact=val).first()
            if nat:
                return nat.name
        except Exception:
            pass
        return str(obj.nationality)

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        import datetime
        from django.db import models
        from apps.features.inventory.models import InventoryUnitType

        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        
        group_block = super().create(validated_data)

        # Auto-create GroupBlockAllocation records if dates exist
        start_date = group_block.start_date
        end_date = group_block.end_date
        if start_date and end_date and start_date <= end_date:
            initial_room_selections = self.initial_data.get('room_selections', [])
            if initial_room_selections:
                for rs in initial_room_selections:
                    room_type_id_or_code = rs.get('roomType') or rs.get('inventory_unit_type_id')
                    ut = None
                    if room_type_id_or_code:
                        ut = InventoryUnitType.objects.filter(
                            tenant=tenant, property=group_block.property
                        ).filter(
                            models.Q(id=room_type_id_or_code) | models.Q(code=room_type_id_or_code) | models.Q(name__iexact=room_type_id_or_code)
                        ).first()
                    if not ut:
                        ut = InventoryUnitType.objects.filter(tenant=tenant, property=group_block.property).first()

                    if ut:
                        assigned_count = len(rs.get('assignedRooms', [])) or group_block.total_rooms or 1
                        curr_date = start_date
                        while curr_date < end_date:
                            GroupBlockAllocation.objects.get_or_create(
                                group_block=group_block,
                                inventory_unit_type=ut,
                                date=curr_date,
                                defaults={
                                    'allocated_qty': assigned_count,
                                    'picked_up_qty': 0,
                                    'created_by': user
                                }
                            )
                            curr_date += datetime.timedelta(days=1)
            else:
                ut = InventoryUnitType.objects.filter(tenant=tenant, property=group_block.property).first()
                if ut:
                    total_qty = group_block.total_rooms or 1
                    curr_date = start_date
                    while curr_date < end_date:
                        GroupBlockAllocation.objects.get_or_create(
                            group_block=group_block,
                            inventory_unit_type=ut,
                            date=curr_date,
                            defaults={
                                'allocated_qty': total_qty,
                                'picked_up_qty': 0,
                                'created_by': user
                            }
                        )
                        curr_date += datetime.timedelta(days=1)

        return group_block


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request else None
        return super().create(validated_data)


class ChannelAllocationSerializer(serializers.ModelSerializer):
    inventory_unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)
    channel_code = serializers.CharField(source='channel.code', read_only=True)
    remaining_qty = serializers.IntegerField(read_only=True)

    class Meta:
        model = ChannelAllocation
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        
        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")

        channel = data.get('channel')
        if channel and channel.tenant != tenant:
            raise ValidationError("Channel must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        return super().create(validated_data)


class DynamicAvailabilityRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicAvailabilityRule
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        return super().create(validated_data)


class WaitlistEntrySerializer(serializers.ModelSerializer):
    inventory_unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)
    guest_name = serializers.SerializerMethodField()

    class Meta:
        model = WaitlistEntry
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at', 'converted_at', 'converted_by', 'reservation')

    def get_guest_name(self, obj):
        if obj.guest:
            return f"{obj.guest.first_name} {obj.guest.last_name}"
        return "Unknown Guest"

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        
        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")

        guest = data.get('guest')
        if guest and guest.tenant != tenant:
            raise ValidationError("Guest must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        return super().create(validated_data)


class InventorySharedPoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySharedPool
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        return super().create(validated_data)


class InventorySharedPoolUnitTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySharedPoolUnitType
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        pool = data.get('pool')
        if pool and pool.tenant != tenant:
            raise ValidationError("Shared pool must belong to the resolved tenant context.")
            
        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        validated_data['created_by'] = user
        return super().create(validated_data)
