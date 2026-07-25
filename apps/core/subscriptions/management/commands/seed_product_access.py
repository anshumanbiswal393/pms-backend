from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.core.subscriptions.models import (
    Product, ProductFeature, TenantProduct, TenantProductLicense,
    TenantProductEntitlement, TenantProductUsage, TenantSubscription, SubscriptionPlan
)
from apps.core.tenants.models import Tenant
from apps.core.accounts.models import AppUser
import uuid

class Command(BaseCommand):
    help = 'Seeds product features, assignments, licenses, entitlements, and usage tracking records.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding Product Access Catalog...")

        # 1. Ensure Products Exist
        products_data = [
            {"code": "PMS", "name": "Property Management System", "description": "Core PMS module"},
            {"code": "POS", "name": "Point of Sale", "description": "F&B and Retail billing"},
            {"code": "CRM", "name": "Guest CRM", "description": "Loyalty and guest profile tracking"},
            {"code": "HOUSEKEEPING", "name": "Housekeeping & Maintenance", "description": "Mobile task and maintenance logs"},
            {"code": "CHANNEL_MANAGER", "name": "Channel Manager Link", "description": "OTA distribution sync"},
            {"code": "REVENUE_MANAGEMENT", "name": "Revenue Management", "description": "Dynamic pricing engine"},
            {"code": "ANALYTICS", "name": "Business Analytics", "description": "Advanced BI and reporting tools"},
        ]

        product_objs = {}
        for p in products_data:
            obj, _ = Product.objects.update_or_create(code=p["code"], defaults=p)
            product_objs[p["code"]] = obj
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(product_objs)} base products."))

        # 2. Seed Product Features
        features_data = {
            "PMS": [
                {"code": "PMS.RESERVATIONS", "name": "Reservations Management"},
                {"code": "PMS.GUESTS", "name": "Guest CRM & Registration"},
                {"code": "PMS.RATES", "name": "Rate & Pricing Management"},
                {"code": "PMS.CHECKIN", "name": "Check-in & Front Desk Operations"},
            ],
            "POS": [
                {"code": "POS.BILLING", "name": "Restaurant Billing"},
                {"code": "POS.KOT", "name": "Kitchen Order Tickets"},
                {"code": "POS.SETTLEMENT", "name": "POS Cash Settlement"},
            ],
            "CRM": [
                {"code": "CRM.LEADS", "name": "Lead Management"},
                {"code": "CRM.CAMPAIGNS", "name": "Marketing Campaigns"},
            ],
            "HOUSEKEEPING": [
                {"code": "HOUSEKEEPING.MAINTENANCE", "name": "Maintenance & Work Orders"},
                {"code": "HOUSEKEEPING.ASSETS", "name": "Asset & Inventory Tracking"},
            ]
        }

        feature_count = 0
        for p_code, feats in features_data.items():
            prod_obj = product_objs[p_code]
            for f in feats:
                ProductFeature.objects.update_or_create(
                    product=prod_obj,
                    code=f["code"],
                    defaults={
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "is_active": True
                    }
                )
                feature_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {feature_count} product features."))

        # 3. Resolve Tenant to Seed Samples
        tenant = Tenant.objects.first()
        if not tenant:
            tenant, _ = Tenant.objects.update_or_create(
                subdomain="grandpalace",
                defaults={"name": "Grand Palace Hotel", "status": "active"}
            )
            self.stdout.write(self.style.SUCCESS(f"Created default tenant '{tenant.subdomain}' for seeding."))

        # Ensure active Subscription Plan and Tenant Subscription
        plan, _ = SubscriptionPlan.objects.update_or_create(
            name="Enterprise Annual",
            defaults={
                "billing_cycle": "YEARLY",
                "price": 2499.00,
                "currency": "USD",
                "is_active": True
            }
        )
        tenant_sub, _ = TenantSubscription.objects.update_or_create(
            tenant=tenant,
            plan=plan,
            defaults={
                "start_date": timezone.now().date(),
                "end_date": timezone.now().date() + timezone.timedelta(days=365),
                "status": "ACTIVE"
            }
        )

        # 4. Tenant Product Activation (PMS, CRM, HOUSEKEEPING)
        activated_prods = ["PMS", "CRM", "HOUSEKEEPING"]
        tenant_product_objs = {}
        for p_code in activated_prods:
            prod_obj = product_objs[p_code]
            tp, _ = TenantProduct.objects.update_or_create(
                tenant=tenant,
                product=prod_obj,
                defaults={
                    "tenant_subscription": tenant_sub,
                    "activated_at": timezone.now(),
                    "expires_at": timezone.now() + timezone.timedelta(days=365),
                    "status": "ACTIVE"
                }
            )
            tenant_product_objs[p_code] = tp

        self.stdout.write(self.style.SUCCESS(f"Activated {len(activated_prods)} products for tenant {tenant.name}."))

        # 5. Seed Licenses
        superuser = AppUser.objects.filter(is_superuser=True).first()
        license_count = 0
        for p_code, tp in tenant_product_objs.items():
            license_key = f"LIC-{p_code}-{uuid.uuid4().hex[:12].upper()}"
            TenantProductLicense.objects.update_or_create(
                tenant_product=tp,
                status="ACTIVE",
                defaults={
                    "license_key": license_key,
                    "start_date": timezone.now().date(),
                    "end_date": timezone.now().date() + timezone.timedelta(days=365),
                    "issued_by": superuser
                }
            )
            license_count += 1
        self.stdout.write(self.style.SUCCESS(f"Generated {license_count} active product licenses."))

        entitlements_to_seed = [
            ("PMS", "MAX_ROOMS", "NUMERIC", 150),
            ("PMS", "MAX_USERS", "NUMERIC", 20),
            ("PMS", "ADVANCED_REPORTS", "BOOLEAN", True),
            ("PMS", "MULTI_PROPERTY", "BOOLEAN", False),
            ("CRM", "MAX_LEADS", "NUMERIC", 1000),
            ("CRM", "API_ACCESS", "BOOLEAN", True),
            ("HOUSEKEEPING", "MAX_ASSETS", "NUMERIC", 500),
            ("HOUSEKEEPING", "HOUSEKEEPING.MAINTENANCE", "BOOLEAN", True)
        ]

        ent_count = 0
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
            ent_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {ent_count} entitlements for tenant {tenant.name}."))

        # 7. Seed Usage Records
        usages_to_seed = [
            ("PMS", "ROOMS_USED", 45, 150),
            ("PMS", "ACTIVE_USERS", 12, 20),
            ("CRM", "LEADS_USED", 150, 1000),
            ("HOUSEKEEPING", "ASSETS_USED", 80, 500)
        ]

        usage_count = 0
        for p_code, metric_code, val, limit in usages_to_seed:
            tp = tenant_product_objs.get(p_code)
            if not tp:
                continue
            percentage = round((val / limit) * 100, 2)
            TenantProductUsage.objects.update_or_create(
                tenant_product=tp,
                metric_code=metric_code,
                defaults={
                    "usage_value": val,
                    "usage_limit": limit,
                    "percentage_used": percentage
                }
            )
            usage_count += 1
        self.stdout.write(self.style.SUCCESS(f"Seeded {usage_count} usage tracking metrics."))

        self.stdout.write(self.style.SUCCESS("All Product Access, License & Entitlement seed data successfully seeded!"))
