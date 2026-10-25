from datetime import date
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.POS.models import MenuCategory, MenuItem, POSOrder, POSOrderItem, POSRecipe, POSStockMovement
from apps.POS.services.stock import StockService
from .helpers import make_sku, make_tenant_property_outlet, unique_suffix


class StockLedgerTests(TestCase):
    def setUp(self):
        self.suffix = unique_suffix()
        self.tenant, self.prop, self.outlet = make_tenant_property_outlet(self.suffix)
        self.rice = make_sku(
            tenant=self.tenant,
            prop=self.prop,
            outlet=self.outlet,
            code=f"RICE-{self.suffix[:6]}",
            name="Basmati Rice",
            qty=6,
            reorder=4,
            par=8,
            unit_cost=90,
        )

    def test_serialize_stock_includes_par_kind_favorite(self):
        payload = StockService.serialize_stock(self.rice)
        self.assertEqual(payload["parLevel"], 8)
        self.assertEqual(payload["itemKind"], "RAW")
        self.assertFalse(payload["isFavorite"])
        self.assertFalse(payload["isLow"])
        self.assertTrue(payload["isAtPar"])

    def test_insufficient_stock_raises(self):
        with self.assertRaises(ValidationError):
            StockService.adjust_stock(
                self.rice.id,
                quantity=99,
                movement_type="OUT",
                notes="Overdraw",
            )

    def test_wastage_deducts(self):
        before = Decimal(str(self.rice.quantity_on_hand))
        row = StockService.create_wastage(
            {
                "stockItemId": str(self.rice.id),
                "quantity": 1.5,
                "reason": "Spoiled / Overripe",
                "approvedBy": "Chef",
                "outlet_id": self.outlet.id,
                "property_id": self.prop.id,
                "tenant_id": self.tenant.id,
            }
        )
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity_on_hand, before - Decimal("1.5"))
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.rice, movement_type="WASTAGE", reference_id=row["id"]
            ).exists()
        )

    def test_closing_adjusts_variance(self):
        StockService.save_closing(
            {
                "date": str(date.today()),
                "property_id": self.prop.id,
                "outlet_id": self.outlet.id,
                "tenant_id": self.tenant.id,
                "entries": [{"id": str(self.rice.id), "newStock": 7}],
            }
        )
        self.rice.refresh_from_db()
        self.assertEqual(self.rice.quantity_on_hand, Decimal("7.000"))  # counted qty wins
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.rice, movement_type="ADJUST"
            ).exists()
        )

    def test_deduct_for_order_once_when_enabled(self):
        category = MenuCategory.objects.create(outlet=self.outlet, name=f"Mains {self.suffix}")
        menu = MenuItem.objects.create(
            outlet=self.outlet,
            category=category,
            code=f"MI-{self.suffix[:6]}",
            name="Rice Bowl",
            price=120,
        )
        StockService.save_recipe(
            {
                "name": "Rice Bowl",
                "menuItemId": str(menu.id),
                "yieldQty": 1,
                "ingredients": [{"stockItemId": str(self.rice.id), "quantity": 0.4, "unit": "Kg"}],
            }
        )
        order = POSOrder.objects.create(
            tenant=self.tenant,
            property=self.prop,
            outlet=self.outlet,
            order_number=f"ORD-{self.suffix[:8]}",
            status="SETTLED",
        )
        POSOrderItem.objects.create(
            order=order,
            menu_item=menu,
            item_name="Rice Bowl",
            quantity=2,
            unit_price=120,
            line_total=240,
        )
        first = StockService.deduct_for_order(order)
        second = StockService.deduct_for_order(order)
        self.rice.refresh_from_db()
        self.assertTrue(first["deducted"])
        self.assertFalse(second["deducted"])
        self.assertEqual(self.rice.quantity_on_hand, Decimal("5.200"))

    def test_deduct_skipped_when_auto_off(self):
        StockService.save_inventory_settings(
            {"recipeBasedConsumption": "No"},
            outlet_id=self.outlet.id,
        )
        order = POSOrder.objects.create(
            tenant=self.tenant,
            property=self.prop,
            outlet=self.outlet,
            order_number=f"ORD-OFF-{self.suffix[:8]}",
            status="SETTLED",
        )
        result = StockService.deduct_for_order(order)
        self.assertFalse(result["deducted"])
        self.assertEqual(result["reason"], "recipe_based_consumption_disabled")

    def test_overview_and_alerts_urls(self):
        client = APIClient()
        overview = client.get(
            "/api/pos/stock/overview/",
            {"outlet_id": str(self.outlet.id), "property_id": str(self.prop.id)},
        )
        alerts = client.get(
            "/api/pos/stock/alerts/",
            {"outlet_id": str(self.outlet.id)},
        )
        self.assertEqual(overview.status_code, 200)
        self.assertTrue(overview.data.get("success"))
        self.assertEqual(alerts.status_code, 200)
        self.assertIn("alerts", alerts.data)
