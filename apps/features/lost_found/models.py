from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property

class LostFoundItem(BaseModel):
    ITEM_TYPE_CHOICES = (
        ('LOST', 'Lost'),
        ('FOUND', 'Found'),
    )
    STATUS_CHOICES = (
        ('REPORTED', 'Reported'),          # Open / Reported
        ('MATCHED', 'Matched'),
        ('AWAITING_CLAIM', 'Awaiting Claim'),
        ('CLAIMED', 'Claimed'),            # Released / Claimed
        ('DISPOSED', 'Disposed'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lost_found_items')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='lost_found_items')
    reference_number = models.CharField(max_length=32, unique=True, null=True, blank=True)
    item_type = models.CharField(max_length=16, choices=ITEM_TYPE_CHOICES, default='FOUND')
    item_name = models.CharField(max_length=120)
    description = models.TextField()
    location_found = models.CharField(max_length=255, null=True, blank=True)
    finder_name = models.CharField(max_length=120, null=True, blank=True)
    image = models.FileField(upload_to='lost_found/', null=True, blank=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_lost_found_items'
    )
    guest_name = models.CharField(max_length=120, null=True, blank=True)
    guest_contact = models.CharField(max_length=120, null=True, blank=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='REPORTED')
    
    # Claim info
    claimed_by = models.CharField(max_length=120, null=True, blank=True)
    claimed_date = models.DateTimeField(null=True, blank=True)
    disposed_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'lost_found_item'

    def clean(self):
        if self.status == 'CLAIMED' and not self.claimed_by:
            raise ValidationError("Claimed items must specify the claimant in 'claimed_by'.")
        if self.status == 'DISPOSED' and not self.disposed_reason:
            raise ValidationError("Disposed items must specify a reason in 'disposed_reason'.")

    def save(self, *args, **kwargs):
        if not self.reference_number:
            count = LostFoundItem.objects.all_with_deleted().filter(tenant=self.tenant).count()
            self.reference_number = f"LF-{301 + count}"
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_type}: {self.item_name} ({self.status})"
