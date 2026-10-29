"""
Part 3 — POS Orders + KOT service (PostgreSQL, PMS-style).

Owns order lifecycle: create → KOT → advance stage → edit (delta KOT) → history.
Settle/Room Charge posting is Part 4 (folio_bridge).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import Max, Prefetch, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.POS.models import (
    Outlet,
    RestaurantTable,
    MenuItem,
    POSOrder,
    POSOrderItem,
    KOTTicket,
    KOTTicketItem,
    POSOrderStatusHistory,
    POSPayment,
)
from apps.POS.services.folio_bridge import FolioBridgeService

ORDER_TYPE_UI = {
    "DINE_IN": "Dine In",
    "TAKEAWAY": "Takeaway",
    "ROOM_SERVICE": "Room Service",
    "DELIVERY": "Delivery",
    "ONLINE": "Online",
}

STATUS_UI = {
    "PLACED": "placed",
    "PREPARED": "prepared",
    "SETTLED": "settled",
    "CANCELLED": "cancelled",
}

STAGE_LABEL = {
    "PLACED": "Placed (In Kitchen)",
    "PREPARED": "Prepared by Chef",
    "SETTLED": "Settled",
    "CANCELLED": "Cancelled",
}

PAYMENT_UI = {
    "CASH": "Cash",
    "CARD": "Card",
    "UPI": "UPI",
    "ROOM_CHARGE": "Add to Room Folio",
    "SPLIT": "Split",
    "DUE": "Due",
}


class OrderService:
    """Business logic for POS orders and KOT tickets."""

    OPEN_STATUSES = ("PLACED", "PREPARED")

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    @classmethod
    def serialize_item(cls, item: POSOrderItem) -> dict[str, Any]:
        diet = (item.item_type or "").lower()
        if diet == "non_veg":
            diet = "non_veg"
        elif diet == "veg":
            diet = "veg"
        elif diet == "egg":
            diet = "egg"
        return {
            "id": str(item.id),
            "menuItemId": str(item.menu_item_id) if item.menu_item_id else None,
            "code": item.item_code or "",
            "name": item.item_name,
            "category": item.category_name or "",
            "selectedVariantName": item.variant_name or None,
            "quantity": float(item.quantity),
            "price": float(item.unit_price),
            "lineTotal": float(item.line_total),
            "taxRate": float(item.tax_rate),
            "notes": item.notes or "",
            "diet": diet or None,
            "isVoid": item.is_void,
        }

    @classmethod
    def _truthy(cls, value: Any) -> bool:
        if value is False or value is None or value == 0 or value == "":
            return False
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes")
        return bool(value)

    @classmethod
    def _wants_kot(cls, data: dict[str, Any], *, default: bool = True) -> bool:
        # Prefer an explicit False from either camelCase or snake_case so HOLD
        # (sendKot: false) is not overwritten by serializer defaults.
        if data.get("sendKot") is False or data.get("send_kot") is False:
            return False
        if data.get("sendKot") is True or data.get("send_kot") is True:
            return True
        if "sendKot" in data:
            return cls._truthy(data.get("sendKot"))
        if "send_kot" in data:
            return cls._truthy(data.get("send_kot"))
        return default

    @classmethod
    def _wants_held(cls, data: dict[str, Any]) -> bool:
        if data.get("held") is False or data.get("isHeld") is False:
            return False
        if "held" in data:
            return cls._truthy(data.get("held"))
        if "isHeld" in data:
            return cls._truthy(data.get("isHeld"))
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        return cls._truthy(meta.get("held"))

    @classmethod
    def _apply_held_meta(cls, order: POSOrder, data: dict[str, Any]) -> None:
        meta = dict(order.meta or {})
        incoming = data.get("meta")
        if isinstance(incoming, dict):
            meta.update(incoming)
        if any(k in data for k in ("held", "isHeld")):
            if cls._wants_held(data):
                meta["held"] = True
            else:
                meta.pop("held", None)
                meta.pop("heldCart", None)
        if data.get("heldCart") is not None:
            meta["heldCart"] = data.get("heldCart")
        order.meta = meta

    @classmethod
    def _ensure_due_for_open_order(cls, order: POSOrder, *, user=None) -> None:
        if order.status == "SETTLED" or bool((order.meta or {}).get("held")):
            return
        from apps.POS.models import POSDueBill
        if POSDueBill.objects.filter(order=order, deleted_at__isnull=True).exists():
            return
        from apps.POS.services.dues import DueLedgerService
        try:
            DueLedgerService.create_for_order(order, paid_amount=Decimal("0.00"), user=user)
        except Exception:
            pass

    @classmethod
    def serialize_order(cls, order: POSOrder) -> dict[str, Any]:
        items = [cls.serialize_item(i) for i in order.items.all() if not i.is_void]
        items_summary = ", ".join(
            f"{i['name']}"
            + (f" ({i['selectedVariantName']})" if i.get("selectedVariantName") else "")
            + f" × {int(i['quantity']) if float(i['quantity']).is_integer() else i['quantity']}"
            for i in items
        )
        if order.order_note:
            items_summary = (
                f"{items_summary}, Note: {order.order_note}"
                if items_summary
                else f"Note: {order.order_note}"
            )

        placed = order.placed_at or order.created_at
        elapsed = 0
        if placed:
            elapsed = max(1, int((timezone.now() - placed).total_seconds() // 60))

        table_or_room = order.table_number or order.room_number or ""
        effective_type = cls._effective_order_type(order)
        source = ""
        if effective_type == "DINE_IN" and table_or_room:
            source = f"Table {table_or_room}"
            if order.section_name:
                source += f" ({order.section_name})"
        elif effective_type == "ROOM_SERVICE" and order.room_number:
            source = f"Room {order.room_number}"
        else:
            source = ORDER_TYPE_UI.get(effective_type, effective_type)

        return {
            "id": str(order.id),
            "orderNumber": order.order_number,
            "order_number": order.order_number,
            "type": effective_type.lower(),
            "orderType": effective_type,
            "typeLabel": ORDER_TYPE_UI.get(effective_type, effective_type),
            "status": order.status,
            "currentStage": STATUS_UI.get(order.status, order.status.lower()),
            "stageLabel": STAGE_LABEL.get(order.status, order.status),
            "source": source,
            "customerName": order.guest_name or "Walk-in Guest",
            "customerPhone": order.guest_phone or "--",
            "tableOrRoom": table_or_room,
            "tableId": str(order.table_id) if order.table_id else None,
            "tableNumber": order.table_number,
            "section": order.section_name,
            "roomNumber": order.room_number,
            "roomUnitId": str(order.room_unit_id) if order.room_unit_id else None,
            "reservationId": str(order.reservation_id) if order.reservation_id else None,
            "folioId": str(order.folio_id) if order.folio_id else None,
            "waiterName": order.waiter_name or "Captain",
            "pax": order.pax or 1,
            "orderNote": order.order_note or "",
            "itemsSummary": items_summary,
            "subtotal": float(order.subtotal),
            "taxAmount": float(order.tax_amount),
            "serviceCharge": float(order.service_charge),
            "discountAmount": float(order.discount_amount),
            "amount": float(order.grand_total),
            "grandTotal": float(order.grand_total),
            "paymentMode": PAYMENT_UI.get(order.payment_mode, order.payment_mode),
            "payment_mode": order.payment_mode,
            "placedAt": placed.isoformat() if placed else None,
            "preparedAt": order.prepared_at.isoformat() if order.prepared_at else None,
            "settledAt": order.settled_at.isoformat() if order.settled_at else None,
            "startTime": placed.strftime("%H:%M") if placed else "",
            "createdTimestamp": int(placed.timestamp() * 1000) if placed else 0,
            "elapsedMinutes": elapsed,
            "estDurationMinutes": 35,
            "outletId": str(order.outlet_id),
            "propertyId": str(order.property_id),
            "tenantId": str(order.tenant_id),
            "items": items,
            "held": bool((order.meta or {}).get("held")),
            "meta": order.meta or {},
            "kotTickets": [
                cls.serialize_kot(t) for t in order.kot_tickets.all()
            ],
        }

    KOT_STATUS_UI = {
        "PENDING": "Not Prepared",
        "PREPARING": "In Kitchen",
        "READY": "Prepared",
        "SERVED": "Served",
        "CANCELLED": "Cancelled",
    }

    @classmethod
    def _effective_order_type(cls, order: POSOrder) -> str:
        if order.room_number and order.order_type == "DINE_IN":
            return "ROOM_SERVICE"
        return order.order_type

    @classmethod
    def _kot_location_label(cls, order: POSOrder) -> str:
        loc = (order.table_number or order.room_number or "").strip()
        if not loc:
            return ""
        if cls._effective_order_type(order) == "ROOM_SERVICE" and not loc.lower().startswith("room"):
            return f"Room {loc}"
        return loc

    @classmethod
    def serialize_kot(cls, ticket: KOTTicket) -> dict[str, Any]:
        order = ticket.order
        items = [
            {
                "id": str(i.id),
                "name": i.item_name + (f" ({i.variant_name})" if i.variant_name else ""),
                "code": i.item_code or "",
                "variantName": i.variant_name,
                "quantity": float(i.quantity),
                "notes": i.notes or "",
                "isVoid": i.is_void,
            }
            for i in ticket.items.all()
        ]
        live_items = [i for i in items if not i.get("isVoid")]
        item_count = int(sum(i["quantity"] for i in live_items)) or len(live_items)
        items_text = ", ".join(
            f"{i['name']} × {int(i['quantity']) if float(i['quantity']).is_integer() else i['quantity']}"
            for i in live_items
        )
        sent = ticket.sent_at or ticket.created_at
        ready = ticket.ready_at
        return {
            "id": str(ticket.id),
            "kotId": ticket.sequence,
            "kotNumber": ticket.kot_number,
            "orderId": str(order.id),
            "orderNumber": order.order_number,
            "orderType": (
                f"{ORDER_TYPE_UI.get(cls._effective_order_type(order), order.order_type)}"
                + (
                    f" ({cls._kot_location_label(order)})"
                    if (order.table_number or order.room_number)
                    else ""
                )
            ),
            "status": ticket.status,
            "statusLabel": cls.KOT_STATUS_UI.get(ticket.status, ticket.status),
            "isModified": ticket.is_modified,
            "customerName": order.guest_name or "--",
            "customerPhone": order.guest_phone or "--",
            "tableOrRoom": order.table_number or order.room_number or "",
            "waiterName": order.waiter_name or "Captain",
            "notes": ticket.notes or order.order_note or "",
            "sentAt": sent.isoformat() if sent else None,
            "createdAt": sent.strftime("%d %b %Y %H:%M:%S").lstrip("0")
            if sent
            else "",
            "createdTimestamp": int(sent.timestamp() * 1000) if sent else 0,
            "readyTimestamp": int(ready.timestamp() * 1000) if ready else None,
            "itemCount": item_count,
            "itemsText": items_text,
            "items": live_items,
        }

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def order_queryset(cls):
        return (
            POSOrder.objects.filter(deleted_at__isnull=True)
            .select_related("outlet", "table", "property", "tenant")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=POSOrderItem.objects.filter(deleted_at__isnull=True).order_by(
                        "sort_order"
                    ),
                ),
                Prefetch(
                    "kot_tickets",
                    queryset=KOTTicket.objects.filter(deleted_at__isnull=True)
                    .prefetch_related("items")
                    .order_by("sequence"),
                ),
            )
        )

    @classmethod
    def _lock_order(cls, order_id) -> POSOrder | None:
        """Row-lock without nullable OUTER JOIN (Postgres FOR UPDATE rule)."""
        return (
            POSOrder.objects.select_for_update()
            .filter(pk=order_id, deleted_at__isnull=True)
            .first()
        )

    @classmethod
    def _next_order_number(cls, property_id) -> str:
        last = (
            POSOrder.objects.all_with_deleted()
            .filter(property_id=property_id, order_number__startswith="ORD-")
            .aggregate(m=Max("order_number"))
            .get("m")
        )
        seq = 10000
        if last:
            try:
                seq = int(str(last).split("-")[-1])
            except (TypeError, ValueError):
                seq = 10000
        return f"ORD-{seq + 1}"

    @classmethod
    def _normalize_payment_mode(cls, mode: str | None) -> str | None:
        if not mode:
            return None
        key = str(mode).strip().upper().replace(" ", "_")
        aliases = {
            "ROOMCHARGE": "ROOM_CHARGE",
            "ROOM_CHARGE": "ROOM_CHARGE",
        }
        key = aliases.get(key, key)
        valid = {c[0] for c in POSOrder.PAYMENT_MODE_CHOICES}
        if key not in valid:
            raise ValidationError({"payment_mode": f"Invalid payment mode: {mode}"})
        return key

    @classmethod
    def _normalize_order_type(cls, order_type: str | None) -> str:
        if not order_type:
            return "DINE_IN"
        key = str(order_type).strip().upper().replace(" ", "_")
        aliases = {
            "DINEIN": "DINE_IN",
            "DINE_IN": "DINE_IN",
            "ROOM": "ROOM_SERVICE",
            "ROOMSERVICE": "ROOM_SERVICE",
            "ROOM_SERVICE": "ROOM_SERVICE",
            "PICKUP": "TAKEAWAY",
            "PICK_UP": "TAKEAWAY",
        }
        key = aliases.get(key, key)
        valid = {c[0] for c in POSOrder.ORDER_TYPE_CHOICES}
        if key not in valid:
            raise ValidationError({"order_type": f"Invalid order type: {order_type}"})
        return key

    @classmethod
    def _build_lines(cls, items_data: list[dict], outlet: Outlet) -> list[dict]:
        if not items_data:
            raise ValidationError({"items": "At least one item is required."})
        lines = []
        for idx, raw in enumerate(items_data):
            qty = Decimal(str(raw.get("quantity") or 1))
            if qty <= 0:
                raise ValidationError({"items": "Quantity must be positive."})
            unit_price = Decimal(str(raw.get("price") or raw.get("unit_price") or 0))
            line_total = (qty * unit_price).quantize(Decimal("0.01"))
            menu_item = None
            menu_item_id = raw.get("menu_item_id") or raw.get("menuItemId") or raw.get("id")
            if menu_item_id:
                try:
                    UUID(str(menu_item_id))
                except (ValueError, TypeError, AttributeError):
                    menu_item_id = None
            if menu_item_id:
                menu_item = (
                    MenuItem.objects.filter(
                        id=menu_item_id, outlet=outlet, deleted_at__isnull=True
                    )
                    .select_related("category", "tax_profile", "outlet")
                    .first()
                )
            item_type = raw.get("item_type") or raw.get("diet") or ""
            if menu_item and not item_type:
                item_type = menu_item.item_type
            item_type = str(item_type).upper().replace("-", "_")
            if item_type in ("NONVEG", "NON_VEG"):
                item_type = "NON_VEG"
            elif item_type in ("VEG", "EGG"):
                pass
            else:
                item_type = item_type or None

            lines.append(
                {
                    "menu_item": menu_item,
                    "item_code": raw.get("code")
                    or raw.get("item_code")
                    or (menu_item.code if menu_item else None),
                    "item_name": raw.get("name")
                    or raw.get("item_name")
                    or (menu_item.name if menu_item else "Item"),
                    "category_name": raw.get("category")
                    or raw.get("category_name")
                    or (
                        menu_item.category.name
                        if menu_item and menu_item.category_id
                        else None
                    ),
                    "variant_name": raw.get("selectedVariantName")
                    or raw.get("variant_name"),
                    "item_type": item_type,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "tax_rate": Decimal(
                        str(
                            raw.get("tax_rate")
                            or raw.get("taxRate")
                            or (menu_item.tax_rate if menu_item else 0)
                            or 0
                        )
                    ),
                    "notes": raw.get("notes") or "",
                    "sort_order": idx,
                }
            )
        return lines

    @classmethod
    def _recompute_totals(
        cls,
        lines: list[dict],
        *,
        subtotal: Decimal | None = None,
        tax_amount: Decimal | None = None,
        service_charge: Decimal | None = None,
        discount_amount: Decimal | None = None,
        grand_total: Decimal | None = None,
    ) -> dict[str, Decimal]:
        computed_sub = sum((ln["line_total"] for ln in lines), Decimal("0.00"))
        sub = Decimal(str(subtotal)) if subtotal is not None else computed_sub
        tax = Decimal(str(tax_amount or 0))
        svc = Decimal(str(service_charge or 0))
        disc = Decimal(str(discount_amount or 0))
        if grand_total is not None:
            grand = Decimal(str(grand_total))
        else:
            grand = (sub + tax + svc - disc).quantize(Decimal("0.01"))
        return {
            "subtotal": sub.quantize(Decimal("0.01")),
            "tax_amount": tax.quantize(Decimal("0.01")),
            "service_charge": svc.quantize(Decimal("0.01")),
            "discount_amount": disc.quantize(Decimal("0.01")),
            "grand_total": grand.quantize(Decimal("0.01")),
        }

    @classmethod
    def _record_status(
        cls, order: POSOrder, from_status: str | None, to_status: str, note: str = "", user=None
    ):
        POSOrderStatusHistory.objects.create(
            order=order,
            from_status=from_status,
            to_status=to_status,
            note=note or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

    @classmethod
    def _create_kot(
        cls,
        order: POSOrder,
        lines: list[POSOrderItem],
        *,
        is_modified: bool = False,
        notes: str | None = None,
        user=None,
    ) -> KOTTicket:
        order.kot_sequence = (order.kot_sequence or 0) + 1
        order.save(update_fields=["kot_sequence", "updated_at"])
        seq = order.kot_sequence
        ticket = KOTTicket.objects.create(
            order=order,
            sequence=seq,
            kot_number=f"{order.order_number}-K{seq}",
            status="PREPARING",
            is_modified=is_modified,
            notes=notes or order.order_note,
            sent_at=timezone.now(),
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        for idx, line in enumerate(lines):
            if line.is_void:
                continue
            KOTTicketItem.objects.create(
                ticket=ticket,
                order_item=line,
                item_name=line.item_name,
                item_code=line.item_code,
                variant_name=line.variant_name,
                quantity=line.quantity,
                notes=line.notes,
                sort_order=idx,
            )
        return ticket

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @classmethod
    @transaction.atomic
    def create_order(cls, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        outlet_id = data.get("outlet_id") or data.get("outletId") or data.get("outlet")
        if not outlet_id:
            raise ValidationError({"outlet_id": "outlet_id is required."})
        outlet = Outlet.objects.filter(id=outlet_id, deleted_at__isnull=True).select_related(
            "tenant", "property"
        ).first()
        if not outlet:
            raise ValidationError({"outlet_id": "Outlet not found."})

        order_type = cls._normalize_order_type(data.get("order_type") or data.get("orderType"))
        room_number = data.get("room_number") or data.get("roomNumber")
        if room_number and order_type == "DINE_IN":
            order_type = "ROOM_SERVICE"
        items_data = data.get("items") or []
        lines = cls._build_lines(items_data, outlet)
        totals = cls._recompute_totals(
            lines,
            subtotal=data.get("subtotal"),
            tax_amount=data.get("tax_amount") or data.get("taxAmount"),
            service_charge=data.get("service_charge") or data.get("serviceCharge"),
            discount_amount=data.get("discount_amount") or data.get("discountAmount"),
            grand_total=data.get("grand_total") or data.get("grandTotal"),
        )

        table = None
        table_id = data.get("table_id") or data.get("tableId") or data.get("table")
        table_number = data.get("table_number") or data.get("tableNumber")
        section_name = data.get("section") or data.get("section_name")
        if table_id:
            table = RestaurantTable.objects.filter(
                id=table_id, deleted_at__isnull=True
            ).select_related("section").first()
            if table:
                table_number = table_number or table.table_number
                section_name = section_name or (
                    table.section.name if table.section_id else None
                )

        mark_settled = bool(data.get("mark_settled") or data.get("markSettled"))
        payment_mode = cls._normalize_payment_mode(
            data.get("payment_mode") or data.get("paymentMode")
        )
        held = cls._wants_held(data)
        meta = dict(data.get("meta") or {})
        if held:
            meta["held"] = True
        if data.get("heldCart") is not None:
            meta["heldCart"] = data.get("heldCart")
        now = timezone.now()
        status = "SETTLED" if mark_settled else "PLACED"

        order = POSOrder.objects.create(
            tenant_id=outlet.tenant_id,
            property_id=outlet.property_id,
            outlet=outlet,
            order_number=cls._next_order_number(outlet.property_id),
            order_type=order_type,
            status=status,
            table=table,
            table_number=table_number,
            section_name=section_name,
            room_unit_id=data.get("room_unit_id") or data.get("roomUnitId"),
            room_number=room_number,
            reservation_id=data.get("reservation_id") or data.get("reservationId"),
            folio_id=data.get("folio_id") or data.get("folioId"),
            guest_name=data.get("guest_name")
            or data.get("guestName")
            or data.get("customerName"),
            guest_phone=data.get("guest_phone")
            or data.get("guestPhone")
            or data.get("customerPhone"),
            waiter_name=data.get("waiter_name") or data.get("waiterName") or "Captain",
            pax=int(data.get("pax") or 1),
            order_note=data.get("order_note") or data.get("orderNote") or "",
            subtotal=totals["subtotal"],
            tax_amount=totals["tax_amount"],
            service_charge=totals["service_charge"],
            discount_amount=totals["discount_amount"],
            grand_total=totals["grand_total"],
            payment_mode=payment_mode,
            meta=meta,
            placed_at=now,
            prepared_at=now if status == "SETTLED" else None,
            settled_at=now if status == "SETTLED" else None,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

        created_lines = []
        for ln in lines:
            created_lines.append(
                POSOrderItem.objects.create(
                    order=order,
                    menu_item=ln["menu_item"],
                    item_code=ln["item_code"],
                    item_name=ln["item_name"],
                    category_name=ln["category_name"],
                    variant_name=ln["variant_name"],
                    item_type=ln["item_type"],
                    quantity=ln["quantity"],
                    unit_price=ln["unit_price"],
                    line_total=ln["line_total"],
                    tax_rate=ln["tax_rate"],
                    notes=ln["notes"],
                    sort_order=ln["sort_order"],
                )
            )

        cls._record_status(order, None, status, note="Order created", user=user)

        send_kot = cls._wants_kot(data, default=not held)
        ticket = None
        if send_kot and created_lines:
            ticket = cls._create_kot(
                order, created_lines, is_modified=False, notes=order.order_note, user=user
            )

        if table and status != "SETTLED":
            table.status = "OCCUPIED"
            table.active_order_id = order.id
            table.active_waiter_name = order.waiter_name
            table.save(
                update_fields=[
                    "status",
                    "active_order_id",
                    "active_waiter_name",
                    "updated_at",
                ]
            )

        if status != "SETTLED" and not held:
            from apps.POS.services.dues import DueLedgerService
            try:
                DueLedgerService.create_for_order(
                    order,
                    paid_amount=Decimal("0.00"),
                    user=user,
                )
            except Exception:
                pass

        order = cls.order_queryset().get(pk=order.pk)
        payload = cls.serialize_order(order)
        if ticket:
            payload["kotId"] = ticket.sequence
            payload["kotNumber"] = ticket.kot_number
        return payload

    @classmethod
    @transaction.atomic
    def mark_ticket_ready(cls, ticket_id, *, user=None) -> dict[str, Any]:
        ticket = (
            KOTTicket.objects.select_for_update()
            .select_related("order")
            .filter(pk=ticket_id, deleted_at__isnull=True)
            .first()
        )
        if not ticket:
            raise ValidationError({"ticket": "KOT not found."})
        # If order was deleted or cancelled, mark ticket CANCELLED and deleted cleanly
        if not ticket.order or ticket.order.deleted_at is not None or ticket.order.status == "CANCELLED":
            ticket.status = "CANCELLED"
            ticket.deleted_at = timezone.now()
            ticket.save(update_fields=["status", "deleted_at", "updated_at"])
            return cls.serialize_kot(ticket)

        if ticket.status in ("SERVED", "CANCELLED"):
            raise ValidationError(
                {"status": f"Cannot mark ready from status {ticket.status}."}
            )
        ticket.status = "READY"
        ticket.ready_at = timezone.now()
        ticket.save(update_fields=["status", "ready_at", "updated_at"])
        remaining = KOTTicket.objects.filter(
            order_id=ticket.order_id,
            deleted_at__isnull=True,
            status__in=("PENDING", "PREPARING"),
        )
        if not remaining.exists() and ticket.order and not ticket.order.deleted_at and ticket.order.status == "PLACED":
            try:
                cls.advance_stage(ticket.order_id, user=user)
            except Exception:
                pass
        ticket = (
            KOTTicket.objects.select_related("order")
            .prefetch_related("items")
            .get(pk=ticket.pk)
        )
        return cls.serialize_kot(ticket)

    @classmethod
    @transaction.atomic
    def mark_ticket_served(cls, ticket_id, *, user=None) -> dict[str, Any]:
        ticket = (
            KOTTicket.objects.select_for_update()
            .select_related("order")
            .filter(pk=ticket_id, deleted_at__isnull=True)
            .first()
        )
        if not ticket:
            raise ValidationError({"ticket": "KOT not found."})
        if not ticket.order or ticket.order.deleted_at is not None or ticket.order.status == "CANCELLED":
            ticket.status = "CANCELLED"
            ticket.deleted_at = timezone.now()
            ticket.save(update_fields=["status", "deleted_at", "updated_at"])
            return cls.serialize_kot(ticket)

        if ticket.status == "CANCELLED":
            raise ValidationError({"status": "Cannot serve a cancelled KOT."})
        ticket.status = "SERVED"
        if not ticket.ready_at:
            ticket.ready_at = timezone.now()
        ticket.save(update_fields=["status", "ready_at", "updated_at"])
        remaining_prep = KOTTicket.objects.filter(
            order_id=ticket.order_id,
            deleted_at__isnull=True,
            status__in=("PENDING", "PREPARING"),
        )
        if not remaining_prep.exists() and ticket.order and not ticket.order.deleted_at and ticket.order.status == "PLACED":
            try:
                cls.advance_stage(ticket.order_id, user=user)
            except Exception:
                pass
        ticket = (
            KOTTicket.objects.select_related("order")
            .prefetch_related("items")
            .get(pk=ticket.pk)
        )
        return cls.serialize_kot(ticket)

    @classmethod
    @transaction.atomic
    def send_kot(cls, order_id, *, notes: str | None = None, user=None) -> dict[str, Any]:
        order = cls._lock_order(order_id)
        if not order:
            raise ValidationError({"order": "Order not found."})
        if not order.is_open():
            raise ValidationError({"order": "Cannot send KOT for settled/cancelled order."})
        lines = list(
            POSOrderItem.objects.filter(
                order=order, is_void=False, deleted_at__isnull=True
            )
        )
        if not lines:
            raise ValidationError({"items": "No items to send to kitchen."})
        ticket = cls._create_kot(
            order, lines, is_modified=bool(order.kot_sequence), notes=notes, user=user
        )
        return cls.serialize_kot(ticket)

    @classmethod
    @transaction.atomic
    def advance_stage(cls, order_id, *, user=None) -> dict[str, Any]:
        order = cls._lock_order(order_id)
        if not order:
            raise ValidationError({"order": "Order not found."})
        if order.status == "PLACED":
            prev = order.status
            order.status = "PREPARED"
            order.prepared_at = timezone.now()
            order.save(update_fields=["status", "prepared_at", "updated_at"])
            cls._record_status(order, prev, "PREPARED", note="Advanced to prepared", user=user)
            KOTTicket.objects.filter(order=order, status="PREPARING").update(
                status="READY", ready_at=timezone.now()
            )
        elif order.status == "PREPARED":
            # Stay prepared — settle is Part 4
            pass
        else:
            raise ValidationError(
                {"status": f"Cannot advance from status {order.status}."}
            )
        order = cls.order_queryset().get(pk=order.pk)
        return cls.serialize_order(order)

    @classmethod
    @transaction.atomic
    def update_order_items(
        cls, order_id, data: dict[str, Any], *, user=None
    ) -> dict[str, Any]:
        order = cls._lock_order(order_id)
        if not order:
            raise ValidationError({"order": "Order not found."})
        if not order.is_open():
            raise ValidationError({"order": "Settled/cancelled orders are immutable."})

        cls._apply_held_meta(order, data)

        items_data = data.get("items")
        if items_data is None:
            # Metadata-only patch
            for field, key in (
                ("guest_name", ("guest_name", "guestName", "customerName")),
                ("guest_phone", ("guest_phone", "guestPhone", "customerPhone")),
                ("waiter_name", ("waiter_name", "waiterName")),
                ("order_note", ("order_note", "orderNote")),
            ):
                for k in key:
                    if k in data:
                        setattr(order, field, data[k])
                        break
            if "pax" in data:
                order.pax = int(data["pax"])
            order.save()
            cls._ensure_due_for_open_order(order, user=user)
            order = cls.order_queryset().get(pk=order.pk)
            return cls.serialize_order(order)

        lines = cls._build_lines(items_data, order.outlet)
        # Soft-void previous lines
        order.items.filter(deleted_at__isnull=True).update(
            is_void=True, deleted_at=timezone.now()
        )
        created_lines = []
        for ln in lines:
            created_lines.append(
                POSOrderItem.objects.create(
                    order=order,
                    menu_item=ln["menu_item"],
                    item_code=ln["item_code"],
                    item_name=ln["item_name"],
                    category_name=ln["category_name"],
                    variant_name=ln["variant_name"],
                    item_type=ln["item_type"],
                    quantity=ln["quantity"],
                    unit_price=ln["unit_price"],
                    line_total=ln["line_total"],
                    tax_rate=ln["tax_rate"],
                    notes=ln["notes"],
                    sort_order=ln["sort_order"],
                )
            )
        totals = cls._recompute_totals(
            lines,
            subtotal=data.get("subtotal"),
            tax_amount=data.get("tax_amount") or data.get("taxAmount"),
            service_charge=data.get("service_charge") or data.get("serviceCharge"),
            discount_amount=data.get("discount_amount") or data.get("discountAmount"),
            grand_total=data.get("grand_total") or data.get("grandTotal"),
        )
        order.subtotal = totals["subtotal"]
        order.tax_amount = totals["tax_amount"]
        order.service_charge = totals["service_charge"]
        order.discount_amount = totals["discount_amount"]
        order.grand_total = totals["grand_total"]
        if "order_note" in data or "orderNote" in data:
            order.order_note = data.get("order_note") or data.get("orderNote") or ""
        order.save()

        # Modified KOT with delta lines (full replacement snapshot for kitchen)
        held = bool((order.meta or {}).get("held"))
        ticket = None
        if cls._wants_kot(data, default=not held) and created_lines:
            ticket = cls._create_kot(
                order,
                created_lines,
                is_modified=True,
                notes=order.order_note,
                user=user,
            )
            # Open orders go back to PLACED when items change
            if order.status == "PREPARED":
                prev = order.status
                order.status = "PLACED"
                order.prepared_at = None
                order.save(update_fields=["status", "prepared_at", "updated_at"])
                cls._record_status(
                    order, prev, "PLACED", note="Items edited — back to kitchen", user=user
                )

        # Sync due bill total
        from apps.POS.models import POSDueBill
        due_bill = POSDueBill.objects.filter(order=order, deleted_at__isnull=True).first()
        if due_bill:
            due_bill.total_amount = Decimal(str(order.grand_total))
            due_bill.due_amount = max(Decimal("0.00"), due_bill.total_amount - Decimal(str(due_bill.paid_amount)))
            due_bill.recompute_status()
            due_bill.save(update_fields=["total_amount", "due_amount", "status", "updated_at"])
        else:
            cls._ensure_due_for_open_order(order, user=user)

        order = cls.order_queryset().get(pk=order.pk)
        payload = cls.serialize_order(order)
        if ticket:
            payload["kotId"] = ticket.sequence
            payload["kotNumber"] = ticket.kot_number
        return payload

    @classmethod
    @transaction.atomic
    def cancel_order(cls, order_id, *, note: str = "", user=None) -> dict[str, Any]:
        order = cls._lock_order(order_id)
        if not order:
            raise ValidationError({"order": "Order not found."})
        if order.status == "SETTLED":
            raise ValidationError({"order": "Cannot cancel a settled order."})
        prev = order.status
        order.status = "CANCELLED"
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_at", "updated_at"])
        cls._record_status(order, prev, "CANCELLED", note=note or "Cancelled", user=user)
        KOTTicket.objects.filter(
            order=order, status__in=("PENDING", "PREPARING")
        ).update(status="CANCELLED")
        from apps.POS.models import POSDueBill
        POSDueBill.objects.filter(order=order).update(status="SETTLED", deleted_at=timezone.now())
        if order.table_id:
            RestaurantTable.objects.filter(
                id=order.table_id, active_order_id=order.id
            ).update(
                status="VACANT",
                active_order_id=None,
                active_waiter_name=None,
            )
        order = cls.order_queryset().get(pk=order.pk)
        from apps.POS.services.stock import StockService
        settings = StockService.get_inventory_settings(order.outlet_id)
        if str(settings.get("reverseConsumptionCancelled", "Yes")).lower() in ("yes", "true", "1"):
            StockService.reverse_for_order(order, user=user)
        return cls.serialize_order(order)

    @classmethod
    def list_current(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> list[dict[str, Any]]:
        # Open checks, plus billed/folio orders that the kitchen is still cooking.
        qs = cls.order_queryset().filter(
            Q(status__in=cls.OPEN_STATUSES)
            | Q(
                status="SETTLED",
                kot_tickets__deleted_at__isnull=True,
                kot_tickets__status__in=("PENDING", "PREPARING"),
            )
        ).distinct()
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        rows = []
        for o in qs.order_by("placed_at"):
            data = cls.serialize_order(o)
            has_open_kot = any(
                t.status in ("PENDING", "PREPARING") for t in o.kot_tickets.all()
            )
            if o.status == "SETTLED" and has_open_kot:
                data["currentStage"] = "placed"
                data["stageLabel"] = "Placed (In Kitchen)"
            rows.append(data)
        return rows

    @classmethod
    def list_history(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        qs = cls.order_queryset().filter(
            status__in=("SETTLED", "CANCELLED", "PREPARED", "PLACED")
        )
        # History UI typically wants settled + cancelled; include all non-deleted with filter
        if status:
            qs = qs.filter(status=status.upper())
        else:
            qs = qs.filter(status__in=("SETTLED", "CANCELLED"))
        if property_id:
            qs = qs.filter(property_id=property_id)
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if search:
            qs = qs.filter(
                Q(order_number__icontains=search)
                | Q(guest_name__icontains=search)
                | Q(table_number__icontains=search)
                | Q(room_number__icontains=search)
            )
        qs = qs.order_by("-settled_at", "-placed_at")[:limit]
        orders = [cls.serialize_order(o) for o in qs]
        grand = sum(Decimal(str(o["grandTotal"])) for o in orders)
        records = []
        for o in orders:
            placed = o.get("placedAt")
            created_at = ""
            if o.get("settledAt"):
                created_at = o["settledAt"]
            elif placed:
                created_at = placed
            history_status = {
                "SETTLED": "Settled",
                "CANCELLED": "Cancelled",
                "PREPARED": "Printed",
                "PLACED": "Running",
            }.get(o.get("status"), o.get("status") or "Settled")
            records.append(
                {
                    **o,
                    "orderNo": (o.get("orderNumber") or "").replace("ORD-", ""),
                    "orderTypeDisplay": o.get("source") or o.get("typeLabel") or "",
                    "assignTo": o.get("waiterName") or "Captain",
                    "myAmount": o.get("subtotal") or 0,
                    "status": history_status,
                    "createdAt": created_at,
                }
            )
        return {
            "success": True,
            "count": len(orders),
            "totalCount": len(orders),
            "grandTotal": float(grand),
            "salesTrend": [],
            "orders": orders,
            "records": records,
        }

    @classmethod
    def live_summary(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        tenant_id=None,
    ) -> dict[str, Any]:
        current = [
            o
            for o in cls.list_current(
                property_id=property_id, outlet_id=outlet_id, tenant_id=tenant_id
            )
            if not o.get("held")
        ]
        dine_in = [o for o in current if o["orderType"] == "DINE_IN"]
        takeaway = [o for o in current if o["orderType"] == "TAKEAWAY"]
        delivery = [o for o in current if o["orderType"] == "DELIVERY"]
        placed = [o for o in current if o.get("currentStage") == "placed"]
        prepared = [o for o in current if o.get("currentStage") == "prepared"]

        def _sum(rows):
            return float(sum(Decimal(str(r["grandTotal"])) for r in rows))

        running_tables = []
        for o in dine_in:
            running_tables.append(
                {
                    "id": o.get("tableId") or o["id"],
                    "tableNumber": o.get("tableNumber") or o.get("tableOrRoom") or "",
                    "section": o.get("section") or "",
                    "capacity": o.get("pax") or 4,
                    "occupancy": o.get("pax") or 1,
                    "orderNumber": o["orderNumber"],
                    "amount": o["grandTotal"],
                    "elapsedMinutes": o["elapsedMinutes"],
                    "status": "running" if o["status"] == "PLACED" else "billed",
                }
            )

        return {
            "runningOrders": {
                "totalOrders": len(current),
                "totalAmount": _sum(current),
                "dineIn": {"count": len(dine_in), "amount": _sum(dine_in)},
                "pickUp": {"count": len(takeaway), "amount": _sum(takeaway)},
                "delivery": {"count": len(delivery), "amount": _sum(delivery)},
            },
            "pendingOrders": {
                "totalOrders": len(placed) + len(prepared),
                "totalAmount": _sum(placed) + _sum(prepared),
                "inPreparation": {"count": len(placed), "amount": _sum(placed)},
                "waitingForPickup": {"count": len(prepared), "amount": _sum(prepared)},
                "outForDelivery": {"count": 0, "amount": 0.0},
            },
            "runningTables": running_tables,
            "currentOrders": current,
        }

    @classmethod
    def list_kot(
        cls,
        *,
        property_id=None,
        outlet_id=None,
        status: str | None = None,
    ) -> dict[str, Any]:
        # Clean up tickets for deleted/cancelled orders. Settled/folio bills stay
        # on the kitchen display until the chef taps Ready — food still has to cook.
        KOTTicket.objects.filter(
            deleted_at__isnull=True,
            order__deleted_at__isnull=False,
        ).update(status="CANCELLED", deleted_at=timezone.now())
        KOTTicket.objects.filter(
            deleted_at__isnull=True,
            order__status="CANCELLED",
            status__in=("PENDING", "PREPARING"),
        ).update(status="CANCELLED")

        qs = (
            KOTTicket.objects.filter(
                deleted_at__isnull=True,
                order__deleted_at__isnull=True,
            )
            .exclude(order__status="CANCELLED")
            .select_related("order")
            .prefetch_related("items")
            .order_by("sent_at")
        )
        if property_id:
            qs = qs.filter(order__property_id=property_id)
        if outlet_id:
            qs = qs.filter(order__outlet_id=outlet_id)
        if status:
            qs = qs.filter(status=status.upper())
        else:
            # Kitchen display is the live cook queue only — Ready leaves KOT.
            qs = qs.filter(status__in=("PENDING", "PREPARING"))
        tickets = [cls.serialize_kot(t) for t in qs]
        return {
            "success": True,
            "count": len(tickets),
            "totalCount": len(tickets),
            "kots": tickets,
            "records": tickets,
        }

    @classmethod
    def _release_table(cls, order: POSOrder):
        if not order.table_id:
            return
        RestaurantTable.objects.filter(
            id=order.table_id, active_order_id=order.id
        ).update(
            status="VACANT",
            active_order_id=None,
            active_waiter_name=None,
        )

    @classmethod
    def settle_order(cls, order_id, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        """
        Settle an open order with CASH/CARD/UPI/ROOM_CHARGE/SPLIT/DUE.

        ROOM_CHARGE posts to PMS GuestFolio via FolioBridgeService (idempotent).
        Stock BOM deduction runs after the settle transaction commits/savepoints
        so a stock DB blip cannot poison payment posting.
        """
        payload = cls._settle_order_tx(order_id, data, user=user)
        order_pk = payload.get("id")
        if not order_pk or payload.get("status") != "SETTLED":
            return payload

        from django.db import connection as db_connection
        from django.db.utils import OperationalError

        from apps.POS.services.stock import StockService

        try:
            order = POSOrder.objects.get(pk=order_pk)
            stock_result = StockService.deduct_for_order(order, user=user)
            payload["stockDeduction"] = stock_result
        except OperationalError:
            try:
                db_connection.close()
                order = POSOrder.objects.get(pk=order_pk)
                stock_result = StockService.deduct_for_order(order, user=user)
                payload["stockDeduction"] = stock_result
            except Exception as exc:
                payload["stockDeduction"] = {
                    "deducted": False,
                    "error": str(exc),
                }
        except Exception as exc:
            payload["stockDeduction"] = {
                "deducted": False,
                "error": str(exc),
            }
        return payload

    @classmethod
    @transaction.atomic
    def _settle_order_tx(cls, order_id, data: dict[str, Any], *, user=None) -> dict[str, Any]:
        order = cls._lock_order(order_id)
        if not order:
            raise ValidationError({"order": "Order not found."})

        payment_mode = cls._normalize_payment_mode(
            data.get("payment_mode") or data.get("paymentMode")
        )
        if not payment_mode:
            raise ValidationError({"payment_mode": "payment_mode is required."})

        idempotency_key = (
            data.get("idempotency_key")
            or data.get("idempotencyKey")
            or ""
        ).strip()

        # Idempotent settle: if already settled and same key replay for room charge
        if order.status == "SETTLED":
            if payment_mode == "ROOM_CHARGE" and idempotency_key:
                result = FolioBridgeService.post_room_charge(
                    order,
                    folio_id=data.get("folio_id") or data.get("folioId"),
                    reservation_id=data.get("reservation_id")
                    or data.get("reservationId"),
                    idempotency_key=idempotency_key,
                    user=user,
                )
                order = cls.order_queryset().get(pk=order.pk)
                payload = cls.serialize_order(order)
                payload.update(result)
                return payload
            raise ValidationError({"order": "Order is already settled."})

        if order.status == "CANCELLED":
            raise ValidationError({"order": "Cannot settle a cancelled order."})

        tendered = data.get("tendered_amount") or data.get("tenderedAmount")
        settle_amount = (
            Decimal(str(tendered))
            if tendered is not None
            else Decimal(str(order.grand_total))
        )

        folio_result = None
        payments_input = data.get("payments")  # optional split legs

        if payment_mode == "ROOM_CHARGE":
            if not idempotency_key:
                raise ValidationError(
                    {
                        "idempotency_key": (
                            "idempotency_key is required for ROOM_CHARGE settles."
                        )
                    }
                )
            folio_result = FolioBridgeService.post_room_charge(
                order,
                folio_id=data.get("folio_id") or data.get("folioId"),
                reservation_id=data.get("reservation_id")
                or data.get("reservationId"),
                idempotency_key=idempotency_key,
                amount=settle_amount,
                user=user,
            )
            POSPayment.objects.create(
                order=order,
                mode="ROOM_CHARGE",
                amount=settle_amount,
                status="CAPTURED",
                reference=idempotency_key,
                folio_id=folio_result.get("folio_id"),
                folio_transaction_id=folio_result.get("folio_transaction_id"),
                meta={"idempotency_key": idempotency_key},
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
        elif payment_mode == "SPLIT" and isinstance(payments_input, list) and payments_input:
            total = Decimal("0.00")
            for leg in payments_input:
                mode = cls._normalize_payment_mode(
                    leg.get("mode") or leg.get("payment_mode") or leg.get("paymentMode")
                )
                amt = Decimal(str(leg.get("amount") or 0))
                if not mode or amt <= 0:
                    raise ValidationError(
                        {"payments": "Each split leg needs mode and positive amount."}
                    )
                if mode == "ROOM_CHARGE":
                    raise ValidationError(
                        {
                            "payments": (
                                "ROOM_CHARGE in SPLIT is not supported here; "
                                "settle remaining with ROOM_CHARGE separately."
                            )
                        }
                    )
                POSPayment.objects.create(
                    order=order,
                    mode=mode,
                    amount=amt,
                    status="CAPTURED",
                    reference=leg.get("reference"),
                    created_by=user
                    if getattr(user, "is_authenticated", False)
                    else None,
                )
                total += amt
            settle_amount = total
        elif payment_mode == "DUE":
            paid_now = settle_amount
            # Explicit DUE with optional partial tender
            if tendered is None:
                paid_now = Decimal("0.00")
            POSPayment.objects.create(
                order=order,
                mode="DUE",
                amount=Decimal(str(order.grand_total)),
                status="CAPTURED",
                reference=data.get("reference") or "DUE",
                meta={"paid_at_settle": str(paid_now)},
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
            if paid_now > 0:
                POSPayment.objects.create(
                    order=order,
                    mode=cls._normalize_payment_mode(
                        data.get("partial_mode") or data.get("partialMode") or "CASH"
                    )
                    or "CASH",
                    amount=paid_now,
                    status="CAPTURED",
                    reference="partial-at-due",
                    created_by=user
                    if getattr(user, "is_authenticated", False)
                    else None,
                )
            settle_amount = paid_now
        else:
            POSPayment.objects.create(
                order=order,
                mode=payment_mode,
                amount=settle_amount,
                status="CAPTURED",
                reference=data.get("reference") or idempotency_key or None,
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )

        prev = order.status
        now = timezone.now()
        order.status = "SETTLED"
        order.payment_mode = payment_mode
        order.settled_at = now
        if order.prepared_at is None:
            order.prepared_at = now
        order.save(
            update_fields=[
                "status",
                "payment_mode",
                "settled_at",
                "prepared_at",
                "updated_at",
            ]
        )
        cls._record_status(
            order,
            prev,
            "SETTLED",
            note=f"Settled via {payment_mode}",
            user=user,
        )
        # Already-ready tickets leave the board; uncooked tickets stay on KOT.
        KOTTicket.objects.filter(order=order, status="READY").update(
            status="SERVED", ready_at=now
        )
        cls._release_table(order)

        # Part 5 — open due ledger when DUE or underpaid; close dues on full pay
        due_payload = None
        grand = Decimal(str(order.grand_total))
        settled_mode = payment_mode
        if settled_mode == "DUE":
            paid_for_due = settle_amount if tendered is not None else Decimal("0.00")
        else:
            paid_for_due = settle_amount

        from apps.POS.services.dues import DueLedgerService

        if settled_mode == "DUE" or (
            settled_mode in ("CASH", "CARD", "UPI", "SPLIT") and paid_for_due < grand
        ):
            if settled_mode != "DUE" and paid_for_due < grand:
                order.payment_mode = "DUE"
                order.save(update_fields=["payment_mode", "updated_at"])
            bill = DueLedgerService.create_for_order(
                order,
                paid_amount=paid_for_due,
                user=user,
            )
            due_payload = DueLedgerService.serialize_due(bill)
        else:
            DueLedgerService.close_for_order(order, mode=settled_mode, user=user)

        order = cls.order_queryset().get(pk=order.pk)
        payload = cls.serialize_order(order)
        if folio_result:
            payload.update(
                {
                    "folio_id": folio_result.get("folio_id"),
                    "folio_number": folio_result.get("folio_number"),
                    "folio_transaction_id": folio_result.get("folio_transaction_id"),
                    "folio_balance_after": folio_result.get("folio_balance_after"),
                    "idempotency_key": folio_result.get("idempotency_key"),
                    "idempotent_replay": folio_result.get("idempotent_replay", False),
                }
            )
        if due_payload:
            payload["dueBill"] = due_payload
        return payload
