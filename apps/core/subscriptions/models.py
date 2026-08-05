import uuid
from django.db import models
from django.conf import settings
from apps.core.tenants.models import Tenant
from apps.core.common.models import BaseModel

class Product(BaseModel):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'product'

    def save(self, *args, **kwargs):
        if self.code:
            import re
            cleaned = re.sub(r'[^A-Za-z0-9_.-]', '_', self.code.strip())
            cleaned = re.sub(r'_+', '_', cleaned).strip('_').upper()
            if cleaned:
                self.code = cleaned
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class SubscriptionPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    billing_cycle = models.CharField(max_length=32, default='MONTHLY') # e.g. MONTHLY, YEARLY
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    is_active = models.BooleanField(default=True)
    products = models.ManyToManyField(Product, through='SubscriptionPlanProduct', related_name='plans')

    class Meta:
        db_table = 'subscription_plan'

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}/{self.billing_cycle}"


class SubscriptionPlanProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='plan_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_plans')

    class Meta:
        db_table = 'subscription_plan_product'
        unique_together = ('plan', 'product')


class SubscriptionEntitlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name='entitlements')
    feature_code = models.CharField(max_length=120, db_index=True)
    limit_type = models.CharField(max_length=32) # BOOLEAN, NUMERIC, JSON
    limit_value = models.JSONField(null=True, blank=True) # supports boolean, numeric, json

    class Meta:
        db_table = 'subscription_entitlement'
        unique_together = ('plan', 'feature_code')

    def __str__(self):
        return f"{self.plan.name} - {self.feature_code}: {self.limit_value}"


class TenantSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, null=True, blank=True, related_name='tenant_subscriptions')
    is_custom = models.BooleanField(default=False)
    custom_name = models.CharField(max_length=120, null=True, blank=True)
    billing_cycle = models.CharField(max_length=32, default='MONTHLY') # e.g. MONTHLY, YEARLY
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, default='USD')
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=32, default='ACTIVE') # ACTIVE, EXPIRED, CANCELLED

    class Meta:
        db_table = 'tenant_subscription'

    def __str__(self):
        plan_str = self.plan.name if self.plan else (self.custom_name or "Custom Subscription")
        return f"{self.tenant.name} - {plan_str} ({self.status})"


class ProductFeature(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name='product_features')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='features')
    code = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'product_feature'
        unique_together = ('product', 'code')
        indexes = [
            models.Index(fields=['product', 'code']),
        ]

    def save(self, *args, **kwargs):
        if self.code:
            import re
            cleaned = re.sub(r'[^A-Za-z0-9_.-]', '_', self.code.strip())
            cleaned = re.sub(r'_+', '_', cleaned).strip('_').upper()
            if cleaned:
                self.code = cleaned
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.code}:{self.code} (${self.price})"


class TenantSubscriptionFeature(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_subscription = models.ForeignKey(TenantSubscription, on_delete=models.CASCADE, related_name='features')
    product_feature = models.ForeignKey(ProductFeature, on_delete=models.CASCADE, related_name='tenant_subscription_features')
    feature_code = models.CharField(max_length=64, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'tenant_subscription_feature'
        unique_together = ('tenant_subscription', 'product_feature')

    def __str__(self):
        return f"{self.tenant_subscription.tenant.name} - {self.feature_code} (${self.price})"


class TenantProduct(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='tenant_products')
    tenant_subscription = models.ForeignKey(TenantSubscription, on_delete=models.CASCADE, related_name='tenant_products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='tenant_products')
    activated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=32, default='ACTIVE') # ACTIVE, SUSPENDED, EXPIRED

    class Meta:
        db_table = 'tenant_product'
        unique_together = ('tenant', 'product')

    def __str__(self):
        return f"{self.tenant.name} - {self.product.code} ({self.status})"


class TenantProductLicense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_product = models.ForeignKey(TenantProduct, on_delete=models.CASCADE, related_name='licenses')
    license_key = models.CharField(max_length=255, unique=True, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField()
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='issued_licenses')
    last_validated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default='ACTIVE') # ACTIVE, SUSPENDED, EXPIRED

    class Meta:
        db_table = 'tenant_product_license'
        indexes = [
            models.Index(fields=['license_key']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.license_key} - {self.status}"


class TenantProductEntitlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_product = models.ForeignKey(TenantProduct, on_delete=models.CASCADE, related_name='entitlements')
    product_feature = models.ForeignKey(ProductFeature, on_delete=models.SET_NULL, null=True, blank=True, related_name='entitlements')
    feature_code = models.CharField(max_length=64, db_index=True)
    limit_type = models.CharField(max_length=32) # BOOLEAN, NUMERIC, JSON
    limit_value_boolean = models.BooleanField(default=False)
    limit_value_numeric = models.IntegerField(null=True, blank=True)
    limit_value_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'tenant_product_entitlement'
        unique_together = ('tenant_product', 'feature_code')

    def __str__(self):
        return f"{self.tenant_product.product.code}:{self.feature_code}"


class TenantProductUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_product = models.ForeignKey(TenantProduct, on_delete=models.CASCADE, related_name='usages')
    metric_code = models.CharField(max_length=64, db_index=True)
    usage_value = models.IntegerField(default=0)
    usage_limit = models.IntegerField(default=0)
    percentage_used = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    last_calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_product_usage'
        unique_together = ('tenant_product', 'metric_code')
        indexes = [
            models.Index(fields=['tenant_product', 'metric_code']),
        ]

    def __str__(self):
        return f"{self.tenant_product.tenant.name} - {self.metric_code}: {self.usage_value}/{self.usage_limit}"


class SubscriptionRequest(BaseModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='subscription_requests')
    product_name = models.CharField(max_length=120)
    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    comments = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=32, default='PENDING') # PENDING, APPROVED, REJECTED
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subscription_request'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.product_name} ({self.status})"

