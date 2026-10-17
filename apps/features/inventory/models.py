import builtins
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property

class InventoryUnitCategory(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='inventory_categories')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Inventory Unit Categories'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_category_code', condition=models.Q(tenant__isnull=False)),
            models.UniqueConstraint(fields=['code'], name='unique_system_category_code', condition=models.Q(tenant__isnull=True)),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class InventoryUnitType(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='unit_types')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='unit_types')
    category = models.ForeignKey(InventoryUnitCategory, on_delete=models.PROTECT, related_name='unit_types')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    
    base_occupancy = models.IntegerField(default=2)
    max_occupancy = models.IntegerField(default=2)
    max_adults = models.IntegerField(default=2)
    max_children = models.IntegerField(default=0)
    max_infants = models.IntegerField(default=0)
    is_sellable = models.BooleanField(default=True)
    
    # STAAH & PMS Physical Specifications
    size_measurement = models.CharField(max_length=32, blank=True, default='25', help_text='Room size measurement')
    size_measurement_unit = models.CharField(max_length=16, blank=True, default='sqm', help_text='Measurement unit (sqm, sqft)')
    description = models.TextField(blank=True, default='', help_text='Room type description')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_unit_type_code'),
        ]

    @builtins.property
    def status(self):
        return 'ACTIVE' if self.deleted_at is None else 'INACTIVE'

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.property.name}"


class InventoryUnit(BaseModel):
    OPERATIONAL_STATUS_CHOICES = (
        ('operational', 'Operational'),
        ('maintenance', 'Maintenance'),
        ('offline', 'Offline'),
    )
    HOUSEKEEPING_STATUS_CHOICES = (
        ('clean', 'Clean'),
        ('dirty', 'Dirty'),
        ('inspecting', 'Inspecting'),
    )
    MAINTENANCE_STATUS_CHOICES = (
        ('none', 'None'),
        ('reported', 'Reported'),
        ('active', 'Active'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='inventory_units')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='inventory_units')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.PROTECT, related_name='inventory_units')
    parent_unit = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_units')
    
    name = models.CharField(max_length=120)
    floor = models.CharField(max_length=32, null=True, blank=True)
    building = models.ForeignKey('Building', on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_units')
    floor_id = models.ForeignKey('Floor', on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_units', db_column='floor_id')
    
    operational_status = models.CharField(max_length=32, choices=OPERATIONAL_STATUS_CHOICES, default='operational')
    housekeeping_status = models.CharField(max_length=32, choices=HOUSEKEEPING_STATUS_CHOICES, default='clean')
    maintenance_status = models.CharField(max_length=32, choices=MAINTENANCE_STATUS_CHOICES, default='none')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'name'], name='unique_property_unit_name'),
        ]

    def __str__(self):
        return f"{self.name} ({self.inventory_unit_type.code})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            from apps.core.common.mixins import invalidate_viewset_cache
            invalidate_viewset_cache('unit', str(self.tenant_id) if self.tenant_id else None)
        except Exception:
            pass


class InventoryRelationship(BaseModel):
    RELATION_TYPE_CHOICES = (
        ('composition', 'Composition'),
        ('lockoff', 'Lock-Off'),
        ('virtual', 'Virtual Join'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='inventory_relationships')
    parent_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, related_name='child_relationships')
    child_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, related_name='parent_relationships')
    relation_type = models.CharField(max_length=32, choices=RELATION_TYPE_CHOICES, default='composition')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['parent_unit', 'child_unit'], name='unique_parent_child_relationship'),
        ]

    def __str__(self):
        return f"{self.parent_unit.name} -> {self.child_unit.name} ({self.relation_type})"


class AttributeDefinition(BaseModel):
    DATA_TYPE_CHOICES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('boolean', 'Boolean'),
        ('choice', 'Choice'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='attribute_definitions')
    code = models.CharField(max_length=64)
    data_type = models.CharField(max_length=32, choices=DATA_TYPE_CHOICES, default='text')
    allowed_values = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_attribute_code', condition=models.Q(tenant__isnull=False)),
            models.UniqueConstraint(fields=['code'], name='unique_system_attribute_code', condition=models.Q(tenant__isnull=True)),
        ]

    def __str__(self):
        return f"{self.code} ({self.data_type})"


class InventoryUnitAttribute(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='unit_attributes')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, null=True, blank=True, related_name='unit_type_attributes')
    inventory_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, null=True, blank=True, related_name='unit_attributes')
    attribute_definition = models.ForeignKey(AttributeDefinition, on_delete=models.PROTECT, related_name='unit_attributes')
    value = models.TextField()

    def clean(self):
        if not (self.inventory_unit_type or self.inventory_unit):
            raise ValidationError("Must target either an inventory unit type or a specific inventory unit.")
        if self.inventory_unit_type and self.inventory_unit:
            raise ValidationError("Cannot target both an inventory unit type and a specific inventory unit.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.inventory_unit_type.code if self.inventory_unit_type else self.inventory_unit.name
        return f"{target} -> {self.attribute_definition.code}: {self.value}"


class Amenity(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='amenities')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=64)
    chargeable = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True, default="")
    icon_name = models.CharField(max_length=64, default="wifi")

    class Meta:
        verbose_name_plural = 'Amenities'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_amenity_code', condition=models.Q(tenant__isnull=False)),
            models.UniqueConstraint(fields=['code'], name='unique_system_amenity_code', condition=models.Q(tenant__isnull=True)),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class InventoryUnitTypeAmenity(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='unit_type_amenities')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='type_amenities')
    amenity = models.ForeignKey(Amenity, on_delete=models.CASCADE, related_name='unit_type_amenities')

    class Meta:
        verbose_name_plural = 'Inventory Unit Type Amenities'
        constraints = [
            models.UniqueConstraint(fields=['inventory_unit_type', 'amenity'], name='unique_type_amenity_pair'),
        ]

    def __str__(self):
        return f"{self.inventory_unit_type.code} -> {self.amenity.code}"


class InventoryMedia(BaseModel):
    MEDIA_TYPE_CHOICES = (
        ('image', 'Image'),
        ('video', 'Video'),
        ('floorplan', 'Floor Plan'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='inventory_media')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, null=True, blank=True, related_name='type_media')
    inventory_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, null=True, blank=True, related_name='unit_media')
    media_url = models.URLField()
    media_type = models.CharField(max_length=32, choices=MEDIA_TYPE_CHOICES, default='image')
    sort_order = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Inventory Media'
        ordering = ['sort_order']

    def clean(self):
        if not (self.inventory_unit_type or self.inventory_unit):
            raise ValidationError("Must target either an inventory unit type or a specific inventory unit.")
        if self.inventory_unit_type and self.inventory_unit:
            raise ValidationError("Cannot target both an inventory unit type and a specific inventory unit.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.inventory_unit_type.code if self.inventory_unit_type else self.inventory_unit.name
        return f"{self.media_type} ({target})"


class Building(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='buildings')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='buildings')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'building'
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_building_code')
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Floor(BaseModel):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    floor_number = models.IntegerField()
    name = models.CharField(max_length=120)

    class Meta:
        db_table = 'floor'
        constraints = [
            models.UniqueConstraint(fields=['building', 'floor_number'], name='unique_building_floor_number')
        ]

    def __str__(self):
        return f"{self.name} (L{self.floor_number})"


class FloorPlan(BaseModel):
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='floor_plans')
    file_url = models.URLField(max_length=2048)
    version = models.CharField(max_length=32, default='1.0')

    class Meta:
        db_table = 'floor_plan'

    def __str__(self):
        return f"FloorPlan L{self.floor.floor_number} v{self.version}"

