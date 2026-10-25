"""
Part 1 — OccupancyService ORM integration tests.

Requires a working migrate against Postgres (or fixed SQLite).

Run (when DB is healthy):
  python manage.py test apps.POS.tests.test_occupied_rooms_integration -v 2 --keepdb --noinput
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.reference.models import Country, ReservationSource
from apps.core.tenants.models import Tenant, Property
from apps.features.crm.models import GuestProfile, GuestContact
from apps.features.front_office.models import GuestFolio
from apps.features.inventory.models import (
    InventoryUnitCategory,
    InventoryUnitType,
    InventoryUnit,
)
from apps.features.rates.models import CancellationPolicy, ChildPolicy
from apps.features.reservations.models import Reservation, ReservationInventory
from apps.POS.services.occupancy import OccupancyService


class OccupancyServiceIntegrationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Retrod Hotels", subdomain="retrod-pos-p1-int")
        try:
            self.property = Property.objects.create(
                tenant=self.tenant,
                name="Highway Inn",
                hotel_id="HI001",
                address_line_1="MG Road",
                city="Pune",
                state="MH",
                country="India",
                postal_code="411001",
                contact_email="hi@example.com",
                contact_phone="0200000000",
                currency="INR",
                timezone="Asia/Kolkata",
            )
        except Exception:
            self.property = Property.objects.create(tenant=self.tenant, name="Highway Inn")

        self.source = ReservationSource.objects.create(code="DIRECT", name="Direct")
        Country.objects.create(code="IN", name="India")
        CancellationPolicy.objects.create(tenant=self.tenant, code="STD", name="Standard")
        ChildPolicy.objects.create(tenant=self.tenant, code="CHILD", name="Child Policy")

        category = InventoryUnitCategory.objects.create(
            tenant=self.tenant, code="ROOM", name="Room"
        )
        unit_type = InventoryUnitType.objects.create(
            tenant=self.tenant,
            property=self.property,
            category=category,
            code="DLX",
            name="Deluxe",
        )
        self.unit_204 = InventoryUnit.objects.create(
            tenant=self.tenant,
            property=self.property,
            inventory_unit_type=unit_type,
            name="204",
            floor="2",
        )
        unit_305 = InventoryUnit.objects.create(
            tenant=self.tenant,
            property=self.property,
            inventory_unit_type=unit_type,
            name="305",
            floor="3",
        )

        guest = GuestProfile.objects.create(
            tenant=self.tenant, first_name="Aman", last_name="Singhal"
        )
        GuestContact.objects.create(
            tenant=self.tenant,
            guest=guest,
            email="aman@example.com",
            phone="9876543210",
            is_primary=True,
        )

        today = timezone.now().date()
        in_house = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            primary_guest=guest,
            reservation_source=self.source,
            booking_date=today,
            arrival_date=today,
            departure_date=today + timedelta(days=2),
            confirmation_number="CONF-INHOUSE-INT-1",
            reservation_type="Transient",
            market_segment="LEISURE",
            status="CHECKED_IN",
        )
        ReservationInventory.objects.create(
            tenant=self.tenant,
            reservation=in_house,
            inventory_unit=self.unit_204,
            inventory_unit_type=unit_type,
            check_in_date=in_house.arrival_date,
            check_out_date=in_house.departure_date,
            adult_count=2,
            child_count=0,
            status="CHECKED_IN",
        )
        GuestFolio.objects.create(
            tenant=self.tenant,
            reservation=in_house,
            folio_number="FOLIO-POS-INT-1001",
            status="OPEN",
            total_charges=Decimal("1200.00"),
            total_payments=Decimal("200.00"),
        )

        pending_guest = GuestProfile.objects.create(
            tenant=self.tenant, first_name="Pending", last_name="Guest"
        )
        confirmed = Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            primary_guest=pending_guest,
            reservation_source=self.source,
            booking_date=today,
            arrival_date=today,
            departure_date=today + timedelta(days=1),
            confirmation_number="CONF-PENDING-INT-1",
            reservation_type="Transient",
            market_segment="LEISURE",
            status="CONFIRMED",
        )
        ReservationInventory.objects.create(
            tenant=self.tenant,
            reservation=confirmed,
            inventory_unit=unit_305,
            inventory_unit_type=unit_type,
            check_in_date=confirmed.arrival_date,
            check_out_date=confirmed.departure_date,
            adult_count=1,
            status="ASSIGNED",
        )

    def test_lists_checked_in_room_with_open_folio(self):
        rooms = OccupancyService.list_occupied_rooms(property_id=self.property.id)
        self.assertEqual(len(rooms), 1)
        room = rooms[0]
        self.assertEqual(room["room_number"], "204")
        self.assertEqual(room["guest_name"], "Aman Singhal")
        self.assertEqual(room["guest_phone"], "9876543210")
        self.assertEqual(room["pax"], 2)
        self.assertEqual(room["folio_number"], "FOLIO-POS-INT-1001")
        self.assertEqual(room["balance"], "1000.00")
        self.assertTrue(room["is_open_for_charges"])

    def test_excludes_confirmed_not_checked_in(self):
        rooms = OccupancyService.list_occupied_rooms(property_id=self.property.id)
        self.assertNotIn("305", {r["room_number"] for r in rooms})
