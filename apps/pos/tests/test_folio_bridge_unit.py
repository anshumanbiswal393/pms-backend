"""
Part 4 — Folio bridge / settle unit tests (no DB migrate required).

Run:
  python manage.py test apps.POS.tests.test_folio_bridge_unit -v 2 --noinput
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apps.POS.services.folio_bridge import FolioBridgeService
from apps.POS.services.orders import OrderService
from apps.POS.views import POSOrderViewSet


class FolioBridgeUnitTests(SimpleTestCase):
    def test_charge_code_room_service(self):
        order = SimpleNamespace(order_type="ROOM_SERVICE")
        self.assertEqual(
            FolioBridgeService._charge_code_for_order(order),
            "POS_ROOM_SERVICE",
        )

    def test_charge_code_fnb(self):
        order = SimpleNamespace(order_type="DINE_IN")
        self.assertEqual(
            FolioBridgeService._charge_code_for_order(order),
            "POS_FNB",
        )

    def test_requires_idempotency_key(self):
        order = SimpleNamespace(
            id=uuid4(),
            order_type="ROOM_SERVICE",
            grand_total=Decimal("100.00"),
            tenant_id=uuid4(),
            reservation_id=None,
            folio_id=None,
            outlet_id=None,
        )
        with self.assertRaises(ValidationError):
            FolioBridgeService.post_room_charge(order, idempotency_key="")


class SettleAPIViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_settle_url_resolves(self):
        oid = uuid4()
        self.assertEqual(
            reverse("pos-order-settle", args=[oid]),
            f"/api/pos/orders/{oid}/settle/",
        )

    @patch.object(
        OrderService,
        "settle_order",
        return_value={
            "orderNumber": "ORD-10001",
            "status": "SETTLED",
            "payment_mode": "CASH",
            "grandTotal": 500.0,
        },
    )
    def test_settle_cash(self, mock_settle):
        oid = str(uuid4())
        view = POSOrderViewSet.as_view({"post": "settle"})
        request = self.factory.post(
            f"/api/pos/orders/{oid}/settle/",
            {"payment_mode": "CASH"},
            format="json",
        )
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "SETTLED")
        mock_settle.assert_called_once()

    @patch.object(
        OrderService,
        "settle_order",
        return_value={
            "orderNumber": "ORD-10002",
            "status": "SETTLED",
            "payment_mode": "ROOM_CHARGE",
            "folio_transaction_id": str(uuid4()),
            "folio_balance_after": "1500.00",
        },
    )
    def test_settle_room_charge(self, mock_settle):
        oid = str(uuid4())
        view = POSOrderViewSet.as_view({"post": "settle"})
        request = self.factory.post(
            f"/api/pos/orders/{oid}/settle/",
            {
                "paymentMode": "ROOM_CHARGE",
                "reservationId": str(uuid4()),
                "folioId": str(uuid4()),
                "idempotencyKey": "pos-ord-settle-1",
            },
            format="json",
        )
        response = view(request, pk=oid)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payment_mode"], "ROOM_CHARGE")
        self.assertIn("folio_transaction_id", response.data)
