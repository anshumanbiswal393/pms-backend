import django_filters
from apps.features.inventory.models import (
    InventoryUnitCategory, InventoryUnitType, InventoryUnit,
    InventoryRelationship, AttributeDefinition, InventoryUnitAttribute,
    Amenity, InventoryUnitTypeAmenity, InventoryMedia,
    Building, Floor, FloorPlan
)

class InventoryUnitCategoryFilter(django_filters.FilterSet):
    class Meta:
        model = InventoryUnitCategory
        fields = ['code', 'is_system', 'is_active']

class InventoryUnitTypeFilter(django_filters.FilterSet):
    property_id = django_filters.UUIDFilter(field_name='property_id')
    property = django_filters.UUIDFilter(field_name='property_id')
    class Meta:
        model = InventoryUnitType
        fields = ['property_id', 'property', 'category', 'is_sellable']

class InventoryUnitFilter(django_filters.FilterSet):
    property_id = django_filters.UUIDFilter(field_name='property_id')
    class Meta:
        model = InventoryUnit
        fields = ['property_id', 'inventory_unit_type', 'operational_status', 'housekeeping_status', 'maintenance_status', 'building', 'floor_id']

class InventoryRelationshipFilter(django_filters.FilterSet):
    class Meta:
        model = InventoryRelationship
        fields = ['relation_type', 'parent_unit', 'child_unit']

class AttributeDefinitionFilter(django_filters.FilterSet):
    class Meta:
        model = AttributeDefinition
        fields = ['code', 'data_type']

class InventoryUnitAttributeFilter(django_filters.FilterSet):
    class Meta:
        model = InventoryUnitAttribute
        fields = ['inventory_unit_type', 'inventory_unit', 'attribute_definition']

class AmenityFilter(django_filters.FilterSet):
    class Meta:
        model = Amenity
        fields = ['code', 'category']

class InventoryUnitTypeAmenityFilter(django_filters.FilterSet):
    class Meta:
        model = InventoryUnitTypeAmenity
        fields = ['inventory_unit_type', 'amenity']

class InventoryMediaFilter(django_filters.FilterSet):
    class Meta:
        model = InventoryMedia
        fields = ['inventory_unit_type', 'inventory_unit', 'media_type']

class BuildingFilter(django_filters.FilterSet):
    property_id = django_filters.UUIDFilter(field_name='property_id')
    class Meta:
        model = Building
        fields = ['property_id', 'code']

class FloorFilter(django_filters.FilterSet):
    class Meta:
        model = Floor
        fields = ['building', 'floor_number']

class FloorPlanFilter(django_filters.FilterSet):
    class Meta:
        model = FloorPlan
        fields = ['floor', 'version']
