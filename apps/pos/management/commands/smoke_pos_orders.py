"""
Atomic rollback smoke test for Part 3 Orders + KOT on PMS PostgreSQL.

  python manage.py smoke_pos_orders
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.POS.models import Outlet, MenuCategory, MenuItem
from apps.POS.services.menu import MenuCatalogService
from apps.POS.services.orders import OrderService
from apps.core.tenants.models import Tenant, Property


class Command(BaseCommand):
    help = "Atomic rollback smoke test for POS orders/KOT on PostgreSQL."

    def handle(self, *args, **options):
        from django.conf import settings

        if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
            raise CommandError("Expected PostgreSQL DATABASE_URL.")

        with transaction.atomic():
            outlet = Outlet.objects.filter(deleted_at__isnull=True, is_active=True).first()
            if not outlet:
                tenant = Tenant.objects.first()
                prop = Property.objects.filter(tenant=tenant).first() if tenant else None
                if not tenant or not prop:
                    raise CommandError("No outlet/tenant/property available.")
                outlet = Outlet.objects.create(
                    tenant=tenant,
                    property=prop,
                    code="SMOKE-ORD",
                    name="Smoke Orders Outlet",
                    outlet_type="PRIMARY",
                    is_active=True,
                )

            cat = MenuCategory.objects.filter(outlet=outlet).first()
            if not cat:
                cat = MenuCategory.objects.create(
                    outlet=outlet, code="STARTERS", name="Starters", is_active=True
                )
            tax = MenuCatalogService.resolve_or_create_tax_profile(
                tenant_id=outlet.tenant_id,
                property_id=outlet.property_id,
                rate=Decimal("5"),
            )
            item = MenuItem.objects.filter(outlet=outlet, status="ACTIVE").first()
            if not item:
                item = MenuItem.objects.create(
                    outlet=outlet,
                    category=cat,
                    tax_profile=tax,
                    code="#SMOKE-ORD-1",
                    name="Smoke Tikka",
                    item_type="VEG",
                    price=Decimal("250.00"),
                    status="ACTIVE",
                )

            created = OrderService.create_order(
                {
                    "outlet_id": str(outlet.id),
                    "order_type": "DINE_IN",
                    "table_number": "T-99",
                    "section": "Garden",
                    "guest_name": "Smoke Guest",
                    "pax": 2,
                    "items": [
                        {
                            "menu_item_id": str(item.id),
                            "name": item.name,
                            "code": item.code,
                            "quantity": 2,
                            "price": str(item.price),
                        }
                    ],
                    "send_kot": True,
                }
            )
            assert created["status"] == "PLACED", created
            assert created.get("kotId") == 1, created
            order_id = created["id"]

            advanced = OrderService.advance_stage(order_id)
            assert advanced["status"] == "PREPARED", advanced

            updated = OrderService.update_order_items(
                order_id,
                {
                    "items": [
                        {
                            "menu_item_id": str(item.id),
                            "name": item.name,
                            "quantity": 3,
                            "price": str(item.price),
                        }
                    ],
                },
            )
            assert updated["status"] == "PLACED", updated
            assert updated.get("kotId") == 2, updated
            assert len(updated["items"]) == 1
            assert updated["items"][0]["quantity"] == 3.0

            current = OrderService.list_current(outlet_id=outlet.id)
            assert any(o["id"] == order_id for o in current), current

            kots = OrderService.list_kot(outlet_id=outlet.id)
            assert kots["count"] >= 1, kots

            self.stdout.write(
                self.style.SUCCESS(
                    f"PostgreSQL orders smoke OK — order={created['orderNumber']} "
                    f"host={settings.DATABASES['default'].get('HOST')}"
                )
            )
            transaction.set_rollback(True)

        self.stdout.write("Rolled back smoke rows (no lasting DB changes).")
