"""
Part 2 — Menu catalog APIs (PostgreSQL / same PMS DATABASE_URL).

Run:
  python manage.py test apps.POS.tests.test_menu -v 2 --keepdb --noinput
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.tenants.models import Tenant, Property
from apps.POS.models import Outlet, TaxProfile, MenuCategory, MenuItem, MenuVariant
from apps.POS.services.menu import MenuCatalogService


class MenuCatalogPostgresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(
            name="POS Menu Test Tenant",
            subdomain="pos-menu-p2-test",
        )
        try:
            cls.property = Property.objects.create(
                tenant=cls.tenant,
                name="POS Menu Test Property",
                hotel_id="PMP001",
                address_line_1="Test Road",
                city="Pune",
                state="MH",
                country="India",
                postal_code="411001",
                contact_email="pos-menu@example.com",
                contact_phone="0201111111",
                currency="INR",
                timezone="Asia/Kolkata",
            )
        except Exception:
            cls.property = Property.objects.create(
                tenant=cls.tenant,
                name="POS Menu Test Property",
            )

        cls.outlet = Outlet.objects.create(
            tenant=cls.tenant,
            property=cls.property,
            code="MAIN-P2",
            name="Main Restaurant P2",
            outlet_type="PRIMARY",
            is_active=True,
        )
        cls.tax5 = MenuCatalogService.resolve_or_create_tax_profile(
            tenant_id=cls.tenant.id,
            property_id=cls.property.id,
            rate=Decimal("5"),
        )
        cls.category = MenuCategory.objects.create(
            outlet=cls.outlet,
            code="STARTERS",
            name="Starters",
            online_display_name="Starters",
            sort_order=1,
            is_active=True,
        )
        cls.item = MenuItem.objects.create(
            outlet=cls.outlet,
            category=cls.category,
            tax_profile=cls.tax5,
            code="#101",
            name="Paneer Tikka Angara",
            online_display_name="Paneer Tikka Angara Charcoal Smoked",
            item_type="VEG",
            price=Decimal("340.00"),
            description="Test item",
            status="ACTIVE",
            base_menu=True,
            zomato=True,
            swiggy=True,
            direct=True,
            images=[
                {
                    "id": "img-1",
                    "url": "https://example.com/paneer.jpg",
                    "name": "paneer.jpg",
                    "isPrimary": True,
                }
            ],
        )
        MenuVariant.objects.create(
            menu_item=cls.item,
            name="Half",
            price=Decimal("220.00"),
            sort_order=0,
        )
        MenuVariant.objects.create(
            menu_item=cls.item,
            name="Full",
            price=Decimal("340.00"),
            sort_order=1,
        )
        MenuItem.objects.create(
            outlet=cls.outlet,
            category=cls.category,
            tax_profile=cls.tax5,
            code="#999",
            name="Hidden Inactive Dish",
            item_type="VEG",
            price=Decimal("100.00"),
            status="INACTIVE",
        )

    def setUp(self):
        self.client = APIClient()

    def test_list_menu_items_ui_shape(self):
        url = reverse("pos-menu-item-list")
        response = self.client.get(url, {"outletId": str(self.outlet.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
        paneer = next(i for i in response.data if i["code"] == "#101")
        self.assertEqual(paneer["outletId"], str(self.outlet.id))
        self.assertEqual(paneer["category"], "Starters")
        self.assertEqual(paneer["itemType"], "Veg")
        self.assertEqual(paneer["status"], "Active")
        self.assertEqual(paneer["taxRate"], 5.0)
        self.assertEqual(paneer["price"], 340.0)
        self.assertEqual(len(paneer["variants"]), 2)
        self.assertTrue(paneer["baseMenu"])

    def test_active_only_filter(self):
        url = reverse("pos-menu-item-list")
        response = self.client.get(
            url,
            {"outlet_id": str(self.outlet.id), "active_only": "true"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        codes = {i["code"] for i in response.data}
        self.assertIn("#101", codes)
        self.assertNotIn("#999", codes)

    def test_list_categories(self):
        url = reverse("pos-menu-category-list")
        response = self.client.get(url, {"outlet_id": str(self.outlet.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Starters")

    def test_billing_catalog_requires_outlet(self):
        url = reverse("pos-billing-menu")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_billing_catalog_active_only(self):
        url = reverse("pos-billing-menu")
        response = self.client.get(url, {"outletId": str(self.outlet.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["items"][0]["code"], "#101")
        self.assertEqual(response.data["categories"][0]["name"], "Starters")

    def test_create_menu_item_camel_case_aliases(self):
        url = reverse("pos-menu-item-list")
        payload = {
            "outletId": str(self.outlet.id),
            "categoryId": str(self.category.id),
            "code": "#201",
            "name": "Butter Naan",
            "itemType": "Veg",
            "price": 90,
            "taxRate": 5,
            "status": "Active",
            "baseMenu": True,
            "zomato": True,
            "swiggy": False,
            "direct": True,
            "commissionType": "Percentage",
            "commissionValue": 10,
            "variants": [{"name": "Plain", "price": 80}],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["itemType"], "Veg")
        self.assertEqual(response.data["status"], "Active")
        self.assertEqual(response.data["commissionType"], "Percentage")
        self.assertEqual(response.data["commissionValue"], 10.0)
        self.assertTrue(
            MenuItem.objects.filter(outlet=self.outlet, code="#201").exists()
        )

    def test_create_menu_item(self):
        url = reverse("pos-menu-item-list")
        payload = {
            "outlet": str(self.outlet.id),
            "category": str(self.category.id),
            "tax_profile": str(self.tax5.id),
            "code": "#200",
            "name": "Garlic Naan",
            "online_display_name": "Garlic Butter Naan",
            "item_type": "VEG",
            "price": "95.00",
            "status": "ACTIVE",
            "variants": [{"name": "Plain", "price": "80.00"}],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "#200")
        self.assertEqual(response.data["itemType"], "Veg")
        self.assertEqual(len(response.data["variants"]), 1)
        self.assertTrue(
            MenuItem.objects.filter(outlet=self.outlet, code="#200").exists()
        )

    def test_toggle_status(self):
        url = reverse("pos-menu-item-toggle-status", args=[self.item.id])
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "Inactive")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "INACTIVE")

    def test_toggle_platform(self):
        url = reverse(
            "pos-menu-item-toggle-platform",
            kwargs={"pk": self.item.id, "platform": "zomato"},
        )
        response = self.client.patch(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["zomato"])

    def test_tax_profile_list(self):
        url = reverse("pos-tax-profile-list")
        response = self.client.get(url, {"tenant_id": str(self.tenant.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertEqual(Decimal(str(response.data[0]["rate"])), Decimal("5.00"))

    def test_uses_postgresql(self):
        from django.conf import settings

        self.assertIn(
            "postgresql",
            settings.DATABASES["default"]["ENGINE"],
            "Part 2 must run against the PMS PostgreSQL database",
        )
