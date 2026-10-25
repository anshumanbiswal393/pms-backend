"""
Part 5 — Due bills / day-end / export unit tests (no DB).

Run:
  python manage.py test apps.POS.tests.test_dues_unit -v 2 --noinput
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.POS.services.dues import DueLedgerService, _aging_bucket
from apps.POS.views import POSOrderViewSet, DayEndSummaryAPIView


class AgingBucketTests(SimpleTestCase):
    def test_buckets(self):
        self.assertEqual(_aging_bucket(0), "0-15")
        self.assertEqual(_aging_bucket(15), "0-15")
        self.assertEqual(_aging_bucket(16), "16-30")
        self.assertEqual(_aging_bucket(31), "30+")


class DueAPIViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_urls_resolve(self):
        self.assertEqual(
            reverse("pos-order-due-settlement"),
            "/api/pos/orders/due-settlement/",
        )
        self.assertEqual(reverse("pos-day-end"), "/api/pos/reports/day-end/")
        self.assertEqual(
            reverse("pos-day-end-close"), "/api/pos/reports/day-end/close/"
        )

    @patch.object(
        DueLedgerService,
        "list_dues",
        return_value=[
            {
                "id": str(uuid4()),
                "billNo": "BILL-8901",
                "dueAmount": 500.0,
                "status": "Pending",
            }
        ],
    )
    def test_due_list(self, mock_list):
        view = POSOrderViewSet.as_view({"get": "due_settlement"})
        request = self.factory.get("/api/pos/orders/due-settlement/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["totalDue"], 500.0)

    @patch.object(
        DueLedgerService,
        "settle_due",
        return_value={"billNo": "BILL-8901", "status": "Settled", "dueAmount": 0.0},
    )
    def test_settle_due(self, mock_settle):
        bill_id = str(uuid4())
        view = POSOrderViewSet.as_view({"post": "settle_due_bill"})
        request = self.factory.post(
            f"/api/pos/orders/due-settlement/{bill_id}/settle/",
            {"paymentMode": "UPI", "paidAmount": 500},
            format="json",
        )
        response = view(request, bill_id=bill_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "Settled")

    @patch(
        "apps.POS.views.DayCloseService.summarize_range",
        return_value={
            "success": True,
            "count": 1,
            "records": [{"date": "16 Oct 2026", "orderCount": 2, "totalAmount": 900}],
        },
    )
    def test_day_end_summary(self, mock_sum):
        view = DayEndSummaryAPIView.as_view()
        request = self.factory.get("/api/pos/reports/day-end/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
