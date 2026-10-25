"""
Atomic rollback smoke for Part 5 dues + day-end on PMS PostgreSQL.

  python manage.py check_pos_db
  python manage.py smoke_pos_dues
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.POS.models import Outlet, MenuCategory, MenuItem
from apps.POS.services.menu import MenuCatalogService
from apps.POS.services.orders import OrderService
from apps.POS.services.dues import DueLedgerService, DayCloseService, ExportService
from apps.core.tenants.models import Tenant, Property


class Command(BaseCommand):
    help = "Atomic rollback smoke for POS dues / day-end / export."

    def handle(self, *args, **options):
        call_command("check_pos_db")

        with transaction.atomic():
            tenant = Tenant.objects.first()
            prop = Property.objects.filter(tenant=tenant).first() if tenant else None
            if not tenant or not prop:
                raise CommandError("Need Tenant + Property.")

            outlet = Outlet.objects.filter(
                property=prop, deleted_at__isnull=True, is_active=True
            ).first()
            if not outlet:
                outlet = Outlet.objects.create(
                    tenant=tenant,
                    property=prop,
                    code="SMOKE-DUE",
                    name="Smoke Due Outlet",
                    outlet_type="PRIMARY",
                    is_active=True,
                )

            cat = MenuCategory.objects.filter(outlet=outlet).first()
            if not cat:
                cat = MenuCategory.objects.create(
                    outlet=outlet, name="Starters", is_active=True
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
                    code="#SMOKE-DUE-1",
                    name="Due Smoke Item",
                    item_type="VEG",
                    price=Decimal("400.00"),
                    status="ACTIVE",
                )

            created = OrderService.create_order(
                {
                    "outlet_id": str(outlet.id),
                    "order_type": "DINE_IN",
                    "table_number": "T-77",
                    "guest_name": "Due Guest",
                    "items": [
                        {
                            "menu_item_id": str(item.id),
                            "name": item.name,
                            "quantity": 1,
                            "price": str(item.price),
                        }
                    ],
                    "grand_total": str(item.price),
                }
            )
            settled = OrderService.settle_order(
                created["id"], {"payment_mode": "DUE"}
            )
            assert settled["status"] == "SETTLED", settled
            assert settled.get("dueBill"), settled
            assert settled["dueBill"]["dueAmount"] == float(item.price)

            dues = DueLedgerService.list_dues(outlet_id=outlet.id)
            assert any(d["orderId"] == created["id"] for d in dues), dues
            bill_id = settled["dueBill"]["id"]

            # Partial collect
            partial = DueLedgerService.settle_due(
                bill_id, {"payment_mode": "CASH", "paid_amount": "150.00"}
            )
            assert partial["status"] == "Partial", partial
            assert abs(partial["dueAmount"] - (float(item.price) - 150)) < 0.001

            # Full collect
            final = DueLedgerService.settle_due(
                bill_id, {"payment_mode": "UPI", "paid_amount": str(partial["dueAmount"])}
            )
            assert final["status"] == "Settled", final
            assert final["dueAmount"] == 0.0

            open_dues = DueLedgerService.list_dues(outlet_id=outlet.id)
            assert not any(d["id"] == bill_id for d in open_dues)

            today = timezone.now().date()
            summary = DayCloseService.summarize_range(
                property_id=prop.id, outlet_id=outlet.id, days=7
            )
            assert summary["success"] is True

            detail = DayCloseService.day_detail(
                business_date=today, property_id=prop.id, outlet_id=outlet.id
            )
            assert detail["orderCount"] >= 1

            closed = DayCloseService.close_day(
                business_date=today,
                property_id=prop.id,
                outlet_id=outlet.id,
                tenant_id=tenant.id,
            )
            assert closed["isClosed"] is True

            hist_csv = ExportService.orders_history_csv(outlet_id=outlet.id)
            assert "Order Number" in hist_csv
            due_csv = ExportService.dues_csv(outlet_id=outlet.id)
            assert "Bill No" in due_csv

            self.stdout.write(
                self.style.SUCCESS(
                    f"PostgreSQL dues smoke OK — bill={settled['dueBill']['billNo']} "
                    f"day={today}"
                )
            )
            transaction.set_rollback(True)

        self.stdout.write("Rolled back smoke rows (no lasting DB changes).")
