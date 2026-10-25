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
        return rooms
