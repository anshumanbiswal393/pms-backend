"""
Part 4 — Folio bridge: post POS Room Charge onto PMS GuestFolio.

PMS remains source of truth for folio balance. POS only posts via FolioTransaction
using the same pattern as front_office night-audit auto-post.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.features.front_office.models import GuestFolio, FolioTransaction
from apps.features.reservations.models import Reservation
from apps.POS.models import POSOrder, FolioPostingLog


class FolioBridgeService:
    """Atomic, idempotent Room Charge posting into GuestFolio."""

    CHARGE_ROOM_SERVICE = "POS_ROOM_SERVICE"
    CHARGE_FNB = "POS_FNB"
    CHARGE_REVERSAL = "POS_REVERSAL"

    @classmethod
    def _charge_code_for_order(cls, order: POSOrder) -> str:
        if order.order_type == "ROOM_SERVICE":
            return cls.CHARGE_ROOM_SERVICE
        return cls.CHARGE_FNB

    @classmethod
    def _resolve_folio(
        cls,
        *,
        order: POSOrder,
        folio_id: str | UUID | None,
        reservation_id: str | UUID | None,
    ) -> tuple[GuestFolio, Reservation]:
        res_id = reservation_id or order.reservation_id
        fol_id = folio_id or order.folio_id

        reservation = None
        folio = None

        if fol_id:
            folio = (
                GuestFolio.objects.filter(id=fol_id, deleted_at__isnull=True)
                .select_related("reservation")
                .first()
            )
            if not folio:
                raise ValidationError({"folio_id": "Guest folio not found."})
            reservation = folio.reservation

        if res_id and not reservation:
            reservation = Reservation.objects.filter(
                id=res_id, deleted_at__isnull=True
            ).first()
            if not reservation:
                raise ValidationError({"reservation_id": "Reservation not found."})

        if reservation and not folio:
            folio = (
                GuestFolio.objects.filter(
                    reservation=reservation,
                    status="OPEN",
                    deleted_at__isnull=True,
                )
                .order_by("-created_at")
                .first()
            )
            if not folio:
                raise ValidationError(
                    {"folio_id": "No OPEN guest folio for this reservation."}
                )

        if not reservation or not folio:
            raise ValidationError(
                {
                    "detail": "reservation_id and/or folio_id required for ROOM_CHARGE.",
                }
            )

        if reservation.status != "CHECKED_IN":
            raise ValidationError(
                {
                    "reservation_id": (
                        f"Reservation must be CHECKED_IN (current={reservation.status})."
                    )
                }
            )
        if folio.status != "OPEN":
            raise ValidationError(
                {
                    "folio_id": (
                        f"Folio must be OPEN for charges (current={folio.status})."
                    )
                }
            )
        if folio.tenant_id != order.tenant_id:
            raise ValidationError(
                {"folio_id": "Folio tenant does not match POS order tenant."}
            )
        return folio, reservation

    @classmethod
    def _success_payload(
        cls,
        *,
        order: POSOrder,
        folio: GuestFolio,
        txn: FolioTransaction,
        log: FolioPostingLog,
    ) -> dict[str, Any]:
        return {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "status": order.status,
            "payment_mode": order.payment_mode,
            "folio_id": str(folio.id),
            "folio_number": folio.folio_number,
            "folio_transaction_id": str(txn.id),
            "folio_balance_after": str(folio.balance),
            "amount": str(log.amount),
            "charge_code": log.charge_code,
            "idempotency_key": log.idempotency_key,
            "posting_status": log.status,
        }

    @classmethod
    def post_room_charge(
        cls,
        order: POSOrder,
        *,
        folio_id: str | UUID | None = None,
        reservation_id: str | UUID | None = None,
        idempotency_key: str,
        amount: Decimal | None = None,
        user=None,
    ) -> dict[str, Any]:
        if not idempotency_key:
            raise ValidationError(
                {"idempotency_key": "idempotency_key is required for ROOM_CHARGE."}
            )
        return cls._post_room_charge_atomic(
            order,
            folio_id=folio_id,
            reservation_id=reservation_id,
            idempotency_key=idempotency_key,
            amount=amount,
            user=user,
        )

    @classmethod
    @transaction.atomic
    def _post_room_charge_atomic(
        cls,
        order: POSOrder,
        *,
        folio_id: str | UUID | None = None,
        reservation_id: str | UUID | None = None,
        idempotency_key: str,
        amount: Decimal | None = None,
        user=None,
    ) -> dict[str, Any]:
        existing = FolioPostingLog.objects.filter(
            idempotency_key=idempotency_key
        ).first()
        if existing and existing.status == "SUCCESS" and existing.folio_transaction_id:
            folio = GuestFolio.objects.filter(id=existing.folio_id).first()
            txn = FolioTransaction.objects.filter(
                id=existing.folio_transaction_id
            ).first()
            if folio and txn:
                # Refresh order from DB
                order.refresh_from_db()
                payload = cls._success_payload(
                    order=order, folio=folio, txn=txn, log=existing
                )
                payload["idempotent_replay"] = True
                return payload

        if existing and existing.status == "PENDING":
            raise ValidationError(
                {"idempotency_key": "A posting with this key is already in progress."}
            )

        folio, reservation = cls._resolve_folio(
            order=order, folio_id=folio_id, reservation_id=reservation_id
        )
        charge_amount = Decimal(str(amount if amount is not None else order.grand_total))
        if charge_amount <= 0:
            raise ValidationError({"amount": "Charge amount must be positive."})

        charge_code = cls._charge_code_for_order(order)
        outlet_name = order.outlet.name if order.outlet_id else "POS"
        description = (
            f"{'Room Service' if charge_code == cls.CHARGE_ROOM_SERVICE else 'F&B'} "
            f"{order.order_number} · Outlet {outlet_name}"
        )

        log = existing
        if not log:
            log = FolioPostingLog.objects.create(
                order=order,
                idempotency_key=idempotency_key,
                reservation_id=reservation.id,
                folio_id=folio.id,
                amount=charge_amount,
                charge_code=charge_code,
                status="PENDING",
                request_payload={
                    "order_id": str(order.id),
                    "folio_id": str(folio.id),
                    "reservation_id": str(reservation.id),
                    "amount": str(charge_amount),
                },
                created_by=user if getattr(user, "is_authenticated", False) else None,
            )
        else:
            # Retry of FAILED
            log.status = "PENDING"
            log.error_message = None
            log.reservation_id = reservation.id
            log.folio_id = folio.id
            log.amount = charge_amount
            log.charge_code = charge_code
            log.save()

        try:
            # Lock folio row
            folio = (
                GuestFolio.objects.select_for_update()
                .filter(pk=folio.pk)
                .first()
            )
            if not folio or folio.status != "OPEN":
                raise ValidationError({"folio_id": "Folio is no longer OPEN."})

            txn = FolioTransaction.objects.create(
                tenant_id=folio.tenant_id,
                folio=folio,
                transaction_type="CHARGE",
                charge_code=charge_code,
                amount=charge_amount,
                description=description,
                posted_at=timezone.now(),
            )
            current_tc = Decimal(str(folio.total_charges or 0))
            current_tp = Decimal(str(folio.total_payments or 0))
            folio.total_charges = current_tc + charge_amount
            folio.total_payments = current_tp
            folio.balance = folio.total_charges - folio.total_payments
            folio.save()

            log.status = "SUCCESS"
            log.folio_transaction_id = txn.id
            log.response_payload = {
                "folio_transaction_id": str(txn.id),
                "folio_balance_after": str(folio.balance),
            }
            log.save(
                update_fields=[
                    "status",
                    "folio_transaction_id",
                    "response_payload",
                    "updated_at",
                ]
            )

            order.folio_id = folio.id
            order.reservation_id = reservation.id
            order.save(update_fields=["folio_id", "reservation_id", "updated_at"])

            return cls._success_payload(order=order, folio=folio, txn=txn, log=log)
        except ValidationError:
            log.status = "FAILED"
            log.error_message = "Validation failed during folio post"
            log.save(update_fields=["status", "error_message", "updated_at"])
            raise
        except Exception as exc:
            log.status = "FAILED"
            log.error_message = str(exc)
            log.save(update_fields=["status", "error_message", "updated_at"])
            raise ValidationError({"folio": f"Failed to post room charge: {exc}"})
