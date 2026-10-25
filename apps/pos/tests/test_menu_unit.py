"""
Part 2 — Menu unit tests (no DB migrate required).

Run:
  python manage.py test apps.POS.tests.test_menu_unit -v 2 --noinput
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.POS.services.menu import MenuCatalogService
from apps.POS.views import BillingMenuCatalogAPIView, MenuItemViewSet


class MenuCatalogServiceUnitTests(SimpleTestCase):
    def test_serialize_item_ui_shape(self):
        outlet_id = uuid4()
        category_id = uuid4()
        item_id = uuid4()
        tax_id = uuid4()

        variant = SimpleNamespace(id=uuid4(), name="Half", price=Decimal("220.00"))
        tax = SimpleNamespace(rate=Decimal("5.00"))
        category = SimpleNamespace(id=category_id, name="Starters")
        outlet = SimpleNamespace(
            id=outlet_id,
            default_cgst_rate=Decimal("2.50"),
            default_sgst_rate=Decimal("2.50"),
        )
        item = SimpleNamespace(
            id=item_id,
            outlet_id=outlet_id,
            outlet=outlet,
            category_id=category_id,
            category=category,
            tax_profile_id=tax_id,
            tax_profile=tax,
            code="#101",
            name="Paneer Tikka",
            online_display_name="Paneer Tikka Angara",
            item_type="VEG",
            price=Decimal("340.00"),
            description="desc",
            status="ACTIVE",
            images=[{"id": "img-1", "url": "https://x", "isPrimary": True}],
            base_menu=True,
            zomato=True,
            swiggy=False,
            direct=True,
            next_available_at=None,
            updated_at=None,
            meta={"commission": {"type": "PERCENT", "value": 10}},
            variants=MagicMock(),
            modifier_groups=MagicMock(),
        )
        item.tax_rate = Decimal("5.00")
        item.variants.all.return_value = [variant]
        item.modifier_groups.filter.return_value = []

        dto = MenuCatalogService.serialize_item_ui(item)
        self.assertEqual(dto["id"], str(item_id))
        self.assertEqual(dto["outletId"], str(outlet_id))
        self.assertEqual(dto["category"], "Starters")
        self.assertEqual(dto["itemType"], "Veg")
        self.assertEqual(dto["status"], "Active")
        self.assertEqual(dto["taxRate"], 5.0)
        self.assertEqual(dto["price"], 340.0)
        self.assertEqual(dto["variants"][0]["name"], "Half")
        self.assertFalse(dto["swiggy"])
        self.assertEqual(dto["commissionType"], "Percentage")
        self.assertEqual(dto["commissionValue"], 10.0)


class MenuAPIViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_billing_menu_url(self):
        self.assertEqual(reverse("pos-billing-menu"), "/api/pos/billing/menu/")

    def test_menu_items_url(self):
        self.assertEqual(reverse("pos-menu-item-list"), "/api/pos/menu/items/")

    def test_billing_requires_outlet(self):
        view = BillingMenuCatalogAPIView.as_view()
        request = self.factory.get("/api/pos/billing/menu/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(
        MenuCatalogService,
        "list_items_ui",
        return_value=[
            {
                "id": "1",
                "outletId": "o1",
                "code": "#101",
                "name": "Paneer",
                "onlineDisplayName": "Paneer",
                "category": "Starters",
                "itemType": "Veg",
                "price": 340.0,
                "taxRate": 5.0,
                "status": "Active",
                "description": "",
                "images": [],
                "variants": [],
                "modifierGroups": [],
                "baseMenu": True,
                "zomato": True,
                "swiggy": True,
                "direct": True,
                "updatedAt": "",
            }
        ],
    )
    def test_list_items_delegates_to_service(self, mock_list):
        view = MenuItemViewSet.as_view({"get": "list"})
        request = self.factory.get("/api/pos/menu/items/", {"outletId": "o1"})
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["code"], "#101")
        mock_list.assert_called_once()
        self.assertEqual(mock_list.call_args.kwargs["outlet_id"], "o1")
