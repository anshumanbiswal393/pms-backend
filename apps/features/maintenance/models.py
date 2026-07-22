import uuid
from django.db import models
from apps.core.tenants.models import Tenant, Property
from apps.features.inventory.models import InventoryUnit
from apps.features.assets.models import Asset
from django.conf import settings

class MaintenanceTicket(models.Model):
    PRIORITY_CHOICES = (
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    )
    STATUS_CHOICES = (
        ('REPORTED', 'Reported'),
        ('IN_PROGRESS', 'In Progress'),
        ('WAITING_PARTS', 'Waiting Parts'),
        ('RESOLVED', 'Resolved'),
    )
    CATEGORY_CHOICES = (
        ('HVAC', 'HVAC'),
        ('PLUMBING', 'Plumbing'),
        ('ELECTRICAL', 'Electrical'),
        ('FURNITURE', 'Furniture'),
        ('GENERAL', 'General'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='maintenance_tickets')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='maintenance_tickets')
    reference_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    inventory_unit = models.ForeignKey(
        InventoryUnit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_tickets'
    )
    location = models.CharField(max_length=120, null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name='maintenance_tickets')
    title = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='GENERAL')
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default='NORMAL')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='REPORTED')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='maintenance_tickets'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'maintenance_ticket'

    def save(self, *args, **kwargs):
        if not self.reference_number:
            count = MaintenanceTicket.objects.filter(tenant=self.tenant).count()
            self.reference_number = f"WO-{441 + count}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket #{self.reference_number or self.title} ({self.status})"


class MaintenanceSchedule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='schedules')
    schedule_type = models.CharField(max_length=64) # e.g. PREVENTATIVE, INSPECTION
    next_due_date = models.DateField()

    class Meta:
        db_table = 'maintenance_schedule'

    def __str__(self):
        return f"{self.asset.asset_name} - {self.schedule_type} due on {self.next_due_date}"
