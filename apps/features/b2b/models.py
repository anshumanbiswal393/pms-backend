import random
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant

class B2BPartner(BaseModel):
    STATUS_CHOICES = (
        ('Pending KYC', 'Pending KYC'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='b2b_partners')
    agent_id = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    location = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Pending KYC')
    commission_rate = models.IntegerField(default=0)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    incorporation_document = models.FileField(upload_to='b2b_documents/', null=True, blank=True)
    owner_id_document = models.FileField(upload_to='b2b_documents/', null=True, blank=True)
    cheque_document = models.FileField(upload_to='b2b_documents/', null=True, blank=True)

    class Meta:
        db_table = 'b2b_partners'
        verbose_name = 'B2B Partner'
        verbose_name_plural = 'B2B Partners'
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'agent_id'], name='unique_tenant_b2b_agent_id'),
        ]

    def save(self, *args, **kwargs):
        if not self.agent_id:
            # Generate a unique agent_id
            while True:
                agent_id = f"AGT-{random.randint(10000, 99999)}"
                # Use all_with_deleted to make sure it is completely unique
                if not B2BPartner.objects.all_with_deleted().filter(agent_id=agent_id).exists():
                    self.agent_id = agent_id
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.agent_id})"
