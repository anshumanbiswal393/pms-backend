import logging
from django.utils import timezone
from decimal import Decimal
from django.db.models import F
from apps.core.subscriptions.models import (
    Product, ProductFeature, TenantProduct, TenantProductLicense, TenantProductEntitlement, TenantProductUsage
)
from apps.core.tenants.models import Tenant

logger = logging.getLogger(__name__)

class ProductAccessService:
    @staticmethod
    def has_product(tenant, product_code):
        """
        Verify if a product is active for a given tenant.
        """
        if not tenant:
            return False
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        return TenantProduct.objects.filter(
            tenant_id=tenant_id,
            product__code=product_code,
            status='ACTIVE',
            tenant_subscription__status='ACTIVE',
            expires_at__gt=timezone.now()
        ).exists()

    @staticmethod
    def has_feature(tenant, feature_code):
        """
        Verify if a feature is active/entitled for a tenant.
        """
        if not tenant:
            return False
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        # Check if tenant has active product associated with this feature
        # And if there's a specific entitlement that overrides it
        entitlement = TenantProductEntitlement.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            tenant_product__tenant_subscription__status='ACTIVE',
            tenant_product__expires_at__gt=timezone.now(),
            feature_code=feature_code
        ).first()

        if entitlement:
            if entitlement.limit_type == 'BOOLEAN':
                return entitlement.limit_value_boolean
            elif entitlement.limit_type == 'NUMERIC':
                return entitlement.limit_value_numeric > 0 if entitlement.limit_value_numeric is not None else False
            return True

        # Fallback: check if feature starts with PMS. / CRM. / HOUSEKEEPING.
        if feature_code.startswith('PMS.'):
            return ProductAccessService.has_product(tenant_id, 'PMS')
        elif feature_code.startswith('CRM.'):
            return ProductAccessService.has_product(tenant_id, 'CRM')
        elif feature_code.startswith('HOUSEKEEPING.'):
            return ProductAccessService.has_product(tenant_id, 'HOUSEKEEPING')

        # Fallback: check if the feature is registered under any active tenant product
        return ProductFeature.objects.filter(
            code=feature_code,
            is_active=True,
            product__tenant_products__tenant_id=tenant_id,
            product__tenant_products__status='ACTIVE',
            product__tenant_products__tenant_subscription__status='ACTIVE',
            product__tenant_products__expires_at__gt=timezone.now()
        ).exists()

    @staticmethod
    def provision_tenant_products(tenant, created_by=None):
        """
        Automatically provisions default active products (PMS, CRM, HOUSEKEEPING), licenses, and entitlements for a tenant.
        """
        import uuid
        from apps.core.subscriptions.models import SubscriptionPlan, TenantSubscription

        # 1. Ensure Products exist
        products_data = [
            ("PMS", "Property Management System"),
            ("CRM", "Customer Relationship Management"),
            ("HOUSEKEEPING", "Housekeeping & Maintenance")
        ]
        product_objs = {}
        for code, name in products_data:
            p_obj, _ = Product.objects.get_or_create(code=code, defaults={"name": name, "is_active": True})
            product_objs[code] = p_obj

        # 2. Ensure Subscription Plan & Tenant Subscription
        plan, _ = SubscriptionPlan.objects.get_or_create(
            name="Enterprise Annual",
            defaults={"billing_cycle": "YEARLY", "price": Decimal("2499.00"), "currency": "USD", "is_active": True}
        )
        tenant_sub, _ = TenantSubscription.objects.get_or_create(
            tenant=tenant,
            plan=plan,
            defaults={
                "start_date": timezone.now().date(),
                "end_date": timezone.now().date() + timezone.timedelta(days=3650),
                "status": "ACTIVE"
            }
        )
        if tenant_sub.status != 'ACTIVE':
            tenant_sub.status = 'ACTIVE'
            tenant_sub.save()

        # 3. Provision Tenant Products
        tenant_product_objs = {}
        for p_code in ["PMS", "CRM", "HOUSEKEEPING"]:
            tp, _ = TenantProduct.objects.get_or_create(
                tenant=tenant,
                product=product_objs[p_code],
                defaults={
                    "tenant_subscription": tenant_sub,
                    "activated_at": timezone.now(),
                    "expires_at": timezone.now() + timezone.timedelta(days=3650),
                    "status": "ACTIVE"
                }
            )
            if tp.status != 'ACTIVE':
                tp.status = 'ACTIVE'
                tp.save()
            tenant_product_objs[p_code] = tp

        # 4. Provision Licenses
        for p_code, tp in tenant_product_objs.items():
            if not TenantProductLicense.objects.filter(tenant_product=tp, status="ACTIVE").exists():
                license_key = f"LIC-{p_code}-{uuid.uuid4().hex[:12].upper()}"
                TenantProductLicense.objects.create(
                    tenant_product=tp,
                    license_key=license_key,
                    start_date=timezone.now().date(),
                    end_date=timezone.now().date() + timezone.timedelta(days=3650),
                    issued_by=created_by,
                    status="ACTIVE"
                )

        # 5. Provision Entitlements
        entitlements_to_seed = [
            ("PMS", "PMS.RESERVATIONS", "BOOLEAN", True),
            ("PMS", "PMS.RATES", "BOOLEAN", True),
            ("PMS", "PMS.INVENTORY", "BOOLEAN", True),
            ("PMS", "MAX_ROOMS", "NUMERIC", 500),
            ("PMS", "MAX_USERS", "NUMERIC", 50),
            ("PMS", "ADVANCED_REPORTS", "BOOLEAN", True),
            ("PMS", "MULTI_PROPERTY", "BOOLEAN", True),
            ("CRM", "CRM.GUESTS", "BOOLEAN", True),
            ("CRM", "MAX_LEADS", "NUMERIC", 5000),
            ("CRM", "API_ACCESS", "BOOLEAN", True),
            ("HOUSEKEEPING", "HOUSEKEEPING.MAINTENANCE", "BOOLEAN", True),
            ("HOUSEKEEPING", "MAX_ASSETS", "NUMERIC", 1000)
        ]

        for p_code, f_code, limit_type, limit_val in entitlements_to_seed:
            tp = tenant_product_objs.get(p_code)
            if not tp:
                continue
            
            defaults = {"limit_type": limit_type}
            if limit_type == "BOOLEAN":
                defaults["limit_value_boolean"] = limit_val
            elif limit_type == "NUMERIC":
                defaults["limit_value_numeric"] = limit_val
            elif limit_type == "JSON":
                defaults["limit_value_json"] = limit_val

            TenantProductEntitlement.objects.update_or_create(
                tenant_product=tp,
                feature_code=f_code,
                defaults=defaults
            )


class LicenseValidationService:
    @staticmethod
    def validate_license(license_key):
        """
        Validate license and update last_validated_at if valid.
        """
        try:
            license_obj = TenantProductLicense.objects.get(license_key=license_key)
        except TenantProductLicense.DoesNotExist:
            return False

        now = timezone.now()
        today = now.date()

        if license_obj.status != 'ACTIVE':
            return False

        if today < license_obj.start_date or today > license_obj.end_date:
            license_obj.status = 'EXPIRED'
            license_obj.save()
            return False

        license_obj.last_validated_at = now
        license_obj.save()
        return True

    @staticmethod
    def is_license_expired(license_key):
        try:
            license_obj = TenantProductLicense.objects.get(license_key=license_key)
        except TenantProductLicense.DoesNotExist:
            return True
        return license_obj.status == 'EXPIRED' or timezone.now().date() > license_obj.end_date

    @staticmethod
    def is_license_active(license_key):
        try:
            license_obj = TenantProductLicense.objects.get(license_key=license_key)
        except TenantProductLicense.DoesNotExist:
            return False
        today = timezone.now().date()
        return license_obj.status == 'ACTIVE' and license_obj.start_date <= today <= license_obj.end_date


class EntitlementValidationService:
    @staticmethod
    def get_limit(tenant, feature_code):
        """
        Get the limit value for a feature.
        """
        if not tenant:
            return None
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        entitlement = TenantProductEntitlement.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            tenant_product__tenant_subscription__status='ACTIVE',
            tenant_product__expires_at__gt=timezone.now(),
            feature_code=feature_code
        ).first()
        if not entitlement:
            return None
        if entitlement.limit_type == 'BOOLEAN':
            return entitlement.limit_value_boolean
        elif entitlement.limit_type == 'NUMERIC':
            return entitlement.limit_value_numeric
        elif entitlement.limit_type == 'JSON':
            return entitlement.limit_value_json
        return None

    @staticmethod
    def has_entitlement(tenant, feature_code):
        """
        Check if entitlement is active and boolean limit is True. Fallback to product check if limit is None.
        """
        limit = EntitlementValidationService.get_limit(tenant, feature_code)
        if limit is not None:
            if isinstance(limit, bool):
                return limit
            return True
        return ProductAccessService.has_feature(tenant, feature_code)

    @staticmethod
    def validate_limit(tenant, feature_code, current_value):
        """
        Validate if current_value is within the entitlement limit.
        """
        if not tenant:
            return False
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        entitlement = TenantProductEntitlement.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            tenant_product__tenant_subscription__status='ACTIVE',
            tenant_product__expires_at__gt=timezone.now(),
            feature_code=feature_code
        ).first()

        if not entitlement:
            return ProductAccessService.has_feature(tenant, feature_code)

        if entitlement.limit_type == 'BOOLEAN':
            return entitlement.limit_value_boolean
        elif entitlement.limit_type == 'NUMERIC':
            if entitlement.limit_value_numeric is None:
                return True
            return current_value <= entitlement.limit_value_numeric
        return True


class UsageTrackingService:
    @staticmethod
    def increment_usage(tenant, metric_code, amount=1):
        """
        Increment live usage consumption.
        """
        if not tenant:
            return None
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        usage = TenantProductUsage.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            metric_code=metric_code
        ).first()

        if not usage:
            # Try to create usage record if a tenant product exists
            tenant_prod = TenantProduct.objects.filter(
                tenant_id=tenant_id,
                status='ACTIVE'
            ).first()
            if not tenant_prod:
                return None
            usage = TenantProductUsage.objects.create(
                tenant_product=tenant_prod,
                metric_code=metric_code,
                usage_value=0,
                usage_limit=100  # Default fallback limit
            )

        usage.usage_value += amount
        if usage.usage_limit > 0:
            usage.percentage_used = Decimal(round((usage.usage_value / usage.usage_limit) * 100, 2))
        else:
            usage.percentage_used = Decimal('0.00')
        usage.save()
        return usage

    @staticmethod
    def decrement_usage(tenant, metric_code, amount=1):
        """
        Decrement live usage consumption.
        """
        if not tenant:
            return None
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        usage = TenantProductUsage.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            metric_code=metric_code
        ).first()

        if not usage:
            return None

        usage.usage_value = max(0, usage.usage_value - amount)
        if usage.usage_limit > 0:
            usage.percentage_used = Decimal(round((usage.usage_value / usage.usage_limit) * 100, 2))
        else:
            usage.percentage_used = Decimal('0.00')
        usage.save()
        return usage

    @staticmethod
    def recalculate_usage(tenant, metric_code):
        """
        Recalculate usage from actual database models based on metric code.
        """
        if not tenant:
            return None
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        usage = TenantProductUsage.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE',
            metric_code=metric_code
        ).first()

        if not usage:
            return None

        # Query actual counts based on metric_code
        actual_value = 0
        if metric_code == 'ROOMS_USED':
            from apps.features.inventory.models import InventoryUnit
            actual_value = InventoryUnit.objects.filter(property__tenant_id=tenant_id).count()
        elif metric_code == 'ACTIVE_USERS':
            from apps.core.accounts.models import AppUser
            actual_value = AppUser.objects.filter(tenant_id=tenant_id, is_active=True).count()
        elif metric_code == 'PROPERTIES_USED':
            from apps.core.tenants.models import Property
            actual_value = Property.objects.filter(tenant_id=tenant_id).count()
        elif metric_code == 'ACTIVE_RESERVATIONS':
            from apps.features.reservations.models import Reservation
            actual_value = Reservation.objects.filter(tenant_id=tenant_id, status='CONFIRMED').count()
        else:
            # If not automated, keep current usage_value
            actual_value = usage.usage_value

        usage.usage_value = actual_value
        if usage.usage_limit > 0:
            usage.percentage_used = Decimal(round((usage.usage_value / usage.usage_limit) * 100, 2))
        else:
            usage.percentage_used = Decimal('0.00')
        usage.save()
        return usage

    @staticmethod
    def get_usage_summary(tenant):
        """
        Get all usage metrics summary for the tenant.
        """
        if not tenant:
            return []
        tenant_id = tenant.id if hasattr(tenant, 'id') else tenant
        usages = TenantProductUsage.objects.filter(
            tenant_product__tenant_id=tenant_id,
            tenant_product__status='ACTIVE'
        )
        summary = []
        for u in usages:
            summary.append({
                'metric_code': u.metric_code,
                'usage_value': u.usage_value,
                'usage_limit': u.usage_limit,
                'percentage_used': float(u.percentage_used),
                'last_calculated_at': u.last_calculated_at
            })
        return summary
