import builtins
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property
from apps.features.inventory.models import InventoryUnitType, InventoryUnit
from apps.features.crm.models import GuestProfile

# Global Choices
GROUP_BLOCK_TYPE_CHOICES = (
    ('Corporate Booking', 'Corporate Booking'),
    ('Wedding Block', 'Wedding Block'),
    ('Conference Block', 'Conference Block'),
    ('Tour Group', 'Tour Group'),
)
GROUP_BLOCK_STATUS_CHOICES = (
    ('OPEN', 'Open'),
    ('CLOSED', 'Closed'),
    ('RELEASED', 'Released'),
    ('CANCELLED', 'Cancelled'),
)


class InventoryAvailability(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='availabilities')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField()
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='availabilities')
    
    allocated_count = models.IntegerField(default=0)
    sold_count = models.IntegerField(default=0)
    blocked_count = models.IntegerField(default=0)
    overbooking_limit = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Inventory Availabilities'
        constraints = [
            models.UniqueConstraint(fields=['property', 'date', 'inventory_unit_type'], name='unique_property_date_unittype'),
            models.CheckConstraint(condition=models.Q(allocated_count__gte=0), name='allocated_count_non_negative'),
            models.CheckConstraint(condition=models.Q(sold_count__gte=0), name='sold_count_non_negative'),
            models.CheckConstraint(condition=models.Q(blocked_count__gte=0), name='blocked_count_non_negative'),
            models.CheckConstraint(condition=models.Q(overbooking_limit__gte=0), name='overbooking_limit_non_negative'),
        ]
        indexes = [
            models.Index(fields=['property', 'inventory_unit_type', 'date'], name='idx_prop_unittype_date'),
            models.Index(fields=['property', 'date'], name='idx_prop_date'),
        ]

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        if self.inventory_unit_type.tenant != self.tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if self.allocated_count < 0:
            raise ValidationError("Allocated count cannot be negative.")
        if self.sold_count < 0:
            raise ValidationError("Sold count cannot be negative.")
        if self.blocked_count < 0:
            raise ValidationError("Blocked count cannot be negative.")
        if self.overbooking_limit < 0:
            raise ValidationError("Overbooking limit cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.property.name} - {self.inventory_unit_type.code} @ {self.date}: {self.allocated_count}"


class InventoryRestriction(BaseModel):
    RESTRICTION_TYPE_CHOICES = (
        ('CTA', 'Closed to Arrival'),
        ('CTD', 'Closed to Departure'),
        ('STOP_SELL', 'Stop Sell'),
        ('MIN_LOS', 'Minimum Length of Stay'),
        ('MAX_LOS', 'Maximum Length of Stay'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='restrictions')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='restrictions')
    date = models.DateField()
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, null=True, blank=True, related_name='restrictions')
    rate_plan_id = models.UUIDField(null=True, blank=True)
    restriction_type = models.CharField(max_length=32, choices=RESTRICTION_TYPE_CHOICES)
    restriction_value = models.IntegerField(null=True, blank=True)

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        if self.inventory_unit_type and self.inventory_unit_type.tenant != self.tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if self.restriction_type in ['MIN_LOS', 'MAX_LOS']:
            if self.restriction_value is None:
                raise ValidationError(f"Restriction value is required for restriction type {self.restriction_type}.")
            if self.restriction_value < 1:
                raise ValidationError("Restriction value must be greater than or equal to 1 for LOS controls.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        target = self.inventory_unit_type.code if self.inventory_unit_type else "All Types"
        return f"{self.property.name} - {target} @ {self.date}: {self.restriction_type}"


class InventoryHold(BaseModel):
    HOLD_TYPE_CHOICES = (
        ('CART', 'Shopping Cart Hold'),
        ('GROUP_ALLOTMENT', 'Group Allotment'),
        ('PROMOTIONAL', 'Promotional Hold'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('RELEASED', 'Released'),
        ('CONVERTED', 'Converted'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='holds')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='holds')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='holds')
    inventory_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, null=True, blank=True, related_name='holds')
    
    hold_type = models.CharField(max_length=32, choices=HOLD_TYPE_CHOICES, default='CART')
    quantity = models.IntegerField(default=1)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='ACTIVE')

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Hold quantity must be greater than or equal to 1.")
        if not self.expires_at:
            raise ValidationError("Expiration timestamp is required.")
        if self.inventory_unit and self.inventory_unit.inventory_unit_type != self.inventory_unit_type:
            raise ValidationError("Target inventory unit type must match the specific inventory unit's type.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.hold_type} Hold - {self.inventory_unit_type.code} (Qty: {self.quantity}, Status: {self.status})"


class GroupBlock(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='group_blocks')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='group_blocks')
    block_type = models.CharField(max_length=32, choices=GROUP_BLOCK_TYPE_CHOICES, default='Wedding Block')
    name = models.CharField(max_length=120)
    cutoff_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=GROUP_BLOCK_STATUS_CHOICES, default='OPEN')
    total_rooms = models.IntegerField(default=0)
    pickup_rooms = models.IntegerField(default=0)
    released_rooms = models.IntegerField(default=0)
    contracted_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Fields for detailed mapping
    code = models.CharField(max_length=64, default="", blank=True)
    contact_name = models.CharField(max_length=120, default="", blank=True)
    contact_email = models.EmailField(default="", blank=True)
    contact_phone = models.CharField(max_length=32, default="", blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    release_date = models.DateField(null=True, blank=True)
    pickup_target = models.CharField(max_length=120, default="", blank=True)
    pickup_location = models.CharField(max_length=255, default="", blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_method = models.CharField(max_length=64, default="", blank=True)
    payment_remark = models.CharField(max_length=255, default="", blank=True)
    id_type = models.CharField(max_length=64, default="", blank=True)
    id_number = models.CharField(max_length=64, default="", blank=True)
    address = models.TextField(default="", blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(block_type__in=[c[0] for c in GROUP_BLOCK_TYPE_CHOICES]),
                name='availability_group_block_type_check'
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[s[0] for s in GROUP_BLOCK_STATUS_CHOICES]),
                name='availability_group_block_status_check'
            ),
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_availability_group_block_code')
        ]

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Start date cannot be after end date.")
        if self.release_date and self.end_date and self.release_date > self.end_date:
            raise ValidationError("Release date cannot be after end date.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.block_type}) - {self.status}"


class GroupBlockAllocation(BaseModel):
    group_block = models.ForeignKey(GroupBlock, on_delete=models.CASCADE, related_name='allocations')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='group_block_allocations')
    date = models.DateField()
    allocated_qty = models.IntegerField(default=0)
    picked_up_qty = models.IntegerField(default=0)

    class Meta:
        db_table = 'group_block_allocation'
        constraints = [
            models.UniqueConstraint(fields=['group_block', 'inventory_unit_type', 'date'], name='unique_block_unittype_date')
        ]

    def clean(self):
        if self.allocated_qty < 0:
            raise ValidationError("Allocated quantity cannot be negative.")
        if self.picked_up_qty < 0:
            raise ValidationError("Picked up quantity cannot be negative.")
        if self.picked_up_qty > self.allocated_qty:
            raise ValidationError("Picked up quantity cannot exceed allocated quantity.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.group_block.name} - {self.inventory_unit_type.code} @ {self.date}: {self.allocated_qty}"


class Channel(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='channels')
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class ChannelAllocation(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='channel_allocations')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='channel_allocations')
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, null=True, blank=True, related_name='allocations')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='channel_allocations')
    date = models.DateField()
    allocated_qty = models.IntegerField(default=0)
    sold_qty = models.IntegerField(default=0)

    class Meta:
        db_table = 'channel_allocation'
        constraints = [
            models.UniqueConstraint(fields=['property', 'channel', 'inventory_unit_type', 'date'], name='unique_channel_allocation_key')
        ]

    @builtins.property
    def remaining_qty(self):
        return max(0, self.allocated_qty - self.sold_qty)

    def clean(self):
        if self.allocated_qty < 0:
            raise ValidationError("Allocated quantity cannot be negative.")
        if self.sold_qty < 0:
            raise ValidationError("Sold quantity cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        channel_name = self.channel.name if self.channel else "No Channel"
        return f"{channel_name} - {self.inventory_unit_type.code} @ {self.date}: {self.allocated_qty}"


class DynamicAvailabilityRule(BaseModel):
    RULE_TYPE_CHOICES = (
        ('BLACKOUT', 'Blackout'),
        ('HOLIDAY', 'Holiday'),
        ('EVENT', 'Event'),
        ('SEASONAL', 'Seasonal'),
        ('FREEZE', 'Freeze'),
    )
    RULE_SCOPE_CHOICES = (
        ('GLOBAL', 'Global'),
        ('PROPERTY', 'Property'),
        ('UNIT_TYPE', 'Unit Type'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='dynamic_availability_rules')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='dynamic_availability_rules')
    rule_type = models.CharField(max_length=32, choices=RULE_TYPE_CHOICES, default='SEASONAL')
    name = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField()
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, null=True, blank=True, related_name='dynamic_availability_rules')
    is_active = models.BooleanField(default=True)
    parameters = models.JSONField(default=dict, blank=True)

    # Added execution variables
    priority = models.IntegerField(default=1)
    evaluation_order = models.IntegerField(default=1)
    enabled = models.BooleanField(default=True)
    rule_scope = models.CharField(max_length=32, choices=RULE_SCOPE_CHOICES, default='PROPERTY')

    class Meta:
        db_table = 'dynamic_availability_rule'

    def clean(self):
        if self.start_date > self.end_date:
            raise ValidationError("Start date cannot be after end date.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.rule_type}) - Priority: {self.priority}"


class WaitlistEntry(BaseModel):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONVERTED', 'Converted'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='waitlist_entries')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='waitlist_entries')
    guest = models.ForeignKey(GuestProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='waitlist_entries')
    email_snapshot = models.EmailField(default="", blank=True)
    phone_snapshot = models.CharField(max_length=32, default="", blank=True)
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='waitlist_entries')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    priority = models.IntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='PENDING')

    # Traceability fields
    converted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_waitlists')
    converted_at = models.DateTimeField(null=True, blank=True)
    reservation = models.ForeignKey('reservations.Reservation', on_delete=models.SET_NULL, null=True, blank=True, related_name='waitlist_entries')

    class Meta:
        db_table = 'waitlist_entry'

    def clean(self):
        if self.check_in_date >= self.check_out_date:
            raise ValidationError("Check-in date must be before check-out date.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        name = f"{self.guest.first_name} {self.guest.last_name}" if self.guest else "Unknown Guest"
        return f"Waitlist: {name} -> {self.inventory_unit_type.code} ({self.status})"


class InventorySharedPool(BaseModel):
    ALLOCATION_STRATEGY_CHOICES = (
        ('EXCLUSIVE', 'Exclusive'),
        ('SHARED', 'Shared'),
        ('PRIORITY', 'Priority'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='shared_pools')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='shared_pools')
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    total_capacity = models.IntegerField(default=1)
    
    # Strategy and capacity buckets
    allocation_strategy = models.CharField(max_length=32, choices=ALLOCATION_STRATEGY_CHOICES, default='SHARED')
    effective_capacity = models.IntegerField(default=1)
    reserved_capacity = models.IntegerField(default=0)
    available_capacity = models.IntegerField(default=1)

    class Meta:
        db_table = 'inventory_shared_pool'
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_shared_pool_code')
        ]

    def clean(self):
        if self.total_capacity < 1:
            raise ValidationError("Total capacity must be at least 1.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class InventorySharedPoolUnitType(BaseModel):
    pool = models.ForeignKey(InventorySharedPool, on_delete=models.CASCADE, related_name='unit_types')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='shared_pools')
    weight = models.IntegerField(default=1)

    class Meta:
        db_table = 'inventory_shared_pool_unit_type'
        constraints = [
            models.UniqueConstraint(fields=['pool', 'inventory_unit_type'], name='unique_pool_unittype_pair')
        ]

    def clean(self):
        if self.weight < 1:
            raise ValidationError("Weight must be at least 1.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.pool.code} -> {self.inventory_unit_type.code} (wt: {self.weight})"
