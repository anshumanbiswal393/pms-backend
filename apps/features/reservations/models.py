from django.db import models
from django.core.exceptions import ValidationError
from apps.core.common.models import BaseModel, BaseManager, BaseQuerySet
from apps.core.tenants.models import Tenant, Property
from apps.features.crm.models import GuestProfile
from apps.core.reference.models import Country, ReservationSource
from apps.features.inventory.models import InventoryUnit, InventoryUnitType
from apps.features.rates.models import RatePlan, RatePlanVersion, Service, HospitalityPackage, Coupon
from django.conf import settings

from apps.features.availability.models import (
    GroupBlock, GROUP_BLOCK_TYPE_CHOICES, GROUP_BLOCK_STATUS_CHOICES
)

RESERVATION_STATUS_CHOICES = (
    ('INQUIRY', 'Inquiry'),
    ('PENDING', 'Pending'),
    ('CONFIRMED', 'Confirmed'),
    ('GUARANTEED', 'Guaranteed'),
    ('WAITLISTED', 'Waitlisted'),
    ('CHECKED_IN', 'Checked In'),
    ('CHECKED_OUT', 'Checked Out'),
    ('CANCELLED', 'Cancelled'),
    ('NO_SHOW', 'No Show'),
)

ALLOCATION_STATUS_CHOICES = (
    ('RESERVED', 'Reserved'),
    ('ASSIGNED', 'Assigned'),
    ('CHECKED_IN', 'Checked In'),
    ('CHECKED_OUT', 'Checked Out'),
    ('CANCELLED', 'Cancelled'),
)


class CorporateAccount(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='corporate_accounts')
    company_name = models.CharField(max_length=120)
    negotiated_rate_code = models.CharField(max_length=32)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    open_invoices_count = models.IntegerField(default=0)
    contact_person = models.CharField(max_length=120, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'company_name'], name='unique_tenant_corporate_company'),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.negotiated_rate_code})"


# GroupBlock is defined in and imported from apps.features.availability.models


class Reservation(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservations')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='reservations')
    primary_guest = models.ForeignKey(GuestProfile, on_delete=models.RESTRICT, related_name='primary_reservations')
    reservation_source = models.ForeignKey(ReservationSource, on_delete=models.RESTRICT, related_name='reservations')
    group_block = models.ForeignKey(GroupBlock, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations')
    corporate_account = models.ForeignKey(CorporateAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='reservations')
    
    status = models.CharField(max_length=24, choices=RESERVATION_STATUS_CHOICES, default='PENDING')
    booking_date = models.DateField()
    arrival_date = models.DateField()
    departure_date = models.DateField()
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    booking_reference = models.CharField(max_length=64, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    confirmation_number = models.CharField(max_length=64, unique=True)
    reservation_type = models.CharField(max_length=32)
    market_segment = models.CharField(max_length=32)
    origin_country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='origin_reservations')
    remarks = models.TextField(null=True, blank=True)
    special_requests = models.TextField(null=True, blank=True)

    # Corporate account specific fields
    corporate_po_ref = models.CharField(max_length=64, null=True, blank=True)
    corporate_billing_type = models.CharField(max_length=120, null=True, blank=True)
    corporate_employee_id = models.CharField(max_length=64, null=True, blank=True)
    corporate_cost_center = models.CharField(max_length=64, null=True, blank=True)
    corporate_gst_number = models.CharField(max_length=32, null=True, blank=True)
    corporate_travel_purpose = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'arrival_date', 'departure_date']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['property', 'arrival_date']),
            models.Index(fields=['deleted_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[s[0] for s in RESERVATION_STATUS_CHOICES]),
                name='reservation_status_check'
            ),
            models.CheckConstraint(
                condition=models.Q(departure_date__gte=models.F('arrival_date')),
                name='departure_after_arrival_check'
            ),
            models.UniqueConstraint(
                fields=['property', 'booking_reference'],
                name='unique_property_booking_reference',
                condition=models.Q(booking_reference__isnull=False)
            )
        ]

    def __str__(self):
        return f"{self.confirmation_number} - {self.primary_guest.first_name} {self.primary_guest.last_name}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if not is_new:
            for alloc in self.room_allocations.all():
                if alloc.check_in_date != self.arrival_date or alloc.check_out_date != self.departure_date:
                    alloc.check_in_date = self.arrival_date
                    alloc.check_out_date = self.departure_date
                    alloc.save(update_fields=['check_in_date', 'check_out_date'])


class ReservationInventory(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_allocations')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='room_allocations')
    inventory_unit = models.ForeignKey(InventoryUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.RESTRICT, related_name='allocations')
    
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    adult_count = models.IntegerField(default=2)
    child_count = models.IntegerField(default=0)
    infant_count = models.IntegerField(default=0)
    status = models.CharField(max_length=24, choices=ALLOCATION_STATUS_CHOICES, default='RESERVED')
    inventory_snapshot = models.JSONField(null=True, blank=True)

    assigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_rooms'
    )
    upgrade_from_inventory_type = models.ForeignKey(
        InventoryUnitType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upgraded_allocations'
    )
    upgrade_reason = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_out_date__gt=models.F('check_in_date')),
                name='checkout_after_checkin_check'
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[s[0] for s in ALLOCATION_STATUS_CHOICES]),
                name='allocation_status_check'
            )
        ]
        indexes = [
            models.Index(fields=['tenant', 'inventory_unit']),
            models.Index(fields=['tenant', 'inventory_unit_type']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['check_in_date', 'check_out_date']),
        ]

    def __str__(self):
        unit_name = self.inventory_unit.name if self.inventory_unit else "Unassigned"
        return f"{self.reservation.confirmation_number} -> {unit_name} ({self.inventory_unit_type.code})"


class ReservationRateSnapshot(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_rate_snapshots')
    reservation_inventory = models.ForeignKey(ReservationInventory, on_delete=models.CASCADE, related_name='rate_snapshots')
    date = models.DateField()
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.RESTRICT, related_name='snapshots')
    rate_plan_version = models.ForeignKey(RatePlanVersion, on_delete=models.RESTRICT, related_name='snapshots')
    amount_charged = models.DecimalField(max_digits=12, decimal_places=2)
    rate_snapshot = models.JSONField()
    policy_snapshot = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['reservation_inventory', 'date'], name='unique_inventory_date_rate_snapshot'),
        ]

    def __str__(self):
        return f"{self.date}: {self.amount_charged} ({self.rate_plan.code})"


class ReservationGuest(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_guests')
    reservation_inventory = models.ForeignKey(ReservationInventory, on_delete=models.CASCADE, related_name='guests')
    guest = models.ForeignKey(GuestProfile, on_delete=models.RESTRICT, related_name='reservations')
    is_primary = models.BooleanField(default=False)
    guest_snapshot = models.JSONField()
    
    is_checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['reservation_inventory', 'guest'], name='unique_inventory_guest_pairing'),
        ]

    def __str__(self):
        return f"{self.guest.first_name} {self.guest.last_name} ({'Primary' if self.is_primary else 'Additional'})"


class ReservationEventQuerySet(BaseQuerySet):
    def update(self, *args, **kwargs):
        raise ValidationError("Updates are blocked for reservation timeline events.")
    def delete(self, *args, **kwargs):
        raise ValidationError("Deletes are blocked for reservation timeline events.")

class ReservationEventManager(BaseManager):
    def get_queryset(self):
        return ReservationEventQuerySet(self.model, using=self._db).active()

class ReservationEvent(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_timeline_events')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='timeline_events')
    timestamp = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=64)
    description = models.TextField()
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    payload_diff = models.JSONField(null=True, blank=True)

    objects = ReservationEventManager()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Reservation timeline events are append-only. Updates are not allowed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Reservation timeline events are append-only. Deletes are not allowed.")

    def __str__(self):
        return f"{self.event_type} on {self.reservation.confirmation_number} at {self.timestamp}"


class ReservationServiceAddon(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_services')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='services')
    service = models.ForeignKey(Service, on_delete=models.RESTRICT, related_name='reservations')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.reservation.confirmation_number} -> {self.service.name}"


class ReservationPackage(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_packages')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='packages')
    package = models.ForeignKey(HospitalityPackage, on_delete=models.RESTRICT, related_name='reservations')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.reservation.confirmation_number} -> {self.package.name}"


class ReservationCoupon(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='reservation_coupons')
    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name='coupons')
    coupon = models.ForeignKey(Coupon, on_delete=models.RESTRICT, related_name='reservations')

    def __str__(self):
        return f"{self.reservation.confirmation_number} -> Coupon {self.coupon.code}"
