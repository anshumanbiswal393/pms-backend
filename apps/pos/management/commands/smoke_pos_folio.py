"""
Atomic rollback smoke for Part 4 Room Charge → GuestFolio on PMS PostgreSQL.

  python manage.py smoke_pos_folio
"""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.tenants.models import Tenant, Property
from apps.core.reference.models import ReservationSource
from apps.features.crm.models import GuestProfile
from apps.features.front_office.models import GuestFolio, FolioTransaction
from apps.features.reservations.models import Reservation
from apps.POS.models import Outlet, MenuCategory, MenuItem, FolioPostingLog
from apps.POS.services.menu import MenuCatalogService
from apps.POS.services.orders import OrderService


class Command(BaseCommand):
    help = "Atomic rollback smoke: settle ROOM_CHARGE posts once to GuestFolio."

    def handle(self, *args, **options):
        from django.conf import settings

        if "postgresql" not in settings.DATABASES["default"]["ENGINE"]:
            raise CommandError("Expected PostgreSQL DATABASE_URL.")

        with transaction.atomic():
            tenant = Tenant.objects.first()
            prop = Property.objects.filter(tenant=tenant).first() if tenant else None
            if not tenant or not prop:
                raise CommandError("Need Tenant + Property in PMS DB.")

            outlet = Outlet.objects.filter(
                property=prop, deleted_at__isnull=True, is_active=True
            ).first()
            if not outlet:
                outlet = Outlet.objects.create(
                    tenant=tenant,
                    property=prop,
                    code="SMOKE-FOLIO",
                    name="Smoke Folio Outlet",
                    outlet_type="ROOM_SERVICE",
                    is_active=True,
                )

            cat = MenuCategory.objects.filter(outlet=outlet).first()
            if not cat:
                cat = MenuCategory.objects.create(
                    outlet=outlet, name="Starters", code="STARTERS", is_active=True
                )
            tax = MenuCatalogService.resolve_or_create_tax_profile(
                tenant_id=tenant.id, property_id=prop.id, rate=Decimal("5")
            )
            item = MenuItem.objects.filter(outlet=outlet, status="ACTIVE").first()
            if not item:
                item = MenuItem.objects.create(
                    outlet=outlet,
                    category=cat,
                    tax_profile=tax,
                    code="#SMOKE-F1",
                    name="Smoke Room Service Dish",
                    item_type="VEG",
                    price=Decimal("350.00"),
                    status="ACTIVE",
                )

            source = ReservationSource.objects.first()
            if not source:
                source = ReservationSource.objects.create(code="DIRECT", name="Direct")

            guest = GuestProfile.objects.create(
                tenant=tenant, first_name="Smoke", last_name="FolioGuest"
            )
            today = timezone.now().date()
            reservation = Reservation.objects.create(
                tenant=tenant,
                property=prop,
                primary_guest=guest,
                reservation_source=source,
                booking_date=today,
                arrival_date=today,
                departure_date=today + timedelta(days=1),
                confirmation_number=f"SMOKE-RC-{uuid4().hex[:8].upper()}",
                reservation_type="Transient",
                market_segment="LEISURE",
                status="CHECKED_IN",
            )
            folio = GuestFolio.objects.create(
                tenant=tenant,
                reservation=reservation,
                folio_number=f"FOLIO-SMOKE-{uuid4().hex[:6].upper()}",
                status="OPEN",
                total_charges=Decimal("1000.00"),
                total_payments=Decimal("0.00"),
            )
            balance_before = Decimal(str(folio.balance))

            created = OrderService.create_order(
                {
                    "outlet_id": str(outlet.id),
                    "order_type": "ROOM_SERVICE",
                    "room_number": "204",
                    "reservation_id": str(reservation.id),
                    "folio_id": str(folio.id),
                    "guest_name": "Smoke FolioGuest",
                    "items": [
                        {
                            "menu_item_id": str(item.id),
                            "name": item.name,
                            "quantity": 1,
                            "price": str(item.price),
                        }
                    ],
                    "grand_total": str(item.price),
                    "send_kot": True,
                }
            )
            order_id = created["id"]
            key = f"smoke-settle-{uuid4().hex}"

            settled = OrderService.settle_order(
                order_id,
                {
                    "payment_mode": "ROOM_CHARGE",
                    "reservation_id": str(reservation.id),
                    "folio_id": str(folio.id),
                    "idempotency_key": key,
                },
            )
            assert settled["status"] == "SETTLED", settled
            assert settled.get("folio_transaction_id"), settled

            folio.refresh_from_db()
            expected = balance_before + Decimal(str(item.price))
            assert Decimal(str(folio.balance)) == expected, (
                folio.balance,
                expected,
            )

            txn_count = FolioTransaction.objects.filter(
                folio=folio, charge_code="POS_ROOM_SERVICE"
            ).count()
            assert txn_count == 1, txn_count

            # Idempotent replay — no second charge
            replay = OrderService.settle_order(
                order_id,
                {
                    "payment_mode": "ROOM_CHARGE",
                    "reservation_id": str(reservation.id),
                    "folio_id": str(folio.id),
                    "idempotency_key": key,
                },
            )
            assert replay.get("idempotent_replay") is True, replay
            folio.refresh_from_db()
            assert Decimal(str(folio.balance)) == expected
            assert (
                FolioTransaction.objects.filter(
                    folio=folio, charge_code="POS_ROOM_SERVICE"
                ).count()
                == 1
            )
            assert FolioPostingLog.objects.filter(
                idempotency_key=key, status="SUCCESS"
            ).count() == 1

            # Cash settle path on a second order
            created2 = OrderService.create_order(
                {
                    "outlet_id": str(outlet.id),
                    "order_type": "DINE_IN",
                    "table_number": "T-1",
                    "items": [
                        {
                            "name": "Tea",
                            "quantity": 1,
                            "price": "50.00",
                        }
                    ],
                    "grand_total": "50.00",
                }
            )
            cash = OrderService.settle_order(
                created2["id"], {"payment_mode": "CASH"}
            )
            assert cash["status"] == "SETTLED", cash
            assert cash["payment_mode"] == "CASH" or cash.get("paymentMode") == "Cash"

            self.stdout.write(
                self.style.SUCCESS(
                    f"PostgreSQL folio smoke OK — order={settled['orderNumber']} "
                    f"folio={folio.folio_number} bal={folio.balance} "
                    f"host={settings.DATABASES['default'].get('HOST')}"
                )
            )
            transaction.set_rollback(True)

        self.stdout.write("Rolled back smoke rows (no lasting DB changes).")
