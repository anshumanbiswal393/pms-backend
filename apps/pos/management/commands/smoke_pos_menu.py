"""
Smoke-test Part 2 menu catalog against the live PMS PostgreSQL DB.

Creates temporary rows inside an atomic block and always rolls back.

  python manage.py smoke_pos_menu
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import RequestFactory

from apps.core.tenants.models import Tenant, Property
from apps.POS.models import Outlet, MenuCategory, MenuItem
from apps.POS.services.menu import MenuCatalogService
from apps.POS.views import BillingMenuCatalogAPIView, MenuItemViewSet


class Command(BaseCommand):
    help = "Atomic rollback smoke test for POS menu on PostgreSQL."

    def handle(self, *args, **options):
        from django.conf import settings

        engine = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in engine:
            raise CommandError(f"Expected PostgreSQL, got {engine}")

        with transaction.atomic():
            tenant = Tenant.objects.first()
            prop = Property.objects.filter(tenant=tenant).first() if tenant else None
            if not tenant or not prop:
                raise CommandError("Need at least one Tenant/Property in PMS DB.")

            outlet = Outlet.objects.create(
                tenant=tenant,
                property=prop,
                code="SMOKE-P2",
                name="Smoke Menu Outlet",
                outlet_type="PRIMARY",
                is_active=True,
            )
            tax = MenuCatalogService.resolve_or_create_tax_profile(
                tenant_id=tenant.id,
                property_id=prop.id,
                rate=Decimal("5"),
            )
            cat = MenuCategory.objects.create(
                outlet=outlet,
                code="STARTERS",
                name="Starters",
                sort_order=1,
                is_active=True,
            )
            item = MenuItem.objects.create(
                outlet=outlet,
                category=cat,
                tax_profile=tax,
                code="#SMOKE-101",
                name="Smoke Paneer",
                item_type="VEG",
                price=Decimal("199.00"),
                status="ACTIVE",
            )

            catalog = MenuCatalogService.billing_catalog(outlet_id=outlet.id)
            assert catalog["count"] == 1, catalog
            assert catalog["items"][0]["code"] == "#SMOKE-101"
            assert catalog["items"][0]["taxRate"] == 5.0

            factory = RequestFactory()
            list_view = MenuItemViewSet.as_view({"get": "list"})
            req = factory.get("/api/pos/menu/items/", {"outletId": str(outlet.id)})
            resp = list_view(req)
            assert resp.status_code == 200, resp.data
            assert any(i["code"] == "#SMOKE-101" for i in resp.data)

            bill_view = BillingMenuCatalogAPIView.as_view()
            req2 = factory.get("/api/pos/billing/menu/", {"outlet_id": str(outlet.id)})
            resp2 = bill_view(req2)
            assert resp2.status_code == 200, resp2.data
            assert resp2.data["count"] == 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"PostgreSQL smoke OK — outlet={outlet.id} item={item.id} "
                    f"host={settings.DATABASES['default'].get('HOST')}"
                )
            )
            transaction.set_rollback(True)

        self.stdout.write("Rolled back smoke rows (no lasting DB changes).")
