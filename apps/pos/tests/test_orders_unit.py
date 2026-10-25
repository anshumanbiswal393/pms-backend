"""
Part 3 — Orders + KOT unit tests (no DB migrate required).

Run:
  python manage.py test apps.POS.tests.test_orders_unit -v 2 --noinput
"""
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.POS.services.orders import OrderService
from apps.POS.views import (
    POSOrderViewSet,
    KOTListAPIView,
    KOTTicketReadyAPIView,
    KOTTicketServedAPIView,
)


SAMPLE_ORDER = {
    "id": str(uuid4()),
    "orderNumber": "ORD-10001",
    "orderType": "DINE_IN",
    "status": "PLACED",
    "currentStage": "placed",
    "grandTotal": 500.0,
    "items": [],
}


class OrderURLTests(SimpleTestCase):
    def test_order_routes_resolve(self):
        self.assertEqual(reverse("pos-order-list"), "/api/pos/orders/")
        self.assertEqual(reverse("pos-order-current"), "/api/pos/orders/current/")
        self.assertEqual(reverse("pos-order-history"), "/api/pos/orders/history/")
        self.assertEqual(reverse("pos-order-live"), "/api/pos/orders/live/")
        self.assertEqual(reverse("pos-kot-list"), "/api/pos/kot/")
        oid = SAMPLE_ORDER["id"]
        self.assertEqual(reverse("pos-kot-ready", kwargs={"pk": oid}), f"/api/pos/kot/{oid}/ready/")
        self.assertEqual(
            reverse("pos-kot-served", kwargs={"pk": oid}), f"/api/pos/kot/{oid}/served/"
        )
        self.assertEqual(
            reverse("pos-order-settle", kwargs={"pk": oid}),
            f"/api/pos/orders/{oid}/settle/",
        )


class OrderAPIViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch.object(OrderService, "list_current", return_value=[SAMPLE_ORDER])
    def test_current_orders(self, mock_list):
        view = POSOrderViewSet.as_view({"get": "current"})
        request = self.factory.get(
            "/api/pos/orders/current/", {"property_id": str(uuid4())}
        )
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["orderNumber"], "ORD-10001")
        mock_list.assert_called_once()

    @patch.object(
        OrderService,
        "list_history",
        return_value={"success": True, "count": 1, "grandTotal": 500.0, "orders": [SAMPLE_ORDER]},
    )
    def test_history(self, mock_hist):
        view = POSOrderViewSet.as_view({"get": "history"})
        request = self.factory.get("/api/pos/orders/history/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    @patch.object(OrderService, "create_order", return_value={**SAMPLE_ORDER, "kotId": 1})
    def test_create_order(self, mock_create):
        view = POSOrderViewSet.as_view({"post": "create"})
        payload = {
            "outletId": str(uuid4()),
            "orderType": "DINE_IN",
            "items": [
                {"name": "Paneer Tikka", "quantity": 1, "price": 340},
            ],
            "grandTotal": 340,
        }
        request = self.factory.post("/api/pos/orders/", payload, format="json")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["orderNumber"], "ORD-10001")
        mock_create.assert_called_once()

    @patch.object(OrderService, "advance_stage", return_value={**SAMPLE_ORDER, "status": "PREPARED"})
    def test_advance_stage(self, mock_adv):
        oid = SAMPLE_ORDER["id"]
        view = POSOrderViewSet.as_view({"post": "advance_stage"})
        request = self.factory.post(f"/api/pos/orders/{oid}/advance-stage/")
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "PREPARED")

    @patch.object(
        OrderService,
        "list_kot",
        return_value={"success": True, "count": 0, "kots": []},
    )
    def test_kot_list(self, mock_kot):
        view = KOTListAPIView.as_view()
        request = self.factory.get("/api/pos/kot/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    @patch.object(
        OrderService,
        "mark_ticket_ready",
        return_value={"id": SAMPLE_ORDER["id"], "status": "READY", "statusLabel": "Prepared"},
    )
    def test_kot_ready(self, mock_ready):
        oid = SAMPLE_ORDER["id"]
        view = KOTTicketReadyAPIView.as_view()
        request = self.factory.post(f"/api/pos/kot/{oid}/ready/")
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "READY")
        mock_ready.assert_called_once()

    @patch.object(
        OrderService,
        "mark_ticket_served",
        return_value={"id": SAMPLE_ORDER["id"], "status": "SERVED", "statusLabel": "Served"},
    )
    def test_kot_served(self, mock_served):
        oid = SAMPLE_ORDER["id"]
        view = KOTTicketServedAPIView.as_view()
        request = self.factory.post(f"/api/pos/kot/{oid}/served/")
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "SERVED")
        mock_served.assert_called_once()

    @patch.object(
        OrderService,
        "update_order_items",
        return_value={**SAMPLE_ORDER, "kotId": 2},
    )
    def test_patch_extra_items(self, mock_patch):
        oid = SAMPLE_ORDER["id"]
        view = POSOrderViewSet.as_view({"patch": "partial_update"})
        request = self.factory.patch(
            f"/api/pos/orders/{oid}/",
            {"items": [{"name": "Naan", "quantity": 1, "price": 40}]},
            format="json",
        )
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_patch.assert_called_once()

    @patch.object(
        OrderService,
        "settle_order",
        return_value={**SAMPLE_ORDER, "status": "SETTLED"},
    )
    def test_settle_order(self, mock_settle):
        oid = SAMPLE_ORDER["id"]
        view = POSOrderViewSet.as_view({"post": "settle"})
        request = self.factory.post(
            f"/api/pos/orders/{oid}/settle/",
            {"paymentMode": "CASH", "tenderedAmount": 500},
            format="json",
        )
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "SETTLED")
        mock_settle.assert_called_once()


class OrderServiceNormalizeTests(SimpleTestCase):
    def test_normalize_order_type(self):
        self.assertEqual(OrderService._normalize_order_type("dine_in"), "DINE_IN")
        self.assertEqual(OrderService._normalize_order_type("Room Service"), "ROOM_SERVICE")

    def test_normalize_payment_mode(self):
        self.assertEqual(OrderService._normalize_payment_mode("Cash"), "CASH")
        self.assertEqual(OrderService._normalize_payment_mode("Room Charge"), "ROOM_CHARGE")
