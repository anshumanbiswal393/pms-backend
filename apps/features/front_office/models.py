import uuid
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property
from apps.features.reservations.models import Reservation, ReservationInventory
from apps.features.crm.models import GuestProfile

class GuestRegistrationCard(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='guest_registration_cards')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='registration_cards')
    guest = models.ForeignKey(GuestProfile, on_delete=models.CASCADE, related_name='registration_cards')
    
    registration_number = models.CharField(max_length=64, unique=True)
    signature_data = models.TextField(null=True, blank=True)
    id_document_type = models.CharField(max_length=32)
    id_document_number = models.CharField(max_length=64)
    is_verified = models.BooleanField(default=False)
    metadata = models.JSONField(null=True, blank=True)

    def clean(self):
        if self.reservation.tenant != self.tenant or self.guest.tenant != self.tenant:
            raise ValidationError("Reservation and guest must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"RegCard {self.registration_number} for {self.guest}"


class RoomKeyCard(BaseModel):
    KEY_TYPE_CHOICES = (
        ('PHYSICAL', 'Physical Key Card'),
        ('MOBILE_NFC', 'Mobile NFC Key'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('DEACTIVATED', 'Deactivated'),
        ('LOST', 'Lost'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='room_key_cards')
    reservation_inventory = models.ForeignKey(ReservationInventory, on_delete=models.CASCADE, related_name='key_cards')
    
    card_number = models.CharField(max_length=128)
    key_type = models.CharField(max_length=32, choices=KEY_TYPE_CHOICES, default='PHYSICAL')
    issued_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='ACTIVE')

    def clean(self):
        if self.reservation_inventory.tenant != self.tenant:
            raise ValidationError("Reservation allocation must belong to the resolved tenant context.")
        if self.expires_at <= self.issued_at:
            raise ValidationError("Expires time must be after issued time.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"KeyCard {self.card_number} ({self.status})"


class GuestFolio(BaseModel):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('SETTLED', 'Settled'),
        ('SUSPENDED', 'Suspended'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='guest_folios')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, null=True, blank=True, related_name='folios')
    
    folio_number = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='OPEN')
    total_charges = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_payments = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def clean(self):
        if self.reservation and self.reservation.tenant != self.tenant:
            raise ValidationError("Reservation must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        from decimal import Decimal
        self.total_charges = Decimal(str(self.total_charges or 0.00))
        self.total_payments = Decimal(str(self.total_payments or 0.00))
        self.balance = self.total_charges - self.total_payments
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['deleted_at']),
        ]

    def __str__(self):
        return f"Folio {self.folio_number} (Bal: {self.balance})"


class FolioTransaction(BaseModel):
    TRANSACTION_TYPE_CHOICES = (
        ('CHARGE', 'Charge Posting'),
        ('PAYMENT', 'Payment Posting'),
        ('REVERSAL', 'Charge Reversal'),
        ('REFUND', 'Refund Processing'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='folio_transactions')
    folio = models.ForeignKey(GuestFolio, on_delete=models.CASCADE, related_name='transactions')
    
    transaction_type = models.CharField(max_length=32, choices=TRANSACTION_TYPE_CHOICES)
    charge_code = models.CharField(max_length=32)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    posted_at = models.DateTimeField(default=timezone.now)
    is_reversed = models.BooleanField(default=False)

    def clean(self):
        if self.folio.tenant != self.tenant:
            raise ValidationError("Folio must belong to the resolved tenant context.")
        if self.amount <= 0:
            raise ValidationError("Amount must be positive.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'folio']),
            models.Index(fields=['deleted_at']),
        ]

    def __str__(self):
        return f"{self.transaction_type}: {self.amount} on {self.folio.folio_number}"


class CashierShift(BaseModel):
    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('CLOSED', 'Closed'),
        ('RECONCILED', 'Reconciled'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='cashier_shifts')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='cashier_shifts')
    
    shift_code = models.CharField(max_length=32)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='OPEN')

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Shift {self.shift_code} @ {self.property.name} ({self.status})"


class GuestDeposit(BaseModel):
    DEPOSIT_TYPE_CHOICES = (
        ('ROOM_DEPOSIT', 'Room Deposit'),
        ('SECURITY_COLLATERAL', 'Security Collateral'),
    )
    STATUS_CHOICES = (
        ('HELD', 'Held'),
        ('RELEASED', 'Released'),
        ('FORFEITED', 'Forfeited'),
        ('REFUNDED', 'Refunded'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='guest_deposits')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='deposits')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_type = models.CharField(max_length=32, choices=DEPOSIT_TYPE_CHOICES, default='ROOM_DEPOSIT')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='HELD')

    def clean(self):
        if self.reservation.tenant != self.tenant:
            raise ValidationError("Reservation must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Deposit {self.amount} for {self.reservation.confirmation_number}"


class HouseAccount(BaseModel):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('SETTLED', 'Settled'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='house_accounts')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='house_accounts')
    
    account_name = models.CharField(max_length=120)
    account_code = models.CharField(max_length=32, unique=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='ACTIVE')

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"HouseAccount {self.account_name} ({self.account_code})"


class NightAuditSession(BaseModel):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('ROLLED_BACK', 'Rolled Back'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='night_audits')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='night_audits')
    
    audit_date = models.DateField()
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    performed_by = models.ForeignKey('accounts.AppUser', on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_night_audits')

    # Operational metrics
    rooms_occupied = models.IntegerField(default=0)
    rooms_total = models.IntegerField(default=0)
    occupancy_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    # Postings & Revenue
    total_room_charges_posted = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_packages_posted = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_tax_posted = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_charges_posted = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_payments_received = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # No-Shows
    no_shows_processed = models.IntegerField(default=0)
    no_show_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Cashier balances
    cashier_opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cashier_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cashier_variance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Ledgers
    guest_ledger_closing = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    city_ledger_closing = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    deposit_ledger_closing = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Logs & details
    pre_audit_checklist_results = models.JSONField(null=True, blank=True, default=dict)
    post_audit_summary = models.JSONField(null=True, blank=True, default=dict)
    exception_logs = models.JSONField(null=True, blank=True, default=list)

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"NightAudit {self.audit_date} @ {self.property.name} ({self.status})"


class ShiftHandover(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='shift_handovers')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='shift_handovers')
    
    handover_notes = models.TextField()
    cash_balance_passed = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    pending_tasks = models.JSONField(null=True, blank=True)

    def clean(self):
        if self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Handover at {self.created_at} @ {self.property.name}"
