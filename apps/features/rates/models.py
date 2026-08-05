import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.core.common.models import BaseModel
from apps.core.tenants.models import Tenant, Property
from apps.features.inventory.models import InventoryUnitType

class MealPlan(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='meal_plans')
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    price_adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_mealplan_code'),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class CancellationPolicy(BaseModel):
    PENALTY_TYPE_CHOICES = (
        ('PERCENTAGE', 'Percentage of Total Stay'),
        ('NIGHTS', 'Number of Nights Charge'),
        ('FLAT_AMOUNT', 'Flat Amount Fee'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='cancellation_policies')
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)
    free_cancellation_hours = models.IntegerField(default=0)
    penalty_type = models.CharField(max_length=24, choices=PENALTY_TYPE_CHOICES, default='PERCENTAGE')
    penalty_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_cancel_code'),
            models.CheckConstraint(
                condition=models.Q(penalty_type__in=['PERCENTAGE', 'NIGHTS', 'FLAT_AMOUNT']),
                name='cancellation_penalty_type_check'
            )
        ]

    def clean(self):
        if self.free_cancellation_hours < 0:
            raise ValidationError("Free cancellation hours cannot be negative.")
        if self.penalty_value < 0:
            raise ValidationError("Penalty value cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class ChildPolicy(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='child_policies')
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    max_free_age = models.IntegerField(default=5)
    charge_age_from = models.IntegerField(default=6)
    charge_age_to = models.IntegerField(default=12)
    child_flat_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_child_code'),
        ]

    def clean(self):
        if self.max_free_age < 0:
            raise ValidationError("Max free age cannot be negative.")
        if self.charge_age_from < 0 or self.charge_age_to < 0:
            raise ValidationError("Charge ages cannot be negative.")
        if self.charge_age_from > self.charge_age_to:
            raise ValidationError("Charge age from cannot exceed charge age to.")
        if self.child_flat_charge < 0:
            raise ValidationError("Child flat charge cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class RatePlan(BaseModel):
    CATEGORY_CHOICES = (
        ('bar', 'Best Available Rate'),
        ('corporate', 'Corporate Rate'),
        ('package', 'Package Rate'),
        ('seasonal', 'Seasonal Rate'),
        ('promotional', 'Promotional Rate'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='rate_plans')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='rate_plans')
    cancellation_policy = models.ForeignKey(CancellationPolicy, on_delete=models.PROTECT, null=True, blank=True, related_name='rate_plans')
    child_policy = models.ForeignKey(ChildPolicy, on_delete=models.PROTECT, null=True, blank=True, related_name='rate_plans')
    default_meal_plan = models.ForeignKey(MealPlan, on_delete=models.PROTECT, null=True, blank=True, related_name='rate_plans')
    
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES, default='bar')
    is_derived = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['property', 'code'], name='unique_property_rateplan_code'),
        ]

    def clean(self):
        if self.property and self.property.tenant != self.tenant:
            raise ValidationError("Property must belong to the resolved tenant context.")
        if self.cancellation_policy and self.cancellation_policy.tenant != self.tenant:
            raise ValidationError("Cancellation policy must belong to the resolved tenant context.")
        if self.child_policy and self.child_policy.tenant != self.tenant:
            raise ValidationError("Child policy must belong to the resolved tenant context.")
        if self.default_meal_plan and self.default_meal_plan.tenant and self.default_meal_plan.tenant != self.tenant:
            raise ValidationError("Meal plan must belong to the resolved tenant context or be a system default.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code}) @ {self.property.name}"


class RatePlanInventoryType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='rate_plan_inventory_types')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='inventory_types')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='rate_plans')
    base_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['rate_plan', 'inventory_unit_type'], name='unique_rateplan_inventorytype'),
        ]

    def clean(self):
        if self.rate_plan.tenant != self.tenant:
            raise ValidationError("Rate plan must belong to the resolved tenant context.")
        if self.inventory_unit_type.tenant != self.tenant:
            raise ValidationError("Inventory unit type must belong to the resolved tenant context.")
        if self.base_rate < 0:
            raise ValidationError("Base rate cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rate_plan.code} - {self.inventory_unit_type.code}: {self.base_rate}"


class RatePlanVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='versions')
    version_number = models.IntegerField(default=1)
    snapshot = models.JSONField()
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['rate_plan', 'version_number'], name='unique_rateplan_version'),
        ]

    def __str__(self):
        return f"{self.rate_plan.code} v{self.version_number}"


class DerivedRateConfig(models.Model):
    MODIFIER_TYPE_CHOICES = (
        ('PERCENT', 'Percentage Adjustment'),
        ('FLAT_AMOUNT', 'Flat Amount Adjustment'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='derived_rate_configs')
    child_rate_plan = models.OneToOneField(RatePlan, on_delete=models.CASCADE, related_name='derived_config')
    anchor_rate_plan = models.ForeignKey(RatePlan, on_delete=models.RESTRICT, related_name='anchored_configs')
    modifier_type = models.CharField(max_length=16, choices=MODIFIER_TYPE_CHOICES, default='PERCENT')
    modifier_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def clean(self):
        if self.child_rate_plan == self.anchor_rate_plan:
            raise ValidationError("Child rate plan cannot be anchored to itself.")
        if self.child_rate_plan.tenant != self.tenant or self.anchor_rate_plan.tenant != self.tenant:
            raise ValidationError("Both child and anchor rate plans must belong to the resolved tenant context.")
        if not self.child_rate_plan.is_derived:
            raise ValidationError("Child rate plan must have is_derived set to True.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Derived: {self.child_rate_plan.code} from {self.anchor_rate_plan.code}"


class RateRuleOccupancy(models.Model):
    MODIFIER_TYPE_CHOICES = (
        ('FLAT_CHARGE', 'Flat Charge'),
        ('PERCENTAGE_ADJUST', 'Percentage Adjustment'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='occupancy_rules')
    rate_plan_inventory_type = models.ForeignKey(RatePlanInventoryType, on_delete=models.CASCADE, related_name='occupancy_rules')
    occupancy_from = models.IntegerField(default=1)
    occupancy_to = models.IntegerField(default=1)
    modifier_type = models.CharField(max_length=32, choices=MODIFIER_TYPE_CHOICES, default='FLAT_CHARGE')
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def clean(self):
        if self.occupancy_from < 1 or self.occupancy_to < 1:
            raise ValidationError("Occupancy ranges must be greater than or equal to 1.")
        if self.occupancy_from > self.occupancy_to:
            raise ValidationError("Occupancy from cannot be greater than occupancy to.")
        if self.rate_plan_inventory_type.tenant != self.tenant:
            raise ValidationError("Rate plan inventory type must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Occupancy {self.occupancy_from}-{self.occupancy_to}: {self.modifier_type} ({self.value})"


class RateRuleDayOfWeek(models.Model):
    MODIFIER_TYPE_CHOICES = (
        ('FLAT_ADJUST', 'Flat Charge/Discount'),
        ('PERCENTAGE_ADJUST', 'Percentage Adjustment'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='day_of_week_rules')
    rate_plan_inventory_type = models.ForeignKey(RatePlanInventoryType, on_delete=models.CASCADE, related_name='day_of_week_rules')
    day_of_week = models.IntegerField()  # 1 = Sunday, 7 = Saturday
    modifier_type = models.CharField(max_length=32, choices=MODIFIER_TYPE_CHOICES, default='FLAT_ADJUST')
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(day_of_week__range=(1, 7)), name='day_of_week_between_1_7'),
        ]

    def clean(self):
        if not (1 <= self.day_of_week <= 7):
            raise ValidationError("Day of week must be between 1 (Sunday) and 7 (Saturday).")
        if self.rate_plan_inventory_type.tenant != self.tenant:
            raise ValidationError("Rate plan inventory type must belong to the resolved tenant context.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        days = {1: 'Sunday', 2: 'Monday', 3: 'Tuesday', 4: 'Wednesday', 5: 'Thursday', 6: 'Friday', 7: 'Saturday'}
        return f"{days.get(self.day_of_week)}: {self.modifier_type} ({self.value})"


class RateCalendar(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='rate_calendars')
    date = models.DateField()
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='rate_calendars')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='rate_calendars')
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_available = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['rate_plan', 'inventory_unit_type', 'date'], name='unique_rateplan_unit_date'),
        ]
        indexes = [
            models.Index(fields=['property', 'inventory_unit_type', 'date'], name='idx_ratecal_prop_unit_date'),
        ]

    def clean(self):
        if self.rate_plan.property != self.property:
            raise ValidationError("Rate plan must belong to the target property.")
        if self.inventory_unit_type.property != self.property:
            raise ValidationError("Inventory unit type must belong to the target property.")
        if self.amount < 0:
            raise ValidationError("Amount cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rate_plan.code} - {self.inventory_unit_type.code} @ {self.date}: {self.amount}"


class HospitalityPackage(BaseModel):
    STATUS_CHOICES = (
        ('Active', 'Active'),
        ('Draft', 'Draft'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='hospitality_packages')
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    inclusions = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='unique_tenant_package_name'),
        ]

    def clean(self):
        if self.price < 0:
            raise ValidationError("Price cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.price} ({self.status})"


class TenantMealPlanPrice(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='tenant_meal_plan_prices')
    meal_plan = models.ForeignKey(MealPlan, on_delete=models.CASCADE, related_name='tenant_prices')
    inventory_unit_type = models.ForeignKey(InventoryUnitType, on_delete=models.CASCADE, related_name='meal_plan_prices')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'meal_plan', 'inventory_unit_type'], name='unique_tenant_mealplan_roomtype'),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.meal_plan.name} - {self.inventory_unit_type.name}: {self.price}"


class ServiceCategory(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='service_categories')
    name = models.CharField(max_length=64)
    description = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='unique_tenant_service_category_name'),
        ]

    def __str__(self):
        return self.name


class Service(BaseModel):
    STATUS_CHOICES = (
        ('Active', 'Active'),
        ('Seasonal', 'Seasonal'),
        ('Draft', 'Draft'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='services')
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='services')
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Active')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'name'], name='unique_tenant_service_name'),
        ]

    def clean(self):
        if self.price < 0:
            raise ValidationError("Price cannot be negative.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.price} ({self.status})"


class Coupon(BaseModel):
    DISCOUNT_TYPE_CHOICES = (
        ('FLAT', 'Flat Amount'),
        ('PERCENTAGE', 'Percentage'),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='coupons')
    code = models.CharField(max_length=64)
    discount_type = models.CharField(max_length=24, choices=DISCOUNT_TYPE_CHOICES, default='PERCENTAGE')
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    max_uses = models.IntegerField(null=True, blank=True, help_text="Maximum total uses allowed")
    current_uses = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'code'], name='unique_tenant_coupon_code'),
        ]

    def clean(self):
        if self.discount_value < 0:
            raise ValidationError("Discount value cannot be negative.")
        if self.discount_type == 'PERCENTAGE' and self.discount_value > 100:
            raise ValidationError("Percentage discount cannot exceed 100.")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError("Valid from date must be before valid until date.")

    def save(self, *args, **kwargs):
        # Enforce uppercase alphanumeric if we wanted, but let's just do uppercase
        self.code = self.code.upper().strip()
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.discount_value} {self.discount_type}"
