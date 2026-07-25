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

    class Meta:
        model = InventoryUnitType
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def get_amenities(self, obj):
        return list(obj.type_amenities.values_list('amenity__code', flat=True))

    def get_rooms_count(self, obj):
        return obj.inventory_units.count()

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
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

        seen_amenities = set()
        for item in amenities_data:
            val = item.get('code') or item.get('id') if isinstance(item, dict) else item
            if not val:
                continue

            amenity_qs = Amenity.objects.filter(
                models.Q(tenant=tenant) | models.Q(tenant__isnull=True)
            )
            amenity = amenity_qs.filter(models.Q(code=val) | models.Q(id=val)).first()

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

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
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

