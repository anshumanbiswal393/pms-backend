import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from apps.core.common.models import BaseModel

class Outlet(BaseModel):
    """
    Physical or virtual restaurant, cloud kitchen, bar, or dining outlet
    operating within a property under a tenant.
    """
    OUTLET_TYPE_CHOICES = (
        ('PRIMARY', 'Primary Dine-In Restaurant'),
        ('VIRTUAL', 'Cloud Kitchen / Virtual Brand'),
        ('HO', 'Head Office'),
        ('KITCHEN', 'Central Kitchen'),
        ('BAR', 'Bar & Cocktail Lounge'),
        ('ROOM_SERVICE', 'In-Room Dining / Room Service'),
        ('BANQUET', 'Banquet & Events'),
        ('CAFE', 'Bakery / Café'),
    )

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_outlets'
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_outlets'
    )
    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=120)
    outlet_type = models.CharField(
        max_length=32,
        choices=OUTLET_TYPE_CHOICES,
        default='PRIMARY'
    )
    cuisine = models.CharField(max_length=120, blank=True, null=True)
    fssai_license = models.CharField(max_length=64, blank=True, null=True)
    gstin = models.CharField(max_length=32, blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    service_charge_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00
    )
    default_cgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.50
    )
    default_sgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.50
    )
    default_vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00
    )
    currency = models.CharField(max_length=8, default='INR')
    is_active = models.BooleanField(default=True)
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
    meta_settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = ('property', 'code')
        verbose_name = 'POS Outlet'
        verbose_name_plural = 'POS Outlets'

    def __str__(self):
        return f"{self.name} ({self.code})"


class FloorSection(BaseModel):
    """
    Physical or themed section within an outlet (e.g., AC Dining, Garden, Rooftop).
    """
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='sections'
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=32, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('outlet', 'name')
        verbose_name = 'Floor Section'
        verbose_name_plural = 'Floor Sections'

    def __str__(self):
        return f"{self.outlet.name} - {self.name}"


class RestaurantTable(BaseModel):
    """
    Dining table with PAX capacity, live seating status, 2D floor coordinates,
    and unique QR code token for scan-and-order digital menu.
    """
    TABLE_STATUS_CHOICES = (
        ('VACANT', 'Vacant / Available'),
        ('OCCUPIED', 'Occupied / Dining'),
        ('BILLED', 'Billed / Payment Pending'),
        ('DIRTY', 'Dirty / Clearance Required'),
        ('RESERVED', 'Reserved'),
    )
    TABLE_SHAPE_CHOICES = (
        ('SQUARE', 'Square'),
        ('ROUND', 'Round'),
        ('RECTANGLE', 'Rectangle'),
    )

    section = models.ForeignKey(
        FloorSection,
        on_delete=models.CASCADE,
        related_name='tables'
    )
    table_number = models.CharField(max_length=32)
    capacity = models.PositiveIntegerField(default=4)
    min_capacity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=24,
        choices=TABLE_STATUS_CHOICES,
        default='VACANT'
    )
    shape = models.CharField(
        max_length=24,
        choices=TABLE_SHAPE_CHOICES,
        default='SQUARE'
    )
    pos_x = models.FloatField(default=0.0)
    pos_y = models.FloatField(default=0.0)
    width = models.FloatField(default=80.0)
    height = models.FloatField(default=80.0)
    qr_code_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    active_order_id = models.UUIDField(null=True, blank=True)
    active_waiter_name = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['table_number']
        unique_together = ('section', 'table_number')
        verbose_name = 'Restaurant Table'
        verbose_name_plural = 'Restaurant Tables'

    def __str__(self):
        return f"{self.section.name} - Table {self.table_number} ({self.status})"


class POSRegister(BaseModel):
    """
    Point of Sale physical or virtual billing register hardware binding.
    """
    REGISTER_TYPE_CHOICES = (
        ('BILLING_COUNTER', 'Main Billing Counter'),
        ('CAPTAIN_TABLET', 'Captain Tablet / Handheld'),
        ('KDS_SCREEN', 'Kitchen Display System'),
        ('BAR_TERMINAL', 'Bar Terminal'),
        ('SELF_KIOSK', 'Self-Service Kiosk'),
    )

    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='registers'
    )
    register_code = models.CharField(max_length=32)
    name = models.CharField(max_length=100)
    register_type = models.CharField(
        max_length=32,
        choices=REGISTER_TYPE_CHOICES,
        default='BILLING_COUNTER'
    )
    is_active = models.BooleanField(default=True)
    meta_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['register_code']
        unique_together = ('outlet', 'register_code')
        verbose_name = 'POS Register'
        verbose_name_plural = 'POS Registers'

    def __str__(self):
        return f"{self.outlet.name} - {self.name} ({self.register_code})"


class DeviceMapping(BaseModel):
    """
    Physical hardware device mapping and security binding to a POS Register.
    """
    DEVICE_PLATFORM_CHOICES = (
        ('WINDOWS', 'Windows Desktop'),
        ('ANDROID', 'Android Tablet/POS'),
        ('IOS', 'Apple iOS / iPadOS'),
        ('WEB', 'Web Browser'),
        ('LINUX', 'Linux Embedded'),
    )
    DEVICE_STATUS_CHOICES = (
        ('ONLINE', 'Online / Active'),
        ('OFFLINE', 'Offline'),
        ('SUSPENDED', 'Suspended'),
    )

    register = models.ForeignKey(
        POSRegister,
        on_delete=models.CASCADE,
        related_name='devices'
    )
    device_name = models.CharField(max_length=120)
    device_fingerprint = models.CharField(max_length=255, db_index=True)
    platform = models.CharField(
        max_length=24,
        choices=DEVICE_PLATFORM_CHOICES,
        default='WEB'
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=64, null=True, blank=True)
    app_version = models.CharField(max_length=32, blank=True, null=True)
    status = models.CharField(
        max_length=24,
        choices=DEVICE_STATUS_CHOICES,
        default='OFFLINE'
    )
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    is_authorized = models.BooleanField(default=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Device Mapping'
        verbose_name_plural = 'Device Mappings'

    def __str__(self):
        return f"{self.device_name} ({self.platform}) - {self.status}"


class TaxProfile(BaseModel):
    """
    POS-owned tax profile for F&B items (separate from room/folio TaxRate masters).
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_tax_profiles',
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_tax_profiles',
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=120)
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_inclusive = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'code')
        verbose_name = 'POS Tax Profile'
        verbose_name_plural = 'POS Tax Profiles'

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class MenuCategory(BaseModel):
    """Menu category scoped to a POS outlet (e.g. Starters, Main Course)."""
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='menu_categories',
    )
    code = models.CharField(max_length=32, blank=True, null=True)
    name = models.CharField(max_length=120)
    online_display_name = models.CharField(max_length=160, blank=True, null=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )
    sort_order = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('outlet', 'name')
        verbose_name = 'Menu Category'
        verbose_name_plural = 'Menu Categories'

    def __str__(self):
        return f"{self.outlet.name} · {self.name}"


class MenuItem(BaseModel):
    """Sellable F&B menu item for POS billing / room service catalog."""
    ITEM_TYPE_CHOICES = (
        ('VEG', 'Veg'),
        ('NON_VEG', 'Non-Veg'),
        ('EGG', 'Egg'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
    )

    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='menu_items',
    )
    category = models.ForeignKey(
        MenuCategory,
        on_delete=models.PROTECT,
        related_name='items',
    )
    tax_profile = models.ForeignKey(
        TaxProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='menu_items',
    )
    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=160)
    online_display_name = models.CharField(max_length=200, blank=True, null=True)
    item_type = models.CharField(
        max_length=16,
        choices=ITEM_TYPE_CHOICES,
        default='VEG',
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='ACTIVE',
        db_index=True,
    )
    images = models.JSONField(default=list, blank=True)
    base_menu = models.BooleanField(default=True)
    zomato = models.BooleanField(default=True)
    swiggy = models.BooleanField(default=True)
    direct = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    next_available_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('outlet', 'code')
        verbose_name = 'Menu Item'
        verbose_name_plural = 'Menu Items'
        indexes = [
            models.Index(fields=['outlet', 'status']),
            models.Index(fields=['category', 'status']),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def tax_rate(self):
        if self.tax_profile_id and self.tax_profile:
            return self.tax_profile.rate
        return self.outlet.default_cgst_rate + self.outlet.default_sgst_rate


class MenuVariant(BaseModel):
    """Size / portion variant with its own price (Half/Full, 180ml/750ml, etc.)."""
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    name = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('menu_item', 'name')
        verbose_name = 'Menu Variant'
        verbose_name_plural = 'Menu Variants'

    def __str__(self):
        return f"{self.menu_item.code} · {self.name}"


class ModifierGroup(BaseModel):
    """Addon / modifier group (e.g. Extra Toppings, Spice Level)."""
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='modifier_groups',
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, blank=True, null=True)
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(default=1)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    menu_items = models.ManyToManyField(
        MenuItem,
        blank=True,
        related_name='modifier_groups',
    )

    class Meta:
        ordering = ['name']
        unique_together = ('outlet', 'name')
        verbose_name = 'Modifier Group'
        verbose_name_plural = 'Modifier Groups'

    def __str__(self):
        return f"{self.outlet.name} · {self.name}"


class ModifierOption(BaseModel):
    """Selectable option inside a modifier group."""
    group = models.ForeignKey(
        ModifierGroup,
        on_delete=models.CASCADE,
        related_name='options',
    )
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = ('group', 'name')
        verbose_name = 'Modifier Option'
        verbose_name_plural = 'Modifier Options'

    def __str__(self):
        return f"{self.group.name} · {self.name}"


class SpecialNote(BaseModel):
    """Kitchen / captain special notes (Parcel, Jain, Spice levels)."""
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='special_notes',
        null=True,
        blank=True,
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_special_notes',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    is_available = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Special Note'
        verbose_name_plural = 'Special Notes'

    def __str__(self):
        return self.name


class POSOrder(BaseModel):
    """
    POS F&B order (dine-in / takeaway / room service / delivery).
    Status flow: PLACED → PREPARED → SETTLED | CANCELLED.
    """
    ORDER_TYPE_CHOICES = (
        ('DINE_IN', 'Dine In'),
        ('TAKEAWAY', 'Takeaway'),
        ('ROOM_SERVICE', 'Room Service'),
        ('DELIVERY', 'Delivery'),
        ('ONLINE', 'Online Aggregator'),
    )
    STATUS_CHOICES = (
        ('PLACED', 'Placed'),
        ('PREPARED', 'Prepared'),
        ('SETTLED', 'Settled'),
        ('CANCELLED', 'Cancelled'),
    )
    PAYMENT_MODE_CHOICES = (
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('UPI', 'UPI'),
        ('ROOM_CHARGE', 'Room Charge'),
        ('SPLIT', 'Split'),
        ('DUE', 'Due'),
    )

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_orders',
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_orders',
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='orders',
    )
    order_number = models.CharField(max_length=32, db_index=True)
    order_type = models.CharField(
        max_length=24,
        choices=ORDER_TYPE_CHOICES,
        default='DINE_IN',
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='PLACED',
        db_index=True,
    )
    table = models.ForeignKey(
        RestaurantTable,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_orders',
    )
    table_number = models.CharField(max_length=32, blank=True, null=True)
    section_name = models.CharField(max_length=100, blank=True, null=True)
    room_unit_id = models.UUIDField(null=True, blank=True, db_index=True)
    room_number = models.CharField(max_length=32, blank=True, null=True)
    reservation_id = models.UUIDField(null=True, blank=True, db_index=True)
    folio_id = models.UUIDField(null=True, blank=True, db_index=True)
    guest_name = models.CharField(max_length=160, blank=True, null=True)
    guest_phone = models.CharField(max_length=32, blank=True, null=True)
    waiter_name = models.CharField(max_length=100, blank=True, null=True)
    pax = models.PositiveSmallIntegerField(default=1)
    order_note = models.TextField(blank=True, null=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_mode = models.CharField(
        max_length=24,
        choices=PAYMENT_MODE_CHOICES,
        blank=True,
        null=True,
    )
    kot_sequence = models.PositiveIntegerField(default=0)
    placed_at = models.DateTimeField(null=True, blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-placed_at', '-created_at']
        unique_together = ('property', 'order_number')
        verbose_name = 'POS Order'
        verbose_name_plural = 'POS Orders'
        indexes = [
            models.Index(fields=['outlet', 'status']),
            models.Index(fields=['property', 'status']),
            models.Index(fields=['status', 'placed_at']),
        ]

    def __str__(self):
        return f"{self.order_number} ({self.status})"

    def is_open(self):
        """True while order can still receive KOT / item edits."""
        return self.status in ('PLACED', 'PREPARED')


class POSOrderItem(BaseModel):
    """Line item snapshot on a POS order."""
    order = models.ForeignKey(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_lines',
    )
    variant = models.ForeignKey(
        MenuVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_lines',
    )
    item_code = models.CharField(max_length=32, blank=True, null=True)
    item_name = models.CharField(max_length=200)
    category_name = models.CharField(max_length=120, blank=True, null=True)
    variant_name = models.CharField(max_length=80, blank=True, null=True)
    item_type = models.CharField(max_length=16, blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_void = models.BooleanField(default=False)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        verbose_name = 'POS Order Item'
        verbose_name_plural = 'POS Order Items'

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"


class KOTTicket(BaseModel):
    """Kitchen Order Ticket generated from a POS order (initial or modified)."""
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PREPARING', 'Preparing'),
        ('READY', 'Ready'),
        ('SERVED', 'Served'),
        ('CANCELLED', 'Cancelled'),
    )

    order = models.ForeignKey(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='kot_tickets',
    )
    sequence = models.PositiveIntegerField(default=1)
    kot_number = models.CharField(max_length=48, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='PREPARING',
        db_index=True,
    )
    is_modified = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-sent_at', '-created_at']
        unique_together = ('order', 'sequence')
        verbose_name = 'KOT Ticket'
        verbose_name_plural = 'KOT Tickets'

    def __str__(self):
        return self.kot_number


class KOTTicketItem(BaseModel):
    """Line on a KOT ticket (may represent a delta for modified KOTs)."""
    ticket = models.ForeignKey(
        KOTTicket,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order_item = models.ForeignKey(
        POSOrderItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='kot_lines',
    )
    item_name = models.CharField(max_length=200)
    item_code = models.CharField(max_length=32, blank=True, null=True)
    variant_name = models.CharField(max_length=80, blank=True, null=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    notes = models.CharField(max_length=255, blank=True, null=True)
    is_void = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'created_at']
        verbose_name = 'KOT Ticket Item'
        verbose_name_plural = 'KOT Ticket Items'

    def __str__(self):
        return f"{self.item_name} x {self.quantity}"


class POSOrderStatusHistory(BaseModel):
    """Audit trail of POS order status transitions."""
    order = models.ForeignKey(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='status_history',
    )
    from_status = models.CharField(max_length=16, blank=True, null=True)
    to_status = models.CharField(max_length=16)
    note = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'POS Order Status History'
        verbose_name_plural = 'POS Order Status Histories'

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status} → {self.to_status}"


class POSPayment(BaseModel):
    """Payment tender line against a POS order (cash/card/upi/room charge/due/split)."""
    MODE_CHOICES = POSOrder.PAYMENT_MODE_CHOICES
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CAPTURED', 'Captured'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    )

    order = models.ForeignKey(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    mode = models.CharField(max_length=24, choices=MODE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='CAPTURED')
    reference = models.CharField(max_length=120, blank=True, null=True)
    folio_id = models.UUIDField(null=True, blank=True, db_index=True)
    folio_transaction_id = models.UUIDField(null=True, blank=True, db_index=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'POS Payment'
        verbose_name_plural = 'POS Payments'

    def __str__(self):
        return f"{self.mode} {self.amount} on {self.order.order_number}"


class FolioPostingLog(BaseModel):
    """
    Idempotent audit log for Room Charge posts to PMS GuestFolio.
    Unique idempotency_key prevents double folio charges on UI retries.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    )

    order = models.ForeignKey(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='folio_postings',
    )
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    reservation_id = models.UUIDField(null=True, blank=True)
    folio_id = models.UUIDField(null=True, blank=True)
    folio_transaction_id = models.UUIDField(null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    charge_code = models.CharField(max_length=32, blank=True, null=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='PENDING')
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Folio Posting Log'
        verbose_name_plural = 'Folio Posting Logs'

    def __str__(self):
        return f"{self.idempotency_key} ({self.status})"


class POSDueBill(BaseModel):
    """
    Pending / partial payment ledger (Pending Payments UI).
    Created when an order is settled as DUE or only partially paid.
    """
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('SETTLED', 'Settled'),
    )

    order = models.OneToOneField(
        POSOrder,
        on_delete=models.CASCADE,
        related_name='due_bill',
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_due_bills',
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_due_bills',
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='due_bills',
    )
    bill_number = models.CharField(max_length=48, db_index=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )
    due_date = models.DateField(null=True, blank=True)
    settlement_mode = models.CharField(max_length=24, blank=True, null=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('property', 'bill_number')
        verbose_name = 'POS Due Bill'
        verbose_name_plural = 'POS Due Bills'
        indexes = [
            models.Index(fields=['outlet', 'status']),
            models.Index(fields=['property', 'status']),
        ]

    def __str__(self):
        return f"{self.bill_number} ({self.status}) due={self.due_amount}"

    def recompute_status(self):
        if self.due_amount <= 0:
            self.status = 'SETTLED'
            self.due_amount = Decimal('0.00')
        elif self.paid_amount > 0:
            self.status = 'PARTIAL'
        else:
            self.status = 'PENDING'


class POSDayClose(BaseModel):
    """Day-end close snapshot for an outlet / property business date."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_day_closes',
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_day_closes',
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='day_closes',
        null=True,
        blank=True,
    )
    business_date = models.DateField(db_index=True)
    order_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cash_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    card_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    upi_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    room_charge_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    due_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    split_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    open_due_count = models.PositiveIntegerField(default=0)
    open_due_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-business_date']
        unique_together = ('property', 'outlet', 'business_date')
        verbose_name = 'POS Day Close'
        verbose_name_plural = 'POS Day Closes'

    def __str__(self):
        return f"DayClose {self.business_date} ({'CLOSED' if self.is_closed else 'OPEN'})"


class POSStockItem(BaseModel):
    """
    POS-owned F&B stock SKU (not hotel room inventory).
    Optional external_sku_ref can later link to a PMS inventory item.
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_stock_items',
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_stock_items',
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        related_name='stock_items',
        null=True,
        blank=True,
    )
    ITEM_KIND_CHOICES = (
        ('RAW', 'Raw Material'),
        ('PREPARED', 'Prepared / Semi-finished'),
    )

    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=120, blank=True, null=True)
    unit = models.CharField(max_length=32, default='Kg')
    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    par_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    reorder_level = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    item_kind = models.CharField(max_length=16, choices=ITEM_KIND_CHOICES, default='RAW')
    is_favorite = models.BooleanField(default=False)
    external_sku_ref = models.CharField(max_length=64, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        unique_together = ('property', 'code')
        verbose_name = 'POS Stock Item'
        verbose_name_plural = 'POS Stock Items'

    def __str__(self):
        return f"{self.code} · {self.name} ({self.quantity_on_hand} {self.unit})"


class POSRecipe(BaseModel):
    """Recipe header linking a menu item to ingredient BOM lines."""
    menu_item = models.OneToOneField(
        MenuItem,
        on_delete=models.CASCADE,
        related_name='recipe',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=160, blank=True, null=True)
    category = models.CharField(max_length=120, blank=True, null=True)
    yield_qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    yield_unit = models.CharField(max_length=32, default='portion')
    prep_time_minutes = models.PositiveIntegerField(default=15)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'POS Recipe'
        verbose_name_plural = 'POS Recipes'

    def __str__(self):
        return self.name or f"Recipe · {self.menu_item_id}"


class POSRecipeIngredient(BaseModel):
    """BOM line: quantity of a stock item consumed per recipe portion."""
    recipe = models.ForeignKey(
        POSRecipe,
        on_delete=models.CASCADE,
        related_name='ingredients',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='recipe_lines',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=32, blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'created_at']
        unique_together = ('recipe', 'stock_item')
        verbose_name = 'POS Recipe Ingredient'
        verbose_name_plural = 'POS Recipe Ingredients'

    def __str__(self):
        return f"{self.stock_item_id} x {self.quantity}"


class POSStockMovement(BaseModel):
    """Stock ledger movement (purchase in, settle deduct, wastage, adjust)."""
    MOVEMENT_CHOICES = (
        ('IN', 'Stock In'),
        ('OUT', 'Stock Out'),
        ('SETTLE_DEDUCT', 'Order Settle Deduction'),
        ('SETTLE_REVERSE', 'Order Settle Reverse'),
        ('WASTAGE', 'Wastage'),
        ('ADJUST', 'Adjustment'),
        ('OPENING', 'Opening Stock'),
        ('CLOSING', 'Closing Count Variance'),
        ('PURCHASE_RETURN', 'Purchase Return'),
    )

    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.CASCADE,
        related_name='movements',
    )
    movement_type = models.CharField(max_length=24, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    balance_after = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    reference_type = models.CharField(max_length=32, blank=True, null=True)
    reference_id = models.UUIDField(null=True, blank=True, db_index=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'POS Stock Movement'
        verbose_name_plural = 'POS Stock Movements'
        indexes = [
            models.Index(fields=['stock_item', 'movement_type']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} → {self.stock_item_id}"


class AggregatorWebhookLog(BaseModel):
    """Inbound aggregator webhook audit (Zomato/Swiggy stubs)."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_aggregator_webhooks',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_aggregator_webhooks',
        null=True,
        blank=True,
    )
    provider = models.CharField(max_length=32, db_index=True)
    event_type = models.CharField(max_length=64, blank=True, null=True)
    external_order_id = models.CharField(max_length=128, blank=True, null=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=24, default='RECEIVED')
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Aggregator Webhook Log'
        verbose_name_plural = 'Aggregator Webhook Logs'

    def __str__(self):
        return f"{self.provider} {self.event_type or ''} ({self.status})"


class ProductionRecipe(BaseModel):
    """
    Food preparation recipe / standard formula for converting raw materials into
    semi-finished preparations (e.g. gravies, pizza dough, marinations, bases).
    """
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_production_recipes',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_production_recipes',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_recipes',
    )
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=100, default='Gravies & Sauces')
    output_unit = models.CharField(max_length=32, default='Liter (L)')
    expected_yield = models.DecimalField(max_digits=12, decimal_places=3, default=1.0)
    standard_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    shelf_life_days = models.PositiveIntegerField(default=3)
    instructions = models.TextField(blank=True, null=True)
    output_stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='produced_by_recipes',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Production Recipe'
        verbose_name_plural = 'Production Recipes'

    def __str__(self):
        return f"{self.code} · {self.name} ({self.expected_yield} {self.output_unit})"


class ProductionRecipeIngredient(BaseModel):
    """
    Ingredient BOM line for a food preparation recipe.
    """
    recipe = models.ForeignKey(
        ProductionRecipe,
        on_delete=models.CASCADE,
        related_name='ingredients',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='production_recipe_lines',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=32, blank=True, null=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'created_at']
        unique_together = ('recipe', 'stock_item')
        verbose_name = 'Production Recipe Ingredient'
        verbose_name_plural = 'Production Recipe Ingredients'

    def __str__(self):
        return f"{self.recipe.name} -> {self.stock_item.name} ({self.quantity} {self.unit})"


class ProductionBatch(BaseModel):
    """
    Actual logged execution of a food preparation batch.
    Deducts raw materials from stock and optionally increments the produced item.
    """
    STATUS_CHOICES = (
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('DISCARDED', 'Discarded'),
    )

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_production_batches',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_production_batches',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='production_batches',
    )
    batch_number = models.CharField(max_length=64, db_index=True)
    recipe = models.ForeignKey(
        ProductionRecipe,
        on_delete=models.PROTECT,
        related_name='batches',
    )
    preparation_date = models.DateField(default=timezone.now)
    yield_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    yield_unit = models.CharField(max_length=32)
    operator = models.CharField(max_length=128, blank=True, null=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='COMPLETED')
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    notes = models.TextField(blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    is_stock_deducted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Production Batch'
        verbose_name_plural = 'Production Batches'

    def __str__(self):
        return f"{self.batch_number} · {self.recipe.name} ({self.yield_quantity} {self.yield_unit})"


class ProductionBatchIngredient(BaseModel):
    """
    Raw material consumed for a specific production batch.
    """
    batch = models.ForeignKey(
        ProductionBatch,
        on_delete=models.CASCADE,
        related_name='ingredients_consumed',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='batch_deductions',
    )
    standard_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    actual_quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=32, blank=True, null=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Production Batch Ingredient'
        verbose_name_plural = 'Production Batch Ingredients'

    def __str__(self):
        return f"{self.batch.batch_number} -> {self.stock_item.name} ({self.actual_quantity} {self.unit})"


class POSVendor(BaseModel):
    """Supplier / vendor for raw materials and inventory purchases."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_vendors',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_vendors',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=160)
    contact_person = models.CharField(max_length=120, blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    category = models.CharField(max_length=80, blank=True, null=True)
    gstin = models.CharField(max_length=32, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'POS Vendor'
        verbose_name_plural = 'POS Vendors'

    def __str__(self):
        return self.name


class POSPurchaseInvoice(BaseModel):
    """
    Unified purchase invoice bill for incoming inventory/raw materials.
    Tracks total amount, paid amount, balance, and payment status (PAID/UNPAID/PARTIAL).
    """
    PAYMENT_STATUS_CHOICES = (
        ('PAID', 'Done'),
        ('UNPAID', 'Pending'),
        ('PARTIAL', 'Partial'),
    )
    STATUS_CHOICES = (
        ('COMPLETED', 'Completed'),
        ('DRAFT', 'Draft'),
        ('CANCELLED', 'Cancelled'),
    )

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_purchases',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_purchases',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchases',
    )
    invoice_no = models.CharField(max_length=64, db_index=True)
    vendor = models.ForeignKey(
        POSVendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
    )
    vendor_name = models.CharField(max_length=160)
    purchase_date = models.DateField(default=timezone.now)
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=24, choices=PAYMENT_STATUS_CHOICES, default='PAID')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='COMPLETED')
    item_count = models.IntegerField(default=1)
    notes = models.TextField(blank=True, null=True)
    items_payload = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-purchase_date', '-created_at']
        verbose_name = 'POS Purchase Invoice'
        verbose_name_plural = 'POS Purchase Invoices'

    def __str__(self):
        return f"{self.invoice_no} · {self.vendor_name} (₹{self.total_amount})"


class POSPurchasePayment(BaseModel):
    """Individual payment record made towards a purchase bill."""
    PAYMENT_METHOD_CHOICES = (
        ('CASH', 'Cash'),
        ('UPI', 'UPI / QR'),
        ('BANK_TRANSFER', 'Bank Transfer / NEFT'),
        ('CHEQUE', 'Cheque'),
        ('CARD', 'Card'),
    )

    invoice = models.ForeignKey(
        POSPurchaseInvoice,
        on_delete=models.CASCADE,
        related_name='payments',
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=32, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    payment_date = models.DateField(default=timezone.now)
    reference_no = models.CharField(max_length=64, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = 'POS Purchase Payment'
        verbose_name_plural = 'POS Purchase Payments'

    def __str__(self):
        return f"{self.invoice.invoice_no} payment of ₹{self.amount} via {self.payment_method}"


class POSPurchaseLine(BaseModel):
    """Normalized purchase invoice line used to IN stock."""
    invoice = models.ForeignKey(
        POSPurchaseInvoice,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='purchase_lines',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=32, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'POS Purchase Line'
        verbose_name_plural = 'POS Purchase Lines'


class POSPurchaseOrder(BaseModel):
    """Supplier purchase order. Stock is added only when received as an invoice."""
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SENT', 'Sent'),
        ('APPROVED', 'Approved'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_purchase_orders',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_purchase_orders',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    po_number = models.CharField(max_length=64, db_index=True)
    vendor = models.ForeignKey(
        POSVendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    vendor_name = models.CharField(max_length=160)
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    item_count = models.IntegerField(default=0)
    estimated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='SENT')
    notes = models.TextField(blank=True, null=True)
    received_invoice = models.ForeignKey(
        POSPurchaseInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_purchase_orders',
    )

    class Meta:
        ordering = ['-order_date', '-created_at']
        verbose_name = 'POS Purchase Order'
        verbose_name_plural = 'POS Purchase Orders'

    def __str__(self):
        return f"{self.po_number} · {self.vendor_name}"


class POSPurchaseOrderLine(BaseModel):
    purchase_order = models.ForeignKey(
        POSPurchaseOrder,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='purchase_order_lines',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=32, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'POS Purchase Order Line'
        verbose_name_plural = 'POS Purchase Order Lines'


class POSPurchaseReturn(BaseModel):
    """Debit note that OUTs previously received stock back to the vendor."""
    STATUS_CHOICES = (
        ('ISSUED', 'Issued'),
        ('APPROVED', 'Approved'),
        ('SETTLED', 'Settled'),
        ('CANCELLED', 'Cancelled'),
    )
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_purchase_returns',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_purchase_returns',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_returns',
    )
    debit_note_no = models.CharField(max_length=64, db_index=True)
    vendor = models.ForeignKey(
        POSVendor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_returns',
    )
    vendor_name = models.CharField(max_length=160)
    return_date = models.DateField(default=timezone.now)
    reason = models.CharField(max_length=80, default='Damaged / Expired')
    item_count = models.IntegerField(default=0)
    return_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='ISSUED')
    notes = models.TextField(blank=True, null=True)
    is_stock_reversed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-return_date', '-created_at']
        verbose_name = 'POS Purchase Return'
        verbose_name_plural = 'POS Purchase Returns'

    def __str__(self):
        return f"{self.debit_note_no} · {self.vendor_name}"


class POSPurchaseReturnLine(BaseModel):
    purchase_return = models.ForeignKey(
        POSPurchaseReturn,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='purchase_return_lines',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=32, blank=True, null=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'POS Purchase Return Line'
        verbose_name_plural = 'POS Purchase Return Lines'


class POSWastage(BaseModel):
    """Logged spoilage / overcook / handling loss. Deducts stock via WASTAGE movement."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_wastage',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_wastage',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wastage_entries',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='wastage_entries',
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.CharField(max_length=32, blank=True, null=True)
    reason = models.CharField(max_length=120, default='Spoiled / Overripe')
    approved_by = models.CharField(max_length=120, blank=True, null=True)
    wastage_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    cost_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_stock_deducted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-wastage_date', '-created_at']
        verbose_name = 'POS Wastage'
        verbose_name_plural = 'POS Wastage'


class POSClosingCount(BaseModel):
    """Daily physical stock count. Variance is posted as CLOSING ADJUST."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_closing_counts',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_closing_counts',
        null=True,
        blank=True,
    )
    outlet = models.ForeignKey(
        Outlet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closing_counts',
    )
    business_date = models.DateField()
    notes = models.TextField(blank=True, null=True)
    is_posted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-business_date']
        unique_together = ('property', 'outlet', 'business_date')
        verbose_name = 'POS Closing Count'
        verbose_name_plural = 'POS Closing Counts'


class POSClosingCountLine(BaseModel):
    closing = models.ForeignKey(
        POSClosingCount,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    stock_item = models.ForeignKey(
        POSStockItem,
        on_delete=models.PROTECT,
        related_name='closing_lines',
    )
    system_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    counted_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    variance = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('closing', 'stock_item')
        verbose_name = 'POS Closing Count Line'
        verbose_name_plural = 'POS Closing Count Lines'


class POSUnit(BaseModel):
    """Unit of measure master (kg, L, pkt)."""
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='pos_units',
        null=True,
        blank=True,
    )
    property = models.ForeignKey(
        'tenants.Property',
        on_delete=models.CASCADE,
        related_name='pos_units',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=16)
    unit_type = models.CharField(max_length=32, default='Weight')
    base_symbol = models.CharField(max_length=16, blank=True, null=True)
    ratio_to_base = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'POS Unit'
        verbose_name_plural = 'POS Units'

    def __str__(self):
        return f"{self.name} ({self.symbol})"
