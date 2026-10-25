"""
Atomic rollback smoke for Part 6 stock/recipe/settle deduction.

  python manage.py check_pos_db
  python manage.py smoke_pos_stock
"""
from decimal import Decimal
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.tenants.models import Tenant, Property
from apps.POS.models import Outlet, MenuCategory, MenuItem, POSOrder, POSStockItem
from apps.POS.services.menu import MenuCatalogService
from apps.POS.services.orders import OrderService
from apps.POS.services.stock import StockService, ReportService, AggregatorWebhookService


class Command(BaseCommand):
    help = "Atomic rollback smoke for POS stock BOM deduction + reports."

    def handle(self, *args, **options):
        call_command("check_pos_db")

        with transaction.atomic():
            tenant = Tenant.objects.first()
            prop = Property.objects.filter(tenant=tenant).first() if tenant else None
            if not tenant or not prop:
                raise CommandError("Need Tenant + Property.")

            outlet = Outlet.objects.filter(
                property=prop, deleted_at__isnull=True, is_active=True
            ).first()
            if not outlet:
                outlet = Outlet.objects.create(
                    tenant=tenant,
                    property=prop,
                    code="SMOKE-STK",
                    name="Smoke Stock Outlet",
                    outlet_type="PRIMARY",
                    is_active=True,
                )

            cat = MenuCategory.objects.filter(outlet=outlet).first()
            if not cat:
                cat = MenuCategory.objects.create(
                    outlet=outlet, name="Mains", is_active=True
                )
            tax = MenuCatalogService.resolve_or_create_tax_profile(
                tenant_id=tenant.id, property_id=prop.id, rate=Decimal("5")
            )
            # Dedicated menu item so recipe is guaranteed on the ordered SKU.
            suffix = uuid4().hex[:8].upper()
            item = MenuItem.objects.create(
                outlet=outlet,
                category=cat,
                tax_profile=tax,
                code=f"#SMOKE-STK-{suffix}",
                name=f"Smoke Butter Chicken {suffix}",
                item_type="NON_VEG",
                price=Decimal("520.00"),
                status="ACTIVE",
            )

            rice = StockService.upsert_stock(
                {
                    "tenant_id": str(tenant.id),
                    "property_id": str(prop.id),
                    "outlet_id": str(outlet.id),
                    "code": f"RM-RICE-{suffix}",
                    "name": "Basmati Rice Smoke",
                    "category": "Groceries",
                    "unit": "Kg",
                    "quantity_on_hand": "10",
                    "reorder_level": "2",
                }
            )
            butter = StockService.upsert_stock(
                {
                    "tenant_id": str(tenant.id),
                    "property_id": str(prop.id),
                    "outlet_id": str(outlet.id),
                    "code": f"RM-BUTTER-{suffix}",
                    "name": "Amul Butter Smoke",
                    "category": "Dairy",
                    "unit": "Kg",
                    "quantity_on_hand": "5",
                    "reorder_level": "1",
                }
            )

            recipe = StockService.set_recipe(
                item.id,
                name="Butter Chicken BOM",
                yield_qty=1,
                ingredients=[
                    {"stockItemId": rice["id"], "quantity": "0.150"},
                    {"stockItemId": butter["id"], "quantity": "0.050"},
                ],
            )
            assert len(recipe["ingredients"]) == 2, recipe

            created = OrderService.create_order(
                {
                    "outlet_id": str(outlet.id),
                    "order_type": "DINE_IN",
                    "table_number": "T-8",
                    "items": [
                        {
                            "menu_item_id": str(item.id),
                            "name": item.name,
                            "code": item.code,
                            "quantity": 2,
                            "price": str(item.price),
                        }
                    ],
                    "grand_total": str(Decimal(item.price) * 2),
                }
            )
            settled = OrderService.settle_order(
                created["id"], {"payment_mode": "CASH"}
            )
            assert settled["status"] == "SETTLED", settled
            stock_info = settled.get("stockDeduction") or {}
            assert stock_info.get("deducted") is True, stock_info
            assert stock_info.get("count") == 2, stock_info

            rice_row = POSStockItem.objects.get(id=rice["id"])
            butter_row = POSStockItem.objects.get(id=butter["id"])
            # 2 portions * 0.150 / 0.050
            assert Decimal(str(rice_row.quantity_on_hand)) == Decimal("9.700"), rice_row.quantity_on_hand
            assert Decimal(str(butter_row.quantity_on_hand)) == Decimal("4.900"), butter_row.quantity_on_hand

            # Idempotent second deduct
            order = POSOrder.objects.get(id=created["id"])
            again = StockService.deduct_for_order(order)
            assert again["deducted"] is False
            assert Decimal(str(POSStockItem.objects.get(id=rice["id"]).quantity_on_hand)) == Decimal(
                "9.700"
            )

            sales = ReportService.sales_report(outlet_id=outlet.id)
            assert sales["count"] >= 1
            stock_rep = ReportService.stock_report(outlet_id=outlet.id)
            assert stock_rep["count"] >= 2
            cons = ReportService.consumption_report(outlet_id=outlet.id)
            assert cons["count"] >= 1

            wh = AggregatorWebhookService.receive(
                {
                    "provider": "zomato",
                    "eventType": "ORDER_NEW",
                    "tenantId": str(tenant.id),
                    "propertyId": str(prop.id),
                }
            )
            assert wh["success"] is True

            self.stdout.write(
                self.style.SUCCESS(
                    f"PostgreSQL stock smoke OK — rice={rice_row.quantity_on_hand} "
                    f"butter={butter_row.quantity_on_hand} sales={sales['count']}"
                )
            )
            transaction.set_rollback(True)

        self.stdout.write("Rolled back smoke rows (no lasting DB changes).")
