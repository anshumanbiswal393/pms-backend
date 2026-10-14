from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.db import models
from apps.features.inventory.models import (
    InventoryUnitCategory, InventoryUnitType, InventoryUnit,
    InventoryRelationship, AttributeDefinition, InventoryUnitAttribute,
    Amenity, InventoryUnitTypeAmenity, InventoryMedia,
    Building, Floor, FloorPlan
)
from apps.features.inventory.services import (
    InventoryUnitService, InventoryRelationshipService,
    InventoryAttributeService, AmenityService
)

class InventoryUnitCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnitCategory
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class InventoryUnitTypeSerializer(serializers.ModelSerializer):
    amenities = serializers.SerializerMethodField()
    rooms_count = serializers.SerializerMethodField()
    media = serializers.SerializerMethodField()

    class Meta:
        model = InventoryUnitType
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def get_amenities(self, obj):
        return list(obj.type_amenities.values_list('amenity__code', flat=True))

    def get_rooms_count(self, obj):
        return obj.inventory_units.count()

    def get_media(self, obj):
        try:
            return [
                {
                    'id': str(m.id),
                    'media_url': m.media_url,
                    'media_type': m.media_type,
                    'sort_order': m.sort_order
                }
                for m in obj.type_media.all()
            ]
        except Exception:
            return []

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        name = data.get('name')
        if name:
            import re
            if not re.match(r"^[a-zA-Z0-9\s\-&.,'()]+$", name.strip()):
                raise ValidationError({"name": "Room Type Name cannot contain special characters (such as @, #, $, %, ^, *, etc.)."})

        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        
        cat = data.get('category')
        if cat and cat.tenant and cat.tenant != tenant:
            raise ValidationError("Category must belong to the resolved tenant context or be a system default.")
        
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        
    def _save_amenities(self, instance, amenities_data, tenant):
        # Hard delete existing relation records (including soft-deleted ones)
        # to prevent PostgreSQL unique constraint "unique_type_amenity_pair" clashes.
        InventoryUnitTypeAmenity.objects.all_with_deleted().filter(
            inventory_unit_type=instance
        ).hard_delete()

        import uuid
        seen_amenities = set()
        for item in amenities_data:
            val = item.get('code') or item.get('id') if isinstance(item, dict) else item
            if not val:
                continue

            amenity_qs = Amenity.objects.filter(
                models.Q(tenant=tenant) | models.Q(tenant__isnull=True)
            )

            is_valid_uuid = False
            try:
                uuid.UUID(str(val))
                is_valid_uuid = True
            except (ValueError, TypeError, AttributeError):
                is_valid_uuid = False

            if is_valid_uuid:
                amenity = amenity_qs.filter(models.Q(code=val) | models.Q(id=val)).first()
            else:
                amenity = amenity_qs.filter(code=val).first()

            if amenity and amenity.id not in seen_amenities:
                seen_amenities.add(amenity.id)
                InventoryUnitTypeAmenity.objects.create(
                    tenant=tenant,
                    inventory_unit_type=instance,
                    amenity=amenity
                )

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        
        amenities_data = request.data.get('amenities', [])
        instance = super().create(validated_data)
        
        if amenities_data:
            self._save_amenities(instance, amenities_data, tenant)
        return instance

    def update(self, instance, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        instance = super().update(instance, validated_data)
        
        if 'amenities' in request.data:
            amenities_data = request.data.get('amenities', [])
            self._save_amenities(instance, amenities_data, tenant)
        return instance


class InventoryUnitSerializer(serializers.ModelSerializer):
    assigned_staff = serializers.SerializerMethodField()
    building_name = serializers.CharField(source='building.name', read_only=True)
    floor_name = serializers.CharField(source='floor_id.name', read_only=True)

    class Meta:
        model = InventoryUnit
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def get_assigned_staff(self, obj):
        try:
            from apps.features.housekeeping.models import CleaningTask
            task = CleaningTask.objects.filter(
                room=obj,
                status__in=['PENDING', 'IN_PROGRESS']
            ).order_by('-created_at').first()
            if task and task.assigned_staff:
                return task.assigned_staff.id
        except ImportError:
            pass
        return None

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
            
        unit_type = data.get('inventory_unit_type')
        if unit_type and unit_type.property != prop:
            raise ValidationError("Inventory unit type must belong to the target property.")
            
        parent = data.get('parent_unit')
        if parent:
            if parent.property != prop:
                raise ValidationError("Parent unit must belong to the same property.")
            
            # Use circular validation from service
            instance_id = self.instance.id if self.instance else None
            try:
                InventoryUnitService.check_circular_parent(instance_id, parent)
            except ValidationError as e:
                raise serializers.ValidationError(e.message)

        # Prevent setting operational_status to maintenance if room has an active/confirmed guest reservation today
        if self.instance and data.get('operational_status') == 'maintenance':
            from apps.features.reservations.models import ReservationInventory
            from django.utils import timezone
            today = timezone.localdate() if hasattr(timezone, 'localdate') else timezone.now().date()
            active_res = ReservationInventory.objects.filter(
                tenant=tenant,
                inventory_unit=self.instance,
                check_in_date__lte=today,
                check_out_date__gt=today,
            ).exclude(
                reservation__status__in=['CANCELLED', 'NO_SHOW']
            ).exclude(
                status__in=['CANCELLED', 'CHECKED_OUT']
            )
            if active_res.exists():
                conflict = active_res.select_related('reservation', 'reservation__primary_guest').first()
                res = conflict.reservation
                guest_name = f"{res.primary_guest.first_name} {res.primary_guest.last_name}".strip() if res.primary_guest else "Guest"
                conf_no = res.confirmation_number or res.booking_reference or "N/A"
                raise serializers.ValidationError(
                    f"Room {self.instance.name} cannot be set to Maintenance: it is currently occupied/reserved by {guest_name} ({conf_no})."
                )

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class InventoryRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryRelationship
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        parent = data.get('parent_unit')
        child = data.get('child_unit')
        
        if parent and parent.tenant != tenant:
            raise ValidationError("Parent unit must belong to the resolved tenant context.")
        if child and child.tenant != tenant:
            raise ValidationError("Child unit must belong to the resolved tenant context.")
            
        try:
            InventoryRelationshipService.validate_relationship(parent, child)
        except ValidationError as e:
            raise serializers.ValidationError(e.message)
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeDefinition
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        data_type = data.get('data_type')
        allowed_values = data.get('allowed_values')
        if data_type == 'choice' and (not allowed_values or not isinstance(allowed_values, list)):
            raise ValidationError("Attribute definitions of type choice must define allowed_values as a JSON list.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class InventoryUnitAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnitAttribute
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        unit_type = data.get('inventory_unit_type')
        unit = data.get('inventory_unit')
        definition = data.get('attribute_definition')
        value = data.get('value')

        if not unit_type and not unit:
            raise ValidationError("Must target either an inventory_unit_type or an inventory_unit.")
        if unit_type and unit:
            raise ValidationError("Cannot target both an inventory_unit_type and an inventory_unit.")
            
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if unit and unit.tenant != tenant:
            raise ValidationError("Inventory unit must belong to the resolved tenant context.")
            
        if definition.tenant and definition.tenant != tenant:
            raise ValidationError("Attribute definition must belong to the resolved tenant context or be a system default.")

        try:
            InventoryAttributeService.validate_attribute_value(definition, value)
        except ValidationError as e:
            raise serializers.ValidationError(e.message)

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate_name(self, value):
        import re
        trimmed = (value or '').strip()
        if not trimmed:
            raise serializers.ValidationError("Amenity name cannot be empty.")
        if not re.match(r"^[a-zA-Z\s\-&/(),.']+$", trimmed):
            raise serializers.ValidationError("Amenity name must contain only letters, spaces, and standard punctuation (no numbers or special characters).")
        return trimmed

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        is_superadmin = user and user.is_authenticated and (user.is_superuser or getattr(user, 'role', '') == 'super_admin')
        
        if is_superadmin:
            validated_data['tenant'] = None
        else:
            tenant = getattr(request, 'tenant', None)
            validated_data['tenant'] = tenant

        validated_data['created_by'] = user if user and user.is_authenticated else None
        return super().create(validated_data)


class InventoryUnitTypeAmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnitTypeAmenity
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        unit_type = data.get('inventory_unit_type')
        amenity = data.get('amenity')
        
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if amenity and amenity.tenant and amenity.tenant != tenant:
            raise ValidationError("Amenity must belong to the resolved tenant context or be a system default.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class InventoryMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMedia
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        unit_type = data.get('inventory_unit_type')
        unit = data.get('inventory_unit')

        if not unit_type and not unit:
            raise ValidationError("Must target either an inventory_unit_type or an inventory_unit.")
        if unit_type and unit:
            raise ValidationError("Cannot target both an inventory_unit_type and an inventory_unit.")
            
        if unit_type and unit_type.tenant != tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if unit and unit.tenant != tenant:
            raise ValidationError("Inventory unit must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        url = instance.media_url or ''
        request = self.context.get('request')
        if url.startswith('/') and request:
            url = request.build_absolute_uri(url)
        ret['url'] = url
        ret['media_url'] = url
        ret['file'] = url
        return ret


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class FloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        building = data.get('building')
        if building and building.tenant != tenant:
            raise serializers.ValidationError("Building must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class FloorPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = FloorPlan
        fields = '__all__'
        read_only_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)

