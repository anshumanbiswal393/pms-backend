"""
Part 5 — Due bills, day-end summary, and CSV export helpers.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.POS.models import (
    POSOrder,
    POSPayment,
    POSDueBill,
    POSDayClose,
    Outlet,
)
from apps.POS.services.orders import OrderService, PAYMENT_UI, ORDER_TYPE_UI


def _aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 15:
        return "0-15"
    if days_overdue <= 30:
        return "16-30"
    return "30+"


class DueLedgerService:
    """Pending Payments / due settlement ledger."""

    @classmethod
    def _next_bill_number(cls, property_id) -> str:
        last = (
            POSDueBill.objects.all_with_deleted()
            .filter(property_id=property_id, bill_number__startswith="BILL-")
            .order_by("-created_at")
            .values_list("bill_number", flat=True)
            .first()
        )
        seq = 8900
        if last:
            try:
                seq = int(str(last).split("-")[-1])
            except (TypeError, ValueError):
                seq = 8900
        return f"BILL-{seq + 1}"

    @classmethod
    def serialize_due(cls, bill: POSDueBill) -> dict[str, Any]:
        order = bill.order
        due_date = bill.due_date or (bill.created_at.date() if bill.created_at else timezone.now().date())
        days_overdue = max(0, (timezone.now().date() - due_date).days)
        items_summary = ""
        if hasattr(order, "items"):
            names = [
                f"{i.item_name} × {int(i.quantity) if float(i.quantity).is_integer() else i.quantity}"
                for i in order.items.all()
                if not i.is_void
            ]
            items_summary = ", ".join(names)

        return {
            "id": str(bill.id),
            "billNo": bill.bill_number,
            "orderId": str(order.id),
            "orderNumber": order.order_number,
            "orderType": ORDER_TYPE_UI.get(order.order_type, order.order_type),
            "tableOrRoom": order.table_number or order.room_number or "",
            "tableId": str(order.table_id) if order.table_id else None,
            "customerName": order.guest_name or "Walk-in Guest",
            "customerPhone": order.guest_phone or "--",
            "waiterName": order.waiter_name or "Captain",
            "itemsSummary": items_summary,
            "totalAmount": float(bill.total_amount),
            "paidAmount": float(bill.paid_amount),
            "dueAmount": float(bill.due_amount),
            "dueDate": due_date.strftime("%d %b %Y"),
            "daysOverdue": days_overdue,
            "status": {
                "PENDING": "Pending",
                "PARTIAL": "Partial",
                "SETTLED": "Settled",
            }.get(bill.status, bill.status),
            "settlementMode": PAYMENT_UI.get(bill.settlement_mode, bill.settlement_mode),
            "agingBucket": _aging_bucket(days_overdue),
            "createdAt": bill.created_at.isoformat() if bill.created_at else None,
            "outletId": str(bill.outlet_id),
            "propertyId": str(bill.property_id),
        }

    @classmethod
    def create_for_order(
        cls,
        order: POSOrder,
        *,
        paid_amount: Decimal | None = None,
        user=None,
    ) -> POSDueBill:
        paid = Decimal(str(paid_amount or 0)).quantize(Decimal("0.01"))
        total = Decimal(str(order.grand_total)).quantize(Decimal("0.01"))
        due = (total - paid).quantize(Decimal("0.01"))
        if due < 0:
            due = Decimal("0.00")

        existing = POSDueBill.objects.filter(order=order, deleted_at__isnull=True).first()

        if existing:
            bill = existing
            bill.paid_amount = paid
            bill.due_amount = due
            bill.total_amount = total
            bill.recompute_status()
            bill.save()
            return bill

        bill = POSDueBill.objects.create(
            order=order,
            tenant_id=order.tenant_id,
            property_id=order.property_id,
            outlet_id=order.outlet_id,
            bill_number=cls._next_bill_number(order.property_id),
            total_amount=total,
            paid_amount=paid,
            due_amount=due,
            due_date=timezone.now().date(),
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        bill.recompute_status()
        bill.save(update_fields=["status", "updated_at"])
        return bill

    @classmethod
    def list_dues(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        include_settled: bool = False,
    ) -> list[dict[str, Any]]:
        qs = (
            POSDueBill.objects.filter(deleted_at__isnull=True)
            .select_related("order", "outlet")
            .prefetch_related("order__items")
            .order_by("-created_at")
        )
        if not include_settled:
            qs = qs.exclude(status="SETTLED")
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        return [cls.serialize_due(b) for b in qs]

    @classmethod
    @transaction.atomic
    def settle_due(
        cls,
        bill_id,
        data: dict[str, Any],
        *,
        user=None,
    ) -> dict[str, Any]:
        bill = (
            POSDueBill.objects.select_for_update()
            .filter(pk=bill_id, deleted_at__isnull=True)
            .select_related("order")
            .first()
        )
        if not bill:
            raise ValidationError({"bill": "Due bill not found."})
        if bill.status == "SETTLED":
            raise ValidationError({"bill": "Due bill already settled."})

        mode = OrderService._normalize_payment_mode(
            data.get("payment_mode") or data.get("paymentMode") or data.get("settlementMode")
        )
        if not mode:
            raise ValidationError({"payment_mode": "payment_mode is required."})
        if mode == "ROOM_CHARGE":
            raise ValidationError(
                {
                    "payment_mode": (
                        "Use order settle ROOM_CHARGE for folio posting; "
                        "due settle supports CASH/CARD/UPI/SPLIT."
                    )
                }
            )

        pay_now = data.get("paid_amount") or data.get("paidAmount") or data.get("amount")
        pay_amt = (
            Decimal(str(pay_now))
            if pay_now is not None
            else Decimal(str(bill.due_amount))
        )
        if pay_amt <= 0:
            raise ValidationError({"amount": "Payment amount must be positive."})

        pay_amt = min(pay_amt, Decimal(str(bill.due_amount)))
        bill.paid_amount = (Decimal(str(bill.paid_amount)) + pay_amt).quantize(
            Decimal("0.01")
        )
        bill.due_amount = (
            Decimal(str(bill.total_amount)) - Decimal(str(bill.paid_amount))
        ).quantize(Decimal("0.01"))
        bill.settlement_mode = mode
        bill.recompute_status()
        if bill.status == "SETTLED":
            bill.settled_at = timezone.now()
        bill.save()

        POSPayment.objects.create(
            order=bill.order,
            mode=mode,
            amount=pay_amt,
            status="CAPTURED",
            reference=data.get("reference") or bill.bill_number,
            meta={"due_bill_id": str(bill.id)},
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        order = bill.order
        if bill.status == "SETTLED":
            now = timezone.now()
            order.status = "SETTLED"
            order.settled_at = now
            order.payment_mode = mode
            order.save(update_fields=["status", "settled_at", "payment_mode", "updated_at"])
            OrderService._release_table(order)

        bill = (
            POSDueBill.objects.filter(pk=bill.pk)
            .select_related("order")
            .prefetch_related("order__items")
            .first()
        )
        return cls.serialize_due(bill)


class DayCloseService:
    """Day-end summary + optional close snapshot."""

    @classmethod
    def summarize_range(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        start_date: date | None = None,
        end_date: date | None = None,
        days: int = 14,
    ) -> dict[str, Any]:
        end = end_date or timezone.now().date()
        start = start_date or (end - timedelta(days=max(days - 1, 0)))

        qs = POSOrder.objects.filter(
            deleted_at__isnull=True,
            status="SETTLED",
            settled_at__date__gte=start,
            settled_at__date__lte=end,
        )
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        grouped = (
            qs.annotate(biz_date=TruncDate("settled_at"))
            .values("biz_date")
            .annotate(
                order_count=Count("id"),
                total_amount=Sum("grand_total"),
            )
            .order_by("-biz_date")
        )

        closed_dates = set()
        close_qs = POSDayClose.objects.filter(
            is_closed=True,
            business_date__gte=start,
            business_date__lte=end,
        )
        if property_id:
            close_qs = close_qs.filter(property_id=property_id)
        if outlet_id:
            close_qs = close_qs.filter(outlet_id=outlet_id)
        closed_dates = set(close_qs.values_list("business_date", flat=True))

        records = []
        for row in grouped:
            d = row["biz_date"]
            records.append(
                {
                    "id": d.isoformat() if d else "",
                    "date": d.strftime("%d %b %Y") if d else "",
                    "businessDate": d.isoformat() if d else None,
                    "orderCount": row["order_count"] or 0,
                    "totalAmount": float(row["total_amount"] or 0),
                    "isClosed": bool(d in closed_dates) if d else False,
                }
            )

        return {
            "success": True,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "count": len(records),
            "records": records,
        }

    @classmethod
    def day_detail(
        cls,
        *,
        business_date: date,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> dict[str, Any]:
        qs = POSOrder.objects.filter(
            deleted_at__isnull=True,
            status="SETTLED",
            settled_at__date=business_date,
        )
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        totals = {m: Decimal("0.00") for m in ("CASH", "CARD", "UPI", "ROOM_CHARGE", "DUE", "SPLIT")}
        agg = qs.aggregate(order_count=Count("id"), grand=Sum("grand_total"))
        order_count = agg["order_count"] or 0
        grand = Decimal(str(agg["grand"] or 0))

        pay_rows = (
            POSPayment.objects.filter(order__in=qs, status="CAPTURED")
            .values("mode")
            .annotate(total=Sum("amount"))
        )
        used_payments = False
        for row in pay_rows:
            used_payments = True
            mode = row["mode"] or "CASH"
            if mode in totals:
                totals[mode] += Decimal(str(row["total"] or 0))
        if not used_payments:
            mode_rows = qs.values("payment_mode").annotate(total=Sum("grand_total"))
            for row in mode_rows:
                mode = row["payment_mode"] or "CASH"
                if mode in totals:
                    totals[mode] += Decimal(str(row["total"] or 0))

        due_qs = POSDueBill.objects.filter(
            deleted_at__isnull=True
        ).exclude(status="SETTLED")
        if property_id:
            due_qs = due_qs.filter(property_id=property_id)
        if outlet_id:
            due_qs = due_qs.filter(outlet_id=outlet_id)
        open_due_count = due_qs.count()
        open_due_amount = due_qs.aggregate(s=Sum("due_amount"))["s"] or Decimal("0.00")

        closed = POSDayClose.objects.filter(
            business_date=business_date, is_closed=True
        )
        if property_id:
            closed = closed.filter(property_id=property_id)
        if outlet_id:
            closed = closed.filter(outlet_id=outlet_id)
        close_row = closed.first()

        return {
            "businessDate": business_date.isoformat(),
            "orderCount": order_count,
            "totalAmount": float(grand),
            "byPaymentMode": {k: float(v) for k, v in totals.items()},
            "openDueCount": open_due_count,
            "openDueAmount": float(open_due_amount),
            "isClosed": bool(close_row),
            "closedAt": close_row.closed_at.isoformat() if close_row and close_row.closed_at else None,
        }

    @classmethod
    @transaction.atomic
    def close_day(
        cls,
        *,
        business_date: date,
        property_id,
        outlet_id=None,
        tenant_id=None,
        user=None,
    ) -> dict[str, Any]:
        if not property_id and outlet_id:
            outlet = Outlet.objects.filter(id=outlet_id).first()
            if outlet:
                property_id = outlet.property_id
                tenant_id = tenant_id or outlet.tenant_id
        if not property_id:
            raise ValidationError({"property_id": "property_id is required to close day."})
        detail = cls.day_detail(
            business_date=business_date,
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
        )
        modes = detail["byPaymentMode"]
        outlet = None
        if outlet_id:
            outlet = Outlet.objects.filter(id=outlet_id).first()
        tenant = tenant_id
        if not tenant and outlet:
            tenant = outlet.tenant_id

        obj, _ = POSDayClose.objects.update_or_create(
            property_id=property_id,
            outlet_id=outlet_id,
            business_date=business_date,
            defaults={
                "tenant_id": tenant,
                "order_count": detail["orderCount"],
                "total_amount": detail["totalAmount"],
                "cash_total": modes.get("CASH", 0),
                "card_total": modes.get("CARD", 0),
                "upi_total": modes.get("UPI", 0),
                "room_charge_total": modes.get("ROOM_CHARGE", 0),
                "due_total": modes.get("DUE", 0),
                "split_total": modes.get("SPLIT", 0),
                "open_due_count": detail["openDueCount"],
                "open_due_amount": detail["openDueAmount"],
                "is_closed": True,
                "closed_at": timezone.now(),
                "summary": detail,
                "updated_by": user
                if getattr(user, "is_authenticated", False)
                else None,
            },
        )
        return {
            "id": str(obj.id),
            "businessDate": business_date.isoformat(),
            "isClosed": True,
            "closedAt": obj.closed_at.isoformat() if obj.closed_at else None,
            **detail,
        }


class ExportService:
    """CSV exporters for Order History / Due Settlement (Excel-friendly)."""

    @classmethod
    def orders_history_csv(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> str:
        data = OrderService.list_history(
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
            limit=2000,
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Order Number",
                "Type",
                "Status",
                "Customer",
                "Phone",
                "Table/Room",
                "Payment Mode",
                "Subtotal",
                "Tax",
                "Grand Total",
                "Placed At",
                "Settled At",
            ]
        )
        for o in data.get("orders", []):
            writer.writerow(
                [
                    o.get("orderNumber"),
                    o.get("typeLabel"),
                    o.get("status"),
                    o.get("customerName"),
                    o.get("customerPhone"),
                    o.get("tableOrRoom"),
                    o.get("paymentMode"),
                    o.get("subtotal"),
                    o.get("taxAmount"),
                    o.get("grandTotal"),
                    o.get("placedAt"),
                    o.get("settledAt"),
                ]
            )
        return buf.getvalue()

    @classmethod
    def dues_csv(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> str:
        rows = DueLedgerService.list_dues(
            property_id=property_id,
            outlet_id=outlet_id,
            tenant_id=tenant_id,
            include_settled=False,
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Bill No",
                "Order Number",
                "Order Type",
                "Customer",
                "Phone",
                "Table/Room",
                "Total",
                "Paid",
                "Due",
                "Status",
                "Due Date",
                "Days Overdue",
                "Aging",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.get("billNo"),
                    r.get("orderNumber"),
                    r.get("orderType"),
                    r.get("customerName"),
                    r.get("customerPhone"),
                    r.get("tableOrRoom"),
                    r.get("totalAmount"),
                    r.get("paidAmount"),
                    r.get("dueAmount"),
                    r.get("status"),
                    r.get("dueDate"),
                    r.get("daysOverdue"),
                    r.get("agingBucket"),
                ]
            )
        return buf.getvalue()
