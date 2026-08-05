import uuid
import random
from django.db import models
from apps.core.common.models import BaseModel

def generate_hotel_id():
    """Generates a random, non-sequential 5-digit hotel ID string."""
    return str(random.randint(10000, 99999))

class Tenant(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    subdomain = models.CharField(max_length=64, unique=True, db_index=True)
    custom_domain = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='active')
    
    country = models.CharField(max_length=100)
    currency = models.CharField(max_length=3)
    timezone = models.CharField(max_length=50)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('accounts.AppUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_tenants')

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

class Property(BaseModel):
    PROPERTY_TYPE_CHOICES = (
        ('HOTEL', 'Hotel'),
        ('VILLA', 'Villa'),
        ('VACATION_RENTAL', 'Vacation Rental'),
        ('HOSTEL', 'Hostel'),
        ('APARTMENT', 'Apartment'),
        ('OTHER', 'Other'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='properties')
    hotel_id = models.CharField(max_length=5, unique=True, null=True, blank=True, db_index=True)
    name = models.CharField(max_length=120)
    property_type = models.CharField(max_length=32, choices=PROPERTY_TYPE_CHOICES, default='HOTEL')
    
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=16)
    
    contact_email = models.EmailField(max_length=255)
    contact_phone = models.CharField(max_length=32)
    
    currency = models.CharField(max_length=3)
    timezone = models.CharField(max_length=50)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    # Detailed setup fields
    description = models.TextField(null=True, blank=True)
    star_rating = models.CharField(max_length=10, default="4")
    website = models.URLField(max_length=255, null=True, blank=True)
    check_in_time = models.CharField(max_length=10, default="14:00")
    check_out_time = models.CharField(max_length=10, default="11:00")
    min_age = models.IntegerField(default=18)
    pets_allowed = models.CharField(max_length=10, default="No")
    tax_id = models.CharField(max_length=50, null=True, blank=True)
    google_map_url = models.TextField(null=True, blank=True)  # Accepts URL or full iframe embed code
    cancellation_policy = models.TextField(null=True, blank=True)
    refund_policy = models.TextField(null=True, blank=True)
    house_rules = models.TextField(null=True, blank=True)
    website_logo = models.TextField(null=True, blank=True)
    kot_logo = models.TextField(null=True, blank=True)
    photos = models.JSONField(default=list, blank=True)
    
    cgst = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    vat = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    city_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    service_charge = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    luxury_tax = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    amenities = models.JSONField(default=list, blank=True)

    def save(self, *args, **kwargs):
        if not self.hotel_id:
            while True:
                candidate = generate_hotel_id()
                if not Property.objects.filter(hotel_id=candidate).exists():
                    self.hotel_id = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.hotel_id}) - {self.tenant.name}"


class TenantBranding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='branding')
    company_name = models.CharField(max_length=120)
    logo_url = models.URLField(null=True, blank=True)
    favicon_url = models.URLField(null=True, blank=True)
    logo_file_id = models.UUIDField(null=True, blank=True)
    favicon_file_id = models.UUIDField(null=True, blank=True)
    primary_color = models.CharField(max_length=16, default='#000000')
    secondary_color = models.CharField(max_length=16, default='#ffffff')
    support_email = models.EmailField(max_length=255)
    support_phone = models.CharField(max_length=32)

    class Meta:
        db_table = 'tenant_branding'

    def __str__(self):
        return f"Branding - {self.tenant.name}"


class TenantDomain(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='domains')
    domain = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    subdomain = models.CharField(max_length=64, unique=True, db_index=True)
    ssl_enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=32, default='ACTIVE') # ACTIVE, INACTIVE, PENDING

    class Meta:
        db_table = 'tenant_domain'

    def __str__(self):
        return f"{self.subdomain}.domain ({self.status})"


class TenantConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='configuration')
    timezone = models.CharField(max_length=50, default='UTC')
    currency = models.CharField(max_length=3, default='USD')
    language = models.CharField(max_length=10, default='en')
    date_format = models.CharField(max_length=32, default='YYYY-MM-DD')
    time_format = models.CharField(max_length=16, default='24H')
    enforce_ip_whitelist = models.BooleanField(default=False)
    mfa_double_confirmation = models.BooleanField(default=True)
    configuration_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'tenant_configuration'

    def __str__(self):
        return f"Config - {self.tenant.name}"


class TenantIsolationConfig(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='isolation_config')
    isolation_mode = models.CharField(max_length=32, default='SHARED') # SHARED, SCHEMA, DATABASE
    database_name = models.CharField(max_length=120, null=True, blank=True)
    schema_name = models.CharField(max_length=120, null=True, blank=True)
    status = models.CharField(max_length=32, default='PROVISIONED')

    class Meta:
        db_table = 'tenant_isolation_config'

    def __str__(self):
        return f"Isolation - {self.tenant.name} ({self.isolation_mode})"
