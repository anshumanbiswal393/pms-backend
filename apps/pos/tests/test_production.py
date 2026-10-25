from decimal import Decimal

from django.test import TestCase

from apps.POS.models import POSStockMovement
from apps.POS.services.production import ProductionService
from .helpers import make_sku, make_tenant_property_outlet, unique_suffix


class ProductionStockTests(TestCase):
    def setUp(self):
        self.suffix = unique_suffix()
        self.tenant, self.prop, self.outlet = make_tenant_property_outlet(self.suffix)
        self.tomato = make_sku(
            tenant=self.tenant,
            prop=self.prop,
            outlet=self.outlet,
            code=f"TOM-{self.suffix[:6]}",
            name="Tomato",
            qty=20,
            unit_cost=40,
        )
        self.gravy = make_sku(
            tenant=self.tenant,
            prop=self.prop,
            outlet=self.outlet,
            code=f"GRV-{self.suffix[:6]}",
            name="Tomato Gravy",
            qty=0,
            kind="PREPARED",
            unit_cost=80,
        )

    def test_list_recipes_does_not_seed_for_real_outlet(self):
        recipes = ProductionService.list_recipes(
            property_id=self.prop.id,
            outlet_id=self.outlet.id,
        )
        self.assertEqual(recipes, [])

    def test_completed_batch_outs_ingredients_and_ins_output(self):
        recipe = ProductionService.save_recipe(
            {
                "name": "Tomato Gravy",
                "code": f"PRD-{self.suffix[:6]}",
                "tenant_id": self.tenant.id,
                "property_id": self.prop.id,
                "outlet_id": self.outlet.id,
                "outputStockItemId": str(self.gravy.id),
                "expectedYield": 5,
                "ingredients": [
                    {
                        "stockItemId": str(self.tomato.id),
                        "quantity": 4,
                        "unit": "Kg",
                        "unitCost": 40,
                    }
                ],
            }
        )
        batch = ProductionService.create_batch(
            {
                "recipeId": recipe["id"],
                "yieldQty": 5,
                "status": "COMPLETED",
                "tenant_id": self.tenant.id,
                "property_id": self.prop.id,
                "outlet_id": self.outlet.id,
            }
        )
        self.tomato.refresh_from_db()
        self.gravy.refresh_from_db()
        self.assertEqual(self.tomato.quantity_on_hand, Decimal("16.000"))
        self.assertEqual(self.gravy.quantity_on_hand, Decimal("5.000"))
        self.assertTrue(batch["isStockDeducted"])
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.tomato,
                movement_type="OUT",
                reference_type="PRODUCTION_BATCH",
            ).exists()
        )
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.gravy,
                movement_type="IN",
                reference_type="PRODUCTION_BATCH",
            ).exists()
        )
        ProductionService.create_batch(
            {
                "recipeId": recipe["id"],
                "yieldQty": 1,
                "status": "IN_PROGRESS",
                "tenant_id": self.tenant.id,
                "property_id": self.prop.id,
                "outlet_id": self.outlet.id,
            }
        )
        self.tomato.refresh_from_db()
        self.assertEqual(self.tomato.quantity_on_hand, Decimal("16.000"))
