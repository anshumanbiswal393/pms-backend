from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.POS.models import POSStockMovement
from apps.POS.services.purchases import PurchaseService
from .helpers import make_sku, make_tenant_property_outlet, unique_suffix


class PurchaseStockTests(TestCase):
    def setUp(self):
        self.suffix = unique_suffix()
        self.tenant, self.prop, self.outlet = make_tenant_property_outlet(self.suffix)
        self.oil = make_sku(
            tenant=self.tenant,
            prop=self.prop,
            outlet=self.outlet,
            code=f"OIL-{self.suffix[:6]}",
            name="Sunflower Oil",
            qty=5,
            unit_cost=140,
        )
        self.scope = {
            "tenant_id": self.tenant.id,
            "property_id": self.prop.id,
            "outlet_id": self.outlet.id,
        }

    def test_create_purchase_requires_items(self):
        with self.assertRaises(ValidationError):
            PurchaseService.create_purchase(
                {**self.scope, "vendorName": "Metro", "totalAmount": 100}
            )

    def test_purchase_in_adds_stock(self):
        invoice = PurchaseService.create_purchase(
            {
                **self.scope,
                "vendorName": "Metro Cash & Carry",
                "invoiceNo": f"INV-{self.suffix[:8]}",
                "totalAmount": 280,
                "items": [
                    {
                        "stockItemId": str(self.oil.id),
                        "name": "Sunflower Oil",
                        "quantity": 2,
                        "unit": "Kg",
                        "unitPrice": 140,
                    }
                ],
            }
        )
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity_on_hand, Decimal("7.000"))
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.oil,
                movement_type="IN",
                reference_type="PURCHASE_INVOICE",
                reference_id=invoice["id"],
            ).exists()
        )

    def test_cancel_purchase_reverses_stock(self):
        invoice = PurchaseService.create_purchase(
            {
                **self.scope,
                "vendorName": "Metro",
                "invoiceNo": f"INV-CXL-{self.suffix[:8]}",
                "totalAmount": 140,
                "items": [{"stockItemId": str(self.oil.id), "quantity": 1, "unitPrice": 140}],
            }
        )
        PurchaseService.delete_purchase(invoice["id"])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity_on_hand, Decimal("5.000"))

    def test_purchase_return_out(self):
        row = PurchaseService.create_purchase_return(
            {
                **self.scope,
                "vendorName": "Metro",
                "debitNoteNo": f"DN-{self.suffix[:8]}",
                "items": [{"stockItemId": str(self.oil.id), "quantity": 1, "unitPrice": 140}],
            }
        )
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity_on_hand, Decimal("4.000"))
        self.assertTrue(
            POSStockMovement.objects.filter(
                stock_item=self.oil,
                movement_type="PURCHASE_RETURN",
                reference_id=row["id"],
            ).exists()
        )

    def test_po_receive_adds_stock(self):
        po = PurchaseService.create_purchase_order(
            {
                **self.scope,
                "vendorName": "Metro",
                "poNumber": f"PO-{self.suffix[:8]}",
                "items": [{"stockItemId": str(self.oil.id), "quantity": 3, "unitPrice": 140}],
            }
        )
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity_on_hand, Decimal("5.000"))
        PurchaseService.receive_purchase_order(po["id"])
        self.oil.refresh_from_db()
        self.assertEqual(self.oil.quantity_on_hand, Decimal("8.000"))
