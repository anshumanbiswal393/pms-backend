"""
POS sales / tax / cashier reports.

One endpoint, `kind=` + date range. Aggregations stay in SQL so the UI can
open any of the 12 catalog reports without loading every order into Python.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import (
    Avg,
    Count,
    DecimalField,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, ExtractHour, TruncDate
from django.utils import timezone

from apps.POS.models import (
    KOTTicket,
    Outlet,
    POSOrder,
    POSOrderItem,
    POSPayment,
)
from apps.POS.services.orders import ORDER_TYPE_UI, PAYMENT_UI

DINE_TYPES = ("DINE_IN", "ROOM_SERVICE")
TAKEAWAY_TYPES = ("TAKEAWAY",)
DELIVERY_TYPES = ("DELIVERY", "ONLINE")

KIND_ALIASES = {
    "REP-01": "overview",
    "REP-02": "items",
    "REP-03": "invoices",
    "REP-04": "biller",
    "REP-05": "channels",
    "REP-06": "daywise",
    "REP-07": "discounts",
    "REP-08": "category",
    "REP-09": "customers",
    "REP-10": "hourly",
    "REP-11": "payments",
    "REP-12": "gst",
    "sales": "overview",
}

PAYMENT_REPORT_LABEL = {
    "CASH": "Cash Drawer Collection",
    "CARD": "Credit / Debit Cards",
    "UPI": "UPI",
    "ROOM_CHARGE": "Hotel Room Post (Guest Folio)",
    "DUE": "Due / Credit",
    "SPLIT": "Split Tender",
}

CHANNEL_META = {
    "DINE_IN": ("Dine-In", "POS Table Desk"),
    "TAKEAWAY": ("Direct Counter Takeaway", "POS Walk-In"),
    "ROOM_SERVICE": ("Room Service", "Hotel PMS Interop"),
    "DELIVERY": ("Delivery", "Direct"),
    "ONLINE": ("Online Aggregator", "Aggregator Integration"),
}

MONEY = DecimalField(max_digits=14, decimal_places=2)


def _d(val, default="0") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    return Decimal(str(val))


def _f(val) -> float:
    return float(_d(val))


def _money_sum(field: str, **filter_kwargs):
    q = Q(**filter_kwargs) if filter_kwargs else Q()
    return Coalesce(
        Sum(field, filter=q),
        Value(0, output_field=MONEY),
        output_field=MONEY,
    )


def resolve_scope(
    *,
    property_id=None,
    outlet_id=None,
    tenant_id=None,
) -> dict[str, Any]:
    if outlet_id and (not property_id or not tenant_id):
        row = (
            Outlet.objects.filter(id=outlet_id)
            .values("property_id", "tenant_id", "name")
            .first()
        )
        if row:
            property_id = property_id or row["property_id"]
            tenant_id = tenant_id or row["tenant_id"]
    return {
        "property_id": property_id,
        "outlet_id": outlet_id,
        "tenant_id": tenant_id,
    }


def parse_iso_date(raw) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()


def default_range(days: int = 7) -> tuple[date, date]:
    end = timezone.localdate()
    start = end - timedelta(days=max(days - 1, 0))
    return start, end


def _aware_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    if timezone.is_naive(start_dt) and timezone.is_aware(timezone.now()):
        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(start_dt, tz)
        end_dt = timezone.make_aware(end_dt, tz)
    return start_dt, end_dt


def _shift_label(hour: int | None) -> str:
    if hour is None:
        return "Unspecified"
    if 6 <= hour < 16:
        return "Day Shift"
    if 16 <= hour < 23:
        return "Evening Shift"
    return "Night Shift"


def _slot_label(hour: int, is_peak: bool = False) -> str:
    hour = int(hour) % 24
    nxt = (hour + 1) % 24

    def fmt(h: int) -> str:
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12:02d}:00 {ampm}"

    label = f"{fmt(hour)} - {fmt(nxt)}"
    if is_peak:
        label += " (Peak)"
    return label


def _customer_segment(visits: int) -> str:
    if visits >= 10:
        return "Platinum VIP"
    if visits >= 5:
        return "Gold Regular"
    if visits >= 3:
        return "Silver Returning"
    return "New Guest"


class SalesAnalyticsService:
    """Date-scoped POS reports matching the Reports catalog (REP-01 … REP-12)."""

    @classmethod
    def run(
        cls,
        *,
        kind: str = "items",
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        resolved = resolve_scope(
            property_id=property_id, outlet_id=outlet_id, tenant_id=tenant_id
        )
        kind = KIND_ALIASES.get((kind or "items").strip(), (kind or "items").strip())
        handler = {
            "dashboard": cls._dashboard,
            "overview": cls._overview,
            "items": cls._items,
            "invoices": cls._invoices,
            "biller": cls._biller,
            "channels": cls._channels,
            "daywise": cls._daywise,
            "discounts": cls._discounts,
            "category": cls._category,
            "customers": cls._customers,
            "hourly": cls._hourly,
            "payments": cls._payments,
            "gst": cls._gst,
        }.get(kind)
        if handler is None:
            return {
                "success": False,
                "detail": f"Unknown report kind '{kind}'.",
                "kind": kind,
                "records": [],
                "count": 0,
            }
        payload = handler(
            property_id=resolved["property_id"],
            outlet_id=resolved["outlet_id"],
            tenant_id=resolved["tenant_id"],
            start_date=start_date,
            end_date=end_date,
            limit=max(1, min(int(limit or 200), 1000)),
        )
        payload.setdefault("success", True)
        payload.setdefault("kind", kind)
        if start_date:
            payload.setdefault("startDate", start_date.isoformat())
        if end_date:
            payload.setdefault("endDate", end_date.isoformat())
        payload.setdefault("count", len(payload.get("records") or []))
        return payload

    @classmethod
    def _scope_orders(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        start_date: date | None = None,
        end_date: date | None = None,
        statuses: tuple[str, ...] = ("SETTLED",),
        date_field: str = "settled_at",
    ):
        qs = POSOrder.objects.filter(status__in=statuses)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if start_date and end_date:
            lo, hi = _aware_bounds(start_date, end_date)
            qs = qs.filter(**{f"{date_field}__gte": lo, f"{date_field}__lt": hi})
        elif start_date:
            lo, _ = _aware_bounds(start_date, start_date)
            qs = qs.filter(**{f"{date_field}__gte": lo})
        elif end_date:
            _, hi = _aware_bounds(end_date, end_date)
            qs = qs.filter(**{f"{date_field}__lt": hi})
        return qs

    @classmethod
    def _scope_items(cls, **kwargs):
        return POSOrderItem.objects.filter(
            is_void=False,
            order__in=cls._scope_orders(**kwargs),
        )

    @classmethod
    def _overview(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = cls._scope_orders(**scope).annotate(biz_date=TruncDate("settled_at"))
        rows = (
            qs.values("biz_date", "outlet_id", "outlet__name")
            .annotate(
                totalBills=Count("id"),
                dineInSales=_money_sum("grand_total", order_type__in=DINE_TYPES),
                takeawaySales=_money_sum("grand_total", order_type__in=TAKEAWAY_TYPES),
                deliverySales=_money_sum("grand_total", order_type__in=DELIVERY_TYPES),
                discounts=_money_sum("discount_amount"),
                taxes=_money_sum("tax_amount"),
                netSales=_money_sum("grand_total"),
                subtotal=_money_sum("subtotal"),
                service=_money_sum("service_charge"),
            )
            .order_by("-biz_date", "outlet__name")[:limit]
        )
        records = []
        for i, r in enumerate(rows, start=1):
            d = r["biz_date"]
            gross = _f(r["subtotal"]) + _f(r["service"])
            records.append(
                {
                    "id": f"{d.isoformat() if d else i}-{r['outlet_id']}",
                    "date": d.isoformat() if d else "",
                    "outlet": r["outlet__name"] or "",
                    "totalBills": r["totalBills"] or 0,
                    "dineInSales": _f(r["dineInSales"]),
                    "takeawaySales": _f(r["takeawaySales"]),
                    "deliverySales": _f(r["deliverySales"]),
                    "grossSales": round(gross, 2),
                    "discounts": _f(r["discounts"]),
                    "taxes": _f(r["taxes"]),
                    "netSales": _f(r["netSales"]),
                }
            )
        return {"records": records}

    @classmethod
    def _daywise(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = cls._scope_orders(**scope).annotate(biz_date=TruncDate("settled_at"))
        rows = (
            qs.values("biz_date")
            .annotate(
                totalBills=Count("id"),
                dineInRev=_money_sum("grand_total", order_type__in=DINE_TYPES),
                takeawayRev=_money_sum("grand_total", order_type__in=TAKEAWAY_TYPES),
                deliveryRev=_money_sum("grand_total", order_type__in=DELIVERY_TYPES),
                totalNetRev=_money_sum("grand_total"),
            )
            .order_by("-biz_date")[:limit]
        )
        records = []
        for i, r in enumerate(rows, start=1):
            d = r["biz_date"]
            records.append(
                {
                    "id": d.isoformat() if d else str(i),
                    "date": d.isoformat() if d else "",
                    "dayOfWeek": d.strftime("%A") if d else "",
                    "dineInRev": _f(r["dineInRev"]),
                    "takeawayRev": _f(r["takeawayRev"]),
                    "deliveryRev": _f(r["deliveryRev"]),
                    "totalBills": r["totalBills"] or 0,
                    "totalNetRev": _f(r["totalNetRev"]),
                }
            )
        return {"records": records}

    @classmethod
    def _items(cls, *, limit: int, **scope) -> dict[str, Any]:
        rows = (
            cls._scope_items(**scope)
            .values(
                "item_code",
                "item_name",
                "category_name",
                "order__outlet__name",
            )
            .annotate(
                qtySold=Sum("quantity"),
                grossRevenue=Sum("line_total"),
                unitPrice=Avg("unit_price"),
            )
            .order_by("-grossRevenue")[:limit]
        )
        items = []
        for i, r in enumerate(rows, start=1):
            gross = _f(r["grossRevenue"])
            rec = {
                "id": str(i),
                "code": r["item_code"] or "",
                "name": r["item_name"],
                "itemCode": r["item_code"] or "",
                "itemName": r["item_name"],
                "category": r["category_name"] or "",
                "outlet": r["order__outlet__name"] or "",
                "unitPrice": round(_f(r["unitPrice"]), 2),
                "qtySold": _f(r["qtySold"]),
                "quantity": _f(r["qtySold"]),
                "grossRevenue": round(gross, 2),
                "discountAmount": 0.0,
                "netRevenue": round(gross, 2),
                "revenue": round(gross, 2),
            }
            items.append(rec)
        return {
            "records": items,
            "items": items,
            "totalRevenue": round(sum(i["revenue"] for i in items), 2),
        }

    @classmethod
    def _category(cls, *, limit: int, **scope) -> dict[str, Any]:
        rows = list(
            cls._scope_items(**scope)
            .values("category_name")
            .annotate(
                itemCount=Count("item_name", distinct=True),
                qtySold=Sum("quantity"),
                totalRevenue=Sum("line_total"),
            )
            .order_by("-totalRevenue")[:limit]
        )
        total = sum(_f(r["totalRevenue"]) for r in rows) or 0.0
        records = []
        for i, r in enumerate(rows, start=1):
            rev = _f(r["totalRevenue"])
            records.append(
                {
                    "id": str(i),
                    "categoryName": r["category_name"] or "Uncategorized",
                    "itemCount": r["itemCount"] or 0,
                    "qtySold": _f(r["qtySold"]),
                    "totalRevenue": round(rev, 2),
                    "contributionPct": round((rev / total) * 100, 1) if total else 0.0,
                    "profitMargin": 0,
                }
            )
        return {"records": records}

    @classmethod
    def _invoices(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = (
            cls._scope_orders(**scope)
            .select_related("outlet")
            .order_by("-settled_at")[:limit]
        )
        records = []
        for order in qs:
            token = (
                order.table_number
                or (f"Room {order.room_number}" if order.room_number else None)
                or "—"
            )
            ts = order.settled_at or order.placed_at
            records.append(
                {
                    "id": str(order.id),
                    "invoiceNo": order.order_number,
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M") if ts else "",
                    "outlet": order.outlet.name if order.outlet_id else "",
                    "orderType": ORDER_TYPE_UI.get(order.order_type, order.order_type),
                    "tableToken": token,
                    "customer": order.guest_name or "Walk-in",
                    "paymentMode": PAYMENT_UI.get(order.payment_mode, order.payment_mode)
                    or "—",
                    "subTotal": _f(order.subtotal),
                    "tax": _f(order.tax_amount),
                    "grandTotal": _f(order.grand_total),
                    "status": "Settled" if order.status == "SETTLED" else order.status,
                }
            )
        return {"records": records}

    @classmethod
    def _biller(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = cls._scope_orders(**scope).annotate(hour=ExtractHour("settled_at"))
        rows = (
            qs.values("waiter_name", "outlet__name", "hour")
            .annotate(
                totalPax=Sum("pax"),
                totalBills=Count("id"),
                totalSales=Sum("grand_total"),
            )
            .order_by("-totalSales")
        )
        merged: dict[tuple, dict] = {}
        for r in rows:
            shift = _shift_label(r["hour"])
            waiter = (r["waiter_name"] or "").strip() or "Unassigned"
            key = (waiter, r["outlet__name"] or "", shift)
            bucket = merged.setdefault(
                key,
                {
                    "billerName": waiter,
                    "outlet": r["outlet__name"] or "",
                    "shift": shift,
                    "totalPax": 0,
                    "totalBills": 0,
                    "totalSales": 0.0,
                },
            )
            bucket["totalPax"] += int(r["totalPax"] or 0)
            bucket["totalBills"] += int(r["totalBills"] or 0)
            bucket["totalSales"] += _f(r["totalSales"])

        records = []
        for i, row in enumerate(
            sorted(merged.values(), key=lambda x: x["totalSales"], reverse=True)[:limit],
            start=1,
        ):
            bills = row["totalBills"] or 0
            pax = row["totalPax"] or 0
            sales = round(row["totalSales"], 2)
            records.append(
                {
                    "id": str(i),
                    "billerName": row["billerName"],
                    "empId": "—",
                    "outlet": row["outlet"],
                    "shift": row["shift"],
                    "totalPax": pax,
                    "totalBills": bills,
                    "totalSales": sales,
                    "avgPerPax": round(sales / pax, 1) if pax else 0,
                    "avgPerBill": round(sales / bills, 2) if bills else 0,
                }
            )
        return {"records": records}

    @classmethod
    def _channels(cls, *, limit: int, **scope) -> dict[str, Any]:
        settled = (
            cls._scope_orders(**scope, statuses=("SETTLED",))
            .values("order_type")
            .annotate(totalOrders=Count("id"), netSettled=Sum("grand_total"))
        )
        cancelled = (
            cls._scope_orders(
                **scope, statuses=("CANCELLED",), date_field="cancelled_at"
            )
            .values("order_type")
            .annotate(cancelledOrders=Count("id"), cancelledAmount=Sum("grand_total"))
        )
        by_type: dict[str, dict] = {}
        for r in settled:
            by_type[r["order_type"] or "DINE_IN"] = {
                "totalOrders": r["totalOrders"] or 0,
                "netSettled": _f(r["netSettled"]),
                "cancelledOrders": 0,
            }
        for r in cancelled:
            key = r["order_type"] or "DINE_IN"
            bucket = by_type.setdefault(
                key, {"totalOrders": 0, "netSettled": 0.0, "cancelledOrders": 0}
            )
            bucket["cancelledOrders"] = r["cancelledOrders"] or 0

        records = []
        for i, (otype, data) in enumerate(by_type.items(), start=1):
            label, channel = CHANNEL_META.get(otype, (otype or "Other", "POS"))
            delivered = max(data["totalOrders"], 0)
            records.append(
                {
                    "id": str(i),
                    "subOrderType": label,
                    "channel": channel,
                    "totalOrders": delivered + data["cancelledOrders"],
                    "deliveredOrders": delivered,
                    "cancelledOrders": data["cancelledOrders"],
                    "grossAmount": round(data["netSettled"], 2),
                    "netSettled": round(data["netSettled"], 2),
                }
            )
        records.sort(key=lambda r: r["netSettled"], reverse=True)
        return {"records": records[:limit]}

    @classmethod
    def _discounts(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = (
            cls._scope_orders(**scope)
            .filter(discount_amount__gt=0)
            .select_related("outlet")
            .order_by("-settled_at")[:limit]
        )
        records = []
        for order in qs:
            meta = order.meta if isinstance(order.meta, dict) else {}
            original = _f(order.subtotal) + _f(order.tax_amount) + _f(order.service_charge)
            disc = _f(order.discount_amount)
            ts = order.settled_at or order.placed_at
            pct = round((disc / original) * 100, 1) if original else 0
            records.append(
                {
                    "id": str(order.id),
                    "billNo": order.order_number,
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M") if ts else "",
                    "authorizedBy": meta.get("authorizedBy")
                    or order.waiter_name
                    or "—",
                    "reason": meta.get("discountReason")
                    or meta.get("reason")
                    or order.order_note
                    or "Bill discount",
                    "discountType": f"Amount ₹{disc:.2f}"
                    if not pct
                    else f"Percentage ({pct}%)",
                    "originalAmount": round(original, 2),
                    "discountValue": disc,
                    "finalBill": _f(order.grand_total),
                }
            )
        return {"records": records}

    @classmethod
    def _customers(cls, *, limit: int, **scope) -> dict[str, Any]:
        rows = (
            cls._scope_orders(**scope)
            .exclude(guest_phone__isnull=True)
            .exclude(guest_phone="")
            .values("guest_phone")
            .annotate(
                customerName=Max("guest_name"),
                totalVisits=Count("id"),
                lastVisit=Max("settled_at"),
                lifetimeSpend=Sum("grand_total"),
            )
            .order_by("-lifetimeSpend")[:limit]
        )
        records = []
        for i, r in enumerate(rows, start=1):
            visits = r["totalVisits"] or 0
            spend = _f(r["lifetimeSpend"])
            last = r["lastVisit"]
            records.append(
                {
                    "id": str(i),
                    "customerName": r["customerName"] or "Guest",
                    "phone": r["guest_phone"],
                    "segment": _customer_segment(visits),
                    "totalVisits": visits,
                    "lastVisit": last.date().isoformat() if last else "",
                    "lifetimeSpend": round(spend, 2),
                    "avgOrderValue": round(spend / visits, 2) if visits else 0,
                }
            )
        return {"records": records}

    @classmethod
    def _hourly(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = cls._scope_orders(**scope)
        rows = list(
            qs.annotate(hour=ExtractHour("settled_at"))
            .values("hour")
            .annotate(
                ordersCount=Count("id"),
                totalCovers=Sum("pax"),
                salesAmount=Sum("grand_total"),
            )
            .order_by("hour")
        )
        peak_hour = None
        if rows:
            peak_hour = max(rows, key=lambda r: r["ordersCount"] or 0)["hour"]

        prep_by_hour: dict[int, float] = {}
        kot_rows = (
            KOTTicket.objects.filter(
                order__in=qs,
                sent_at__isnull=False,
                ready_at__isnull=False,
            )
            .annotate(
                hour=ExtractHour("order__settled_at"),
                duration=ExpressionWrapper(
                    F("ready_at") - F("sent_at"), output_field=DurationField()
                ),
            )
            .values("hour")
            .annotate(avg_duration=Avg("duration"))
        )
        for row in kot_rows:
            dur = row["avg_duration"]
            if row["hour"] is None or dur is None:
                continue
            seconds = dur.total_seconds() if hasattr(dur, "total_seconds") else 0
            if seconds >= 0:
                prep_by_hour[int(row["hour"])] = seconds / 60.0

        records = []
        for r in rows[:limit]:
            hour = r["hour"]
            if hour is None:
                continue
            mins = prep_by_hour.get(int(hour))
            records.append(
                {
                    "id": str(int(hour)),
                    "timeSlot": _slot_label(int(hour), is_peak=(hour == peak_hour)),
                    "ordersCount": r["ordersCount"] or 0,
                    "totalCovers": int(r["totalCovers"] or 0),
                    "salesAmount": _f(r["salesAmount"]),
                    "avgSpeed": f"{round(mins)} mins" if mins is not None else "—",
                }
            )
        return {"records": records}

    @classmethod
    def _payments(cls, *, limit: int, **scope) -> dict[str, Any]:
        orders = cls._scope_orders(**scope)
        pay = (
            POSPayment.objects.filter(order__in=orders, status="CAPTURED")
            .values("mode")
            .annotate(txnCount=Count("id"), collectedAmount=Sum("amount"))
            .order_by("-collectedAmount")
        )
        rows = list(pay)
        if not rows:
            rows = list(
                orders.exclude(payment_mode__isnull=True)
                .exclude(payment_mode="")
                .values("payment_mode")
                .annotate(txnCount=Count("id"), collectedAmount=Sum("grand_total"))
                .order_by("-collectedAmount")
            )
            for r in rows:
                r["mode"] = r.pop("payment_mode")

        records = []
        for i, r in enumerate(rows[:limit], start=1):
            mode = r.get("mode") or "CASH"
            collected = _f(r["collectedAmount"])
            records.append(
                {
                    "id": str(i),
                    "paymentMethod": PAYMENT_REPORT_LABEL.get(
                        mode, PAYMENT_UI.get(mode, mode)
                    ),
                    "txnCount": r["txnCount"] or 0,
                    "collectedAmount": round(collected, 2),
                    "processingFee": 0.0,
                    "netBankDeposit": round(collected, 2),
                }
            )
        return {"records": records}

    @classmethod
    def _gst(cls, *, limit: int, **scope) -> dict[str, Any]:
        rows = list(
            cls._scope_items(**scope)
            .values("tax_rate")
            .annotate(taxableAmount=Sum("line_total"))
            .order_by("tax_rate")
        )
        records = []
        used_line_tax = False
        for i, r in enumerate(rows, start=1):
            rate = _f(r["tax_rate"])
            taxable = _f(r["taxableAmount"])
            tax = round(taxable * rate / 100.0, 2) if rate else 0.0
            if tax:
                used_line_tax = True
            half = round(tax / 2.0, 2)
            records.append(
                {
                    "id": str(i),
                    "taxType": f"GST {rate:g}%" if rate else "Exempt / Zero rated",
                    "rate": rate,
                    "taxableAmount": round(taxable, 2),
                    "cgst": half,
                    "sgst": half,
                    "totalTax": tax,
                }
            )
        if not used_line_tax:
            agg = cls._scope_orders(**scope).aggregate(
                taxable=Sum("subtotal"), tax=Sum("tax_amount")
            )
            tax = _f(agg["tax"])
            taxable = _f(agg["taxable"])
            if tax or taxable:
                half = round(tax / 2.0, 2)
                records = [
                    {
                        "id": "1",
                        "taxType": "GST (order totals)",
                        "rate": 0,
                        "taxableAmount": round(taxable, 2),
                        "cgst": half,
                        "sgst": half,
                        "totalTax": round(tax, 2),
                    }
                ]
        return {"records": records[:limit]}

    @classmethod
    def _dashboard(cls, *, limit: int, **scope) -> dict[str, Any]:
        qs = cls._scope_orders(**scope)
        totals = qs.aggregate(
            bills=Count("id"),
            net=Sum("grand_total"),
            gross=Sum("subtotal"),
            service=Sum("service_charge"),
            tax=Sum("tax_amount"),
            discount=Sum("discount_amount"),
            dine=Sum("grand_total", filter=Q(order_type__in=DINE_TYPES)),
            takeaway=Sum("grand_total", filter=Q(order_type__in=TAKEAWAY_TYPES)),
            delivery=Sum("grand_total", filter=Q(order_type__in=DELIVERY_TYPES)),
        )
        bills = totals["bills"] or 0
        net = _f(totals["net"])
        gross = _f(totals["gross"]) + _f(totals["service"])
        dine = _f(totals["dine"])
        takeaway = _f(totals["takeaway"])
        delivery = _f(totals["delivery"])
        dine_pct = round((dine / net) * 100, 1) if net else 0.0
        avg_ticket = round(net / bills, 2) if bills else 0.0
        days = 1
        if scope.get("start_date") and scope.get("end_date"):
            days = max((scope["end_date"] - scope["start_date"]).days + 1, 1)

        prev_kpis = {"net": 0.0, "avgTicket": 0.0}
        if scope.get("start_date") and scope.get("end_date"):
            span = (scope["end_date"] - scope["start_date"]).days + 1
            prev_end = scope["start_date"] - timedelta(days=1)
            prev_start = prev_end - timedelta(days=span - 1)
            prev = cls._scope_orders(
                property_id=scope.get("property_id"),
                outlet_id=scope.get("outlet_id"),
                tenant_id=scope.get("tenant_id"),
                start_date=prev_start,
                end_date=prev_end,
            ).aggregate(bills=Count("id"), net=Sum("grand_total"))
            prev_net = _f(prev["net"])
            prev_bills = prev["bills"] or 0
            prev_kpis = {
                "net": prev_net,
                "avgTicket": round(prev_net / prev_bills, 2) if prev_bills else 0.0,
            }

        def delta_pct(current: float, previous: float) -> float:
            if not previous:
                return 0.0
            return round(((current - previous) / previous) * 100, 1)

        channels = [
            {"label": "Dine-In Restaurant", "amount": dine, "color": "teal"},
            {"label": "Room Service", "amount": 0.0, "color": "sky"},
            {"label": "Online / Delivery", "amount": delivery, "color": "purple"},
            {"label": "Direct Counter Takeaway", "amount": takeaway, "color": "amber"},
        ]
        room = _f(
            qs.filter(order_type="ROOM_SERVICE").aggregate(s=Sum("grand_total"))["s"]
        )
        dine_only = _f(
            qs.filter(order_type="DINE_IN").aggregate(s=Sum("grand_total"))["s"]
        )
        channels[0]["amount"] = dine_only
        channels[1]["amount"] = room
        for ch in channels:
            ch["pct"] = round((ch["amount"] / net) * 100, 1) if net else 0.0

        top = (
            cls._scope_items(**scope)
            .values("item_name", "category_name")
            .annotate(qty=Sum("quantity"), revenue=Sum("line_total"))
            .order_by("-revenue")[:4]
        )
        top_dishes = [
            {
                "name": r["item_name"],
                "category": r["category_name"] or "",
                "qty": _f(r["qty"]),
                "revenue": _f(r["revenue"]),
            }
            for r in top
        ]
        kpis = {
            "grossSales": round(gross, 2),
            "netSales": round(net, 2),
            "totalBills": bills,
            "avgTicket": avg_ticket,
            "dineInVolume": dine_pct,
            "billsPerDay": round(bills / days, 1) if days else bills,
            "grossDeltaPct": delta_pct(net, prev_kpis["net"]),
            "avgTicketDelta": round(avg_ticket - prev_kpis["avgTicket"], 2),
            "taxes": _f(totals["tax"]),
            "discounts": _f(totals["discount"]),
        }
        return {
            "records": [],
            "kpis": kpis,
            "channels": channels,
            "topDishes": top_dishes,
        }
