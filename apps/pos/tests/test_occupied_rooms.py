"""
Part 1 — Occupied rooms bridge (unit / API tests, no DB required).

Run (PostgreSQL via PMS .env DATABASE_URL):
  python manage.py test apps.POS.tests.test_occupied_rooms -v 2 --noinput
"""
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.POS.serializers import OccupiedRoomsResponseSerializer
from apps.POS.services.occupancy import OccupancyService
from apps.POS.views import OccupiedRoomsAPIView


SAMPLE_ROOM = {
    "room_number": "204",
    "unit_id": "11111111-1111-1111-1111-111111111111",
    "unit_type": "Deluxe",
    "floor": "2",
    "reservation_id": "22222222-2222-2222-2222-222222222222",
    "confirmation_number": "CONF-INHOUSE-1",
    "allocation_id": "33333333-3333-3333-3333-333333333333",
    "guest_name": "Aman Singhal",
    "guest_phone": "9876543210",
    "guest_id": "44444444-4444-4444-4444-444444444444",
    "pax": 2,
    "adult_count": 2,
    "child_count": 0,
    "arrival_date": "2026-10-16",
    "departure_date": "2026-10-18",
    "folio_id": "55555555-5555-5555-5555-555555555555",
    "folio_number": "FOLIO-POS-1001",
    "folio_status": "OPEN",
    "balance": "1000.00",
    "is_open_for_charges": True,
    "property_id": "66666666-6666-6666-6666-666666666666",
    "tenant_id": "77777777-7777-7777-7777-777777777777",
}


class OccupiedRoomsSerializerTests(SimpleTestCase):
    def test_response_serializer_validates_payload(self):
        payload = {"count": 1, "rooms": [SAMPLE_ROOM]}
        serializer = OccupiedRoomsResponseSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["count"], 1)
        self.assertEqual(serializer.validated_data["rooms"][0]["room_number"], "204")
        self.assertTrue(serializer.validated_data["rooms"][0]["is_open_for_charges"])


class OccupiedRoomsAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = OccupiedRoomsAPIView.as_view()

    def test_url_resolves(self):
        self.assertEqual(
            reverse("pos-occupied-rooms"),
            "/api/pos/integrations/occupied-rooms/",
        )

    def test_requires_property_or_tenant(self):
        request = self.factory.get("/api/pos/integrations/occupied-rooms/")
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("property_id", response.data["detail"])

    @patch.object(OccupancyService, "list_occupied_rooms", return_value=[SAMPLE_ROOM])
    def test_returns_rooms_for_property_query(self, mock_list):
        request = self.factory.get(
            "/api/pos/integrations/occupied-rooms/",
            {"property_id": SAMPLE_ROOM["property_id"]},
        )
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["rooms"][0]["room_number"], "204")
        self.assertEqual(response.data["rooms"][0]["guest_name"], "Aman Singhal")
        mock_list.assert_called_once_with(
            property_id=SAMPLE_ROOM["property_id"],
            tenant_id=None,
        )

    @patch.object(OccupancyService, "list_occupied_rooms", return_value=[SAMPLE_ROOM])
    def test_accepts_property_header(self, mock_list):
        request = self.factory.get(
            "/api/pos/integrations/occupied-rooms/",
            HTTP_X_PROPERTY_ID=SAMPLE_ROOM["property_id"],
        )
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        mock_list.assert_called_once_with(
            property_id=SAMPLE_ROOM["property_id"],
            tenant_id=None,
        )

    @patch.object(OccupancyService, "list_occupied_rooms", return_value=[SAMPLE_ROOM])
    def test_accepts_tenant_header(self, mock_list):
        request = self.factory.get(
            "/api/pos/integrations/occupied-rooms/",
            HTTP_X_TENANT_ID=SAMPLE_ROOM["tenant_id"],
        )
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_list.assert_called_once_with(
            property_id=None,
            tenant_id=SAMPLE_ROOM["tenant_id"],
        )

    @patch.object(OccupancyService, "list_occupied_rooms", return_value=[])
    def test_empty_list(self, mock_list):
        request = self.factory.get(
            "/api/pos/integrations/occupied-rooms/",
            {"property_id": SAMPLE_ROOM["property_id"]},
        )
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["rooms"], [])


class OccupancyServiceGuardTests(SimpleTestCase):
    def test_returns_empty_without_scope(self):
        self.assertEqual(OccupancyService.list_occupied_rooms(), [])
