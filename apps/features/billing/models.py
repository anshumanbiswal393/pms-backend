from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant
from apps.features.front_office.models import GuestFolio

class TaxRate(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='tax_rates')
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=16)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def clean(self):
        if self.percentage < 0 or self.percentage > 100:
            raise ValidationError("Tax percentage must be between 0 and 100.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"


class Invoice(BaseModel):
    INVOICE_TYPE_CHOICES = (
        ('STANDARD', 'Standard Invoice'),
        ('TAX_INVOICE', 'Tax Invoice'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invoices')
    folio = models.ForeignKey(GuestFolio, on_delete=models.CASCADE, related_name='invoices')
    invoice_number = models.CharField(max_length=64, unique=True)
    invoice_type = models.CharField(max_length=32, choices=INVOICE_TYPE_CHOICES, default='STANDARD')
    issued_at = models.DateTimeField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pdf_file_path = models.CharField(max_length=255, null=True, blank=True)

    def clean(self):
        if self.folio.tenant != self.tenant:
            raise ValidationError("Folio must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.invoice_number} (Folio: {self.folio.folio_number})"


class InvoiceLineItem(BaseModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    description = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} x {self.quantity}"


class CreditNote(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='credit_notes')
    original_invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='credit_notes')
    credit_note_number = models.CharField(max_length=64, unique=True)
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    issued_at = models.DateTimeField(default=timezone.now)

    def clean(self):
        if self.original_invoice.tenant != self.tenant:
            raise ValidationError("Invoice must belong to the resolved tenant context.")
        if self.credit_amount <= 0:
            raise ValidationError("Credit amount must be positive.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"CreditNote {self.credit_note_number} for Invoice {self.original_invoice.invoice_number}"


class BillingAdjustment(BaseModel):
    ADJUSTMENT_TYPE_CHOICES = (
        ('DISCOUNT', 'Discount Adjustment'),
        ('REFUND', 'Refund Posting'),
        ('REVERSAL', 'Charge Reversal'),
        ('TRANSFER', 'Folio Transfer'),
        ('SPLIT', 'Folio Split'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='billing_adjustments')
    folio = models.ForeignKey(GuestFolio, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=32, choices=ADJUSTMENT_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_billing_adjustments'
    )

    def clean(self):
        if self.folio.tenant != self.tenant:
            raise ValidationError("Folio must belong to the resolved tenant context.")
        if self.amount <= 0:
            raise ValidationError("Adjustment amount must be positive.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Adjustment {self.adjustment_type} ({self.amount}) for Folio {self.folio.folio_number}"
