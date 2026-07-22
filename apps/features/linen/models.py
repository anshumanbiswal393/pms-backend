from django.db import models
from django.core.exceptions import ValidationError
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property
from apps.features.inventory.models import InventoryUnit
from apps.features.reservations.models import Reservation


class LinenItem(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='linen_items')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='linen_items')
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=64)
    location = models.CharField(max_length=120, default='Housekeeping')
    total_qty = models.IntegerField(default=0)
    in_use_qty = models.IntegerField(default=0)
    in_wash_qty = models.IntegerField(default=0)
    damaged_qty = models.IntegerField(default=0)
    par_stock = models.IntegerField(default=0)
    status = models.CharField(max_length=32, choices=(('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')), default='ACTIVE')

    class Meta:
        db_table = 'linen_item'
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_linen_code')
        ]

    def get_stock_status(self):
        if self.total_qty <= 0:
            return 'OUT_OF_STOCK'
        if self.total_qty <= self.par_stock:
            return 'LOW_STOCK'
        return 'NORMAL'

    def clean(self):
        if self.total_qty < 0:
            raise ValidationError("Total quantity cannot be negative.")
        if self.in_use_qty < 0 or self.in_wash_qty < 0 or self.damaged_qty < 0:
            raise ValidationError("Stock quantity breakdown cannot be negative.")
        if self.par_stock < 0:
            raise ValidationError("Par stock quantity cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class LinenAssignment(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='linen_assignments')
    linen_item = models.ForeignKey(LinenItem, on_delete=models.CASCADE, related_name='assignments')
    inventory_unit = models.ForeignKey(InventoryUnit, on_delete=models.CASCADE, related_name='linen_assignments')
    quantity = models.IntegerField(default=1)

    class Meta:
        db_table = 'linen_assignment'

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Assigned quantity must be at least 1.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.linen_item.name} x {self.quantity} -> {self.inventory_unit.name}"


class LaundryRecord(BaseModel):
    STATUS_CHOICES = (
        ('SENT', 'Sent'),
        ('RETURNED', 'Returned'),
        ('PARTIALLY_RETURNED', 'Partially Returned'),
        ('LOST', 'Lost'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='laundry_records')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='laundry_records')
    linen_item = models.ForeignKey(LinenItem, on_delete=models.CASCADE, related_name='laundry_records')
    quantity_sent = models.IntegerField()
    quantity_returned = models.IntegerField(default=0)
    sent_date = models.DateField()
    expected_return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='SENT')

    class Meta:
        db_table = 'laundry_record'

    def clean(self):
        if self.quantity_sent < 1:
            raise ValidationError("Quantity sent to laundry must be at least 1.")
        if self.quantity_returned < 0:
            raise ValidationError("Quantity returned cannot be negative.")
        if self.quantity_returned > self.quantity_sent:
            raise ValidationError("Quantity returned cannot exceed quantity sent.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.linen_item.name} - Sent: {self.quantity_sent}, Returned: {self.quantity_returned} ({self.status})"


class GuestLaundryOrder(BaseModel):
    SERVICE_SPEED_CHOICES = (
        ('STANDARD', 'Standard'),
        ('EXPRESS', 'Express'),
    )
    STATUS_CHOICES = (
        ('PICKUP_REQUESTED', 'Pickup Requested'),
        ('RECEIVED_AT_LAUNDRY', 'Received at Laundry'),
        ('WASHING', 'Washing'),
        ('READY_FOR_DELIVERY', 'Ready for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='guest_laundry_orders')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='guest_laundry_orders')
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name='laundry_orders')
    room_number = models.CharField(max_length=32)
    guest_name = models.CharField(max_length=120)
    order_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    expected_pickup_time = models.DateTimeField(null=True, blank=True)
    service_speed = models.CharField(max_length=16, choices=SERVICE_SPEED_CHOICES, default='STANDARD')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='PICKUP_REQUESTED')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_posted_to_folio = models.BooleanField(default=False)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'guest_laundry_order'

    def save(self, *args, **kwargs):
        if not self.order_number:
            count = GuestLaundryOrder.objects.filter(tenant=self.tenant).count()
            self.order_number = f"LND-{1001 + count}"
        super().save(*args, **kwargs)

    def calculate_total(self):
        total = sum(item.total_price for item in self.items.all())
        self.total_amount = total
        GuestLaundryOrder.objects.filter(id=self.id).update(total_amount=total)
        return total

    def __str__(self):
        return f"{self.order_number} - {self.guest_name} (Room {self.room_number})"


class GuestLaundryOrderItem(BaseModel):
    order = models.ForeignKey(GuestLaundryOrder, on_delete=models.CASCADE, related_name='items')
    category = models.CharField(max_length=64, default='Garment')
    item_name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(default=1)
    service = models.CharField(max_length=64, default='Wash & Fold')
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'guest_laundry_order_item'

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)
        if self.order_id:
            self.order.calculate_total()

    def __str__(self):
        return f"{self.quantity}x {self.item_name} ({self.service})"


class LaundryMachine(BaseModel):
    MACHINE_TYPE_CHOICES = (
        ('WASHER', 'Washer'),
        ('DRYER', 'Dryer'),
        ('IRON_PRESS', 'Iron Press'),
    )
    STATUS_CHOICES = (
        ('OPERATING', 'Operating'),
        ('IDLE', 'Idle'),
        ('MAINTENANCE', 'Maintenance'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='laundry_machines')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='laundry_machines')
    name = models.CharField(max_length=120)
    machine_type = models.CharField(max_length=32, choices=MACHINE_TYPE_CHOICES, default='WASHER')
    capacity_kg = models.CharField(max_length=32, default='50kg')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='IDLE')

    class Meta:
        db_table = 'laundry_machine'

    def __str__(self):
        return f"{self.name} ({self.status})"
