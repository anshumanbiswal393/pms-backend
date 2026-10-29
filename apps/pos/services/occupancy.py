"""
Read-only bridge: in-house (CHECKED_IN) rooms for POS Room Service / billing.

PMS remains source of truth for stay + folio. POS must not invent occupancy state.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db.models import Prefetch

from apps.features.crm.models import GuestContact
from apps.features.front_office.models import GuestFolio
from apps.features.reservations.models import Reservation, ReservationInventory


class OccupancyService:
    """Lists occupied hotel rooms suitable for POS room charge / room service."""

    @classmethod
    def list_occupied_rooms(
        cls,
        *,
        property_id: str | UUID | None = None,
        tenant_id: str | UUID | None = None,
    ) -> list[dict[str, Any]]:
        if not property_id and not tenant_id:
            return []

        alloc_qs = (
            ReservationInventory.objects.filter(
                deleted_at__isnull=True,
                status="CHECKED_IN",
                inventory_unit__isnull=False,
            )
            .select_related(
                "inventory_unit",
                "inventory_unit_type",
            )
            .order_by("inventory_unit__name")
        )

        reservations = (
            Reservation.objects.filter(
                deleted_at__isnull=True,
                status="CHECKED_IN",
            )
            .select_related("primary_guest", "property", "tenant")
            .prefetch_related(
                Prefetch("room_allocations", queryset=alloc_qs),
                Prefetch(
                    "folios",
                    queryset=GuestFolio.objects.filter(
                        deleted_at__isnull=True,
                        status="OPEN",
                    ).order_by("-created_at"),
                ),
                Prefetch(
                    "primary_guest__contacts",
                    queryset=GuestContact.objects.filter(is_primary=True).order_by(
                        "-is_primary"
                    ),
                ),
            )
        )

        if property_id:
            reservations = reservations.filter(property_id=property_id)
        if tenant_id:
            reservations = reservations.filter(tenant_id=tenant_id)

        rooms: list[dict[str, Any]] = []
        for reservation in reservations:
            guest = reservation.primary_guest
            guest_name = ""
            if guest:
                guest_name = f"{guest.first_name or ''} {guest.last_name or ''}".strip()

            guest_phone = "--"
            if guest:
                contact = next(iter(guest.contacts.all()), None)
                if contact and contact.phone:
                    guest_phone = contact.phone

            open_folio = next(iter(reservation.folios.all()), None)
            is_open_for_charges = bool(open_folio and open_folio.status == "OPEN")

            checked_in_allocs = [
                a
                for a in reservation.room_allocations.all()
                if a.status == "CHECKED_IN" and a.inventory_unit_id
            ]

            if not checked_in_allocs:
                # Reservation checked in but room not assigned yet — skip for POS room picker
                continue

            for alloc in checked_in_allocs:
                unit = alloc.inventory_unit
                pax = (
                    (alloc.adult_count or 0)
                    + (alloc.child_count or 0)
                    + (alloc.infant_count or 0)
                )
                rooms.append(
                    {
                        "room_number": unit.name if unit else "",
                        "unit_id": str(unit.id) if unit else None,
                        "unit_type": (
                            alloc.inventory_unit_type.name
                            if alloc.inventory_unit_type
                            else None
                        ),
                        "floor": unit.floor if unit else None,
                        "reservation_id": str(reservation.id),
                        "confirmation_number": reservation.confirmation_number,
                        "allocation_id": str(alloc.id),
                        "guest_name": guest_name or "Walk-in Guest",
                        "guest_phone": guest_phone,
                        "guest_id": str(guest.id) if guest else None,
                        "pax": pax or 1,
                        "adult_count": alloc.adult_count or 0,
                        "child_count": alloc.child_count or 0,
                        "arrival_date": (
                            str(reservation.arrival_date)
                            if reservation.arrival_date
                            else None
                        ),
                        "departure_date": (
                            str(reservation.departure_date)
                            if reservation.departure_date
                            else None
                        ),
                        "folio_id": str(open_folio.id) if open_folio else None,
                        "folio_number": open_folio.folio_number if open_folio else None,
                        "folio_status": open_folio.status if open_folio else None,
                        "balance": (
                            str(open_folio.balance)
                            if open_folio
                            else str(Decimal("0.00"))
                        ),
                        "is_open_for_charges": is_open_for_charges,
                        "property_id": str(reservation.property_id),
                        "tenant_id": str(reservation.tenant_id),
                    }
                )

        rooms.sort(key=lambda r: (r.get("room_number") or "", r.get("confirmation_number") or ""))
        cls._attach_pos_orders(rooms, property_id=property_id)
        return rooms

    @classmethod
    def _attach_pos_orders(cls, rooms: list[dict[str, Any]], *, property_id=None) -> None:
        """Attach POS F&B orders (KOT / folio) so Room View can show order-price."""
        for room in rooms:
            room.setdefault("pos_orders", [])
            room.setdefault("pos_charge_total", 0.0)
        if not rooms:
            return

        try:
            from django.db.models import Q

            from apps.POS.models import POSOrder
        except Exception:
            return

        def _room_key(value: str | None) -> str:
            return str(value or "").replace("Room ", "").replace("ROOM ", "").strip()

        res_ids = [r["reservation_id"] for r in rooms if r.get("reservation_id")]
        room_numbers = [_room_key(r.get("room_number")) for r in rooms if r.get("room_number")]
        room_numbers = [n for n in room_numbers if n]
        if not res_ids and not room_numbers:
            return

        lookup = Q()
        if res_ids:
            lookup |= Q(reservation_id__in=res_ids)
        if room_numbers:
            lookup |= Q(room_number__in=room_numbers)

        pos_qs = (
            POSOrder.objects.filter(
                deleted_at__isnull=True,
                status__in=("PLACED", "PREPARED", "SETTLED"),
            )
            .filter(lookup)
            .prefetch_related("items")
            .order_by("-placed_at", "-created_at")
        )
        if property_id:
            pos_qs = pos_qs.filter(property_id=property_id)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for order in pos_qs:
            items = [
                {
                    "name": i.item_name + (f" ({i.variant_name})" if i.variant_name else ""),
                    "quantity": float(i.quantity),
                    "unitPrice": float(i.unit_price),
                }
                for i in order.items.all()
                if not i.is_void
            ]
            summary = ", ".join(
                f"{it['name']} × {int(it['quantity']) if float(it['quantity']).is_integer() else it['quantity']}"
                for it in items
            )
            placed = order.placed_at or order.created_at
            payload = {
                "id": str(order.id),
                "orderNumber": order.order_number,
                "totalAmount": float(order.grand_total),
                "itemsSummary": summary,
                "items": items,
                "createdAt": placed.strftime("%d %b %Y %H:%M") if placed else "",
                "paymentMode": (
                    "Add to Room Folio"
                    if order.payment_mode == "ROOM_CHARGE"
                    else (order.payment_mode or "")
                ),
                "status": order.status,
            }
            keys = []
            if order.reservation_id:
                keys.append(f"res:{order.reservation_id}")
            rn = _room_key(order.room_number)
            if rn:
                keys.append(f"room:{rn}")
            for key in keys:
                grouped.setdefault(key, []).append(payload)

        for room in rooms:
            room_key = f"room:{_room_key(room.get('room_number'))}"
            res_key = f"res:{room.get('reservation_id')}" if room.get("reservation_id") else None
            seen: set[str] = set()
            attached: list[dict[str, Any]] = []
            for key in (res_key, room_key):
                if not key:
                    continue
                for row in grouped.get(key, []):
                    if row["id"] in seen:
                        continue
                    seen.add(row["id"])
                    attached.append(row)
            room["pos_orders"] = attached
            room["pos_charge_total"] = float(sum(o["totalAmount"] for o in attached))
