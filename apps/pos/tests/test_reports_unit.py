"""
POS reports unit tests (no DB migrate required).

Run:
  python manage.py test apps.POS.tests.test_reports_unit -v 2 --noinput
"""
from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.POS.services.reports import KIND_ALIASES, parse_iso_date
from apps.POS.views import SalesReportAPIView, DayEndCloseAPIView


class ReportKindTests(SimpleTestCase):
    def test_catalog_ids_map_to_kinds(self):
        self.assertEqual(KIND_ALIASES["REP-01"], "overview")
        self.assertEqual(KIND_ALIASES["REP-02"], "items")
        self.assertEqual(KIND_ALIASES["REP-10"], "hourly")
        self.assertEqual(KIND_ALIASES["REP-12"], "gst")

    def test_parse_iso_date(self):
        self.assertEqual(parse_iso_date("2026-10-24"), date(2026, 10, 24))
        self.assertIsNone(parse_iso_date(None))
        self.assertIsNone(parse_iso_date(""))


class SalesReportAPIViewUnitTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_sales_url_resolves(self):
        self.assertEqual(reverse("pos-report-sales"), "/api/pos/reports/sales/")
        self.assertEqual(reverse("pos-report-consumption"), "/api/pos/reports/consumption/")
        self.assertEqual(reverse("pos-day-end"), "/api/pos/reports/day-end/")

    @patch("apps.POS.views.SalesAnalyticsService.run")
    def test_kind_and_dates_forwarded(self, mock_run):
        mock_run.return_value = {
            "success": True,
            "kind": "overview",
            "count": 1,
            "records": [{"id": "1", "netSales": 500}],
        }
        view = SalesReportAPIView.as_view()
        request = self.factory.get(
            "/api/pos/reports/sales/",
            {
                "kind": "REP-01",
                "startDate": "2026-10-01",
                "endDate": "2026-10-24",
            },
        )
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kind"], "overview")
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["kind"], "REP-01")
        self.assertEqual(kwargs["start_date"], date(2026, 10, 1))
        self.assertEqual(kwargs["end_date"], date(2026, 10, 24))

    @patch("apps.POS.views.SalesAnalyticsService.run")
    def test_default_kind_is_items(self, mock_run):
        mock_run.return_value = {"success": True, "kind": "items", "items": [], "records": []}
        view = SalesReportAPIView.as_view()
        request = self.factory.get("/api/pos/reports/sales/")
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_run.call_args.kwargs["kind"], "items")


class DayEndCloseScopeTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_close_requires_date(self):
        view = DayEndCloseAPIView.as_view()
        request = self.factory.post(
            "/api/pos/reports/day-end/close/", {}, format="json"
        )
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
