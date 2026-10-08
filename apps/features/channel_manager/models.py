import uuid
from django.db import models
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property

class StaahConfig(BaseModel):
    """
    Configuration and API credentials for STAAH Su API per Property / Tenant.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='staah_configs')
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name='staah_config')
    
    # STAAH Su API Credentials
    domain = models.CharField(max_length=255, default='https://connect.su-api.com', help_text='STAAH Su API base URL')
    app_id = models.CharField(max_length=255, help_text='Base64 partner app-id or domain identifier')
    auth_token = models.CharField(max_length=255, help_text='Basic Auth token (e.g. Basic bkdBOGpRdEM6YkkyeVFKMno)')
    hotel_id = models.CharField(max_length=64, help_text='STAAH property code / hotelid (e.g. VR-TEST)')
    
    is_active = models.BooleanField(default=True, help_text='Channel Manager connection enabled')
    is_live = models.BooleanField(default=False, help_text='True for production, False for sandbox simulator')
    auto_sync_inventory = models.BooleanField(default=True, help_text='Automatically push ARI changes on reservation updates')
    auto_fetch_reservations = models.BooleanField(default=True, help_text='Automatically poll for incoming bookings')
    
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'staah_config'
        verbose_name = 'STAAH Configuration'
        verbose_name_plural = 'STAAH Configurations'

    def __str__(self):
        return f"STAAH Config: {self.property.name} ({self.hotel_id})"


class StaahRoomMapping(BaseModel):
    """
    Mapping between internal PMS Room Types and STAAH Room IDs.
    """
    STATUS_CHOICES = (
        ('Mapped', 'Mapped'),
        ('Mismatch', 'Mismatch'),
        ('Unmapped', 'Unmapped'),
        ('Pending', 'Pending'),
    )

    config = models.ForeignKey(StaahConfig, on_delete=models.CASCADE, related_name='room_mappings')
    pms_room_code = models.CharField(max_length=64, db_index=True, help_text='Internal PMS room type code')
    pms_room_name = models.CharField(max_length=128, help_text='Internal PMS room type display name')
    
    staah_room_id = models.CharField(max_length=64, db_index=True, help_text='STAAH roomid')
    staah_room_name = models.CharField(max_length=128, blank=True, default='')
    
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='Mapped')
    ota_mappings = models.JSONField(default=dict, blank=True, help_text='Channel-specific room IDs (Booking.com, Agoda, etc.)')
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'staah_room_mapping'
        unique_together = ('config', 'pms_room_code')
        verbose_name = 'STAAH Room Mapping'
        verbose_name_plural = 'STAAH Room Mappings'

    def __str__(self):
        return f"{self.pms_room_code} -> {self.staah_room_id} ({self.status})"


class StaahRateMapping(BaseModel):
    """
    Mapping between internal PMS Rate Plans and STAAH Rate IDs.
    """
    STATUS_CHOICES = (
        ('Mapped', 'Mapped'),
        ('Mismatch', 'Mismatch'),
        ('Unmapped', 'Unmapped'),
        ('Pending', 'Pending'),
    )

    config = models.ForeignKey(StaahConfig, on_delete=models.CASCADE, related_name='rate_mappings')
    pms_rate_code = models.CharField(max_length=64, db_index=True, help_text='Internal PMS rate plan code')
    pms_rate_name = models.CharField(max_length=128, help_text='Internal PMS rate plan name')
    meal_plan_code = models.CharField(max_length=32, blank=True, default='EP', help_text='EP, CP, MAP, AP, etc.')
    
    staah_rate_id = models.CharField(max_length=64, db_index=True, help_text='STAAH rateplanid')
    staah_rate_name = models.CharField(max_length=128, blank=True, default='')
    
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='Mapped')
    ota_mappings = models.JSONField(default=dict, blank=True, help_text='Channel-specific rate IDs')
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'staah_rate_mapping'
        unique_together = ('config', 'pms_rate_code')
        verbose_name = 'STAAH Rate Mapping'
        verbose_name_plural = 'STAAH Rate Mappings'

    def __str__(self):
        return f"{self.pms_rate_code} -> {self.staah_rate_id} ({self.status})"


class StaahSyncLog(BaseModel):
    """
    Audit log of all two-way transactions between PMS and STAAH Su API.
    """
    SYNC_TYPE_CHOICES = (
        ('Inventory', 'Inventory / Availability'),
        ('Rates', 'Rates & Pricing'),
        ('Restrictions', 'Restrictions (Stop-Sell / MinLOS)'),
        ('Reservations', 'Reservations Ingestion'),
        ('Content', 'Property Content'),
        ('Images', 'Images'),
        ('Mapping', 'Room & Rate Mapping'),
        ('Incident', 'Incident / Reporting'),
    )

    DIRECTION_CHOICES = (
        ('OUTBOUND', 'PMS to STAAH'),
        ('INBOUND', 'STAAH to PMS'),
    )

    STATUS_CHOICES = (
        ('Success', 'Success'),
        ('Warning', 'Warning'),
        ('Error', 'Error'),
        ('In Progress', 'In Progress'),
    )

    config = models.ForeignKey(StaahConfig, on_delete=models.CASCADE, related_name='sync_logs')
    sync_type = models.CharField(max_length=32, choices=SYNC_TYPE_CHOICES)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES, default='OUTBOUND')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='Success')
    endpoint = models.CharField(max_length=255)
    
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    records_count = models.IntegerField(default=0)
    duration_ms = models.IntegerField(default=0)

    class Meta:
        db_table = 'staah_sync_log'
        ordering = ['-created_at']
        verbose_name = 'STAAH Sync Log'
        verbose_name_plural = 'STAAH Sync Logs'

    def __str__(self):
        return f"[{self.status}] {self.sync_type} ({self.direction}) - {self.created_at}"


class StaahChannelConnection(BaseModel):
    """
    Cached connection status and revenue metrics for each connected OTA channel.
    """
    config = models.ForeignKey(StaahConfig, on_delete=models.CASCADE, related_name='channel_connections')
    channel_name = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=24, default='Connected')
    property_id = models.CharField(max_length=64, blank=True, default='')
    last_sync = models.CharField(max_length=64, blank=True, default='Just now')
    commission = models.CharField(max_length=16, blank=True, default='15%')
    bookings_mtd = models.IntegerField(default=0)
    revenue_mtd = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    parity = models.CharField(max_length=24, default='Aligned')
    parity_delta = models.CharField(max_length=32, blank=True, default='0%')

    class Meta:
        db_table = 'staah_channel_connection'
        unique_together = ('config', 'channel_name')
        verbose_name = 'STAAH Channel Connection'
        verbose_name_plural = 'STAAH Channel Connections'

    def __str__(self):
        return f"{self.channel_name} - {self.status} ({self.config.hotel_id})"


class StaahReservationIngest(BaseModel):
    """
    Audit record for every ingested STAAH OTA reservation.
    Links the STAAH channel_bookingid to the internal PMS Booking.
    """
    STATUS_CHOICES = (
        ('Synced', 'Synced'),
        ('Pending', 'Pending'),
        ('Conflict', 'Conflict'),
        ('Failed', 'Failed'),
        ('Cancelled', 'Cancelled'),
    )

    config = models.ForeignKey(StaahConfig, on_delete=models.CASCADE, related_name='ingested_reservations')
    channel_booking_id = models.CharField(max_length=128, unique=True, db_index=True)
    channel_name = models.CharField(max_length=64, default='Booking.com', db_index=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Synced')
    
    # Linked internal models
    pms_booking_reference = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    guest_name = models.CharField(max_length=128)
    guest_email = models.CharField(max_length=128, blank=True, default='')
    guest_phone = models.CharField(max_length=64, blank=True, default='')
    
    room_type_name = models.CharField(max_length=128)
    check_in = models.DateField()
    check_out = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)
    currency = models.CharField(max_length=8, default='INR')
    
    raw_payload = models.JSONField(default=dict, blank=True)
    is_confirmed_to_staah = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'staah_reservation_ingest'
        ordering = ['-created_at']
        verbose_name = 'STAAH Ingested Reservation'
        verbose_name_plural = 'STAAH Ingested Reservations'

    def __str__(self):
        return f"{self.channel_name} #{self.channel_booking_id} -> {self.pms_booking_reference} ({self.status})"

