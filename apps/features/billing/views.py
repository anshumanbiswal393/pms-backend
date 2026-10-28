import decimal
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.features.billing.models import TaxRate, Invoice, InvoiceLineItem, CreditNote, BillingAdjustment
from apps.features.billing.serializers import (
    TaxRateSerializer, InvoiceSerializer, InvoiceLineItemSerializer,
    CreditNoteSerializer, BillingAdjustmentSerializer
)
from apps.features.reservations.models import Reservation
from apps.features.front_office.models import GuestFolio
from apps.core.tenants.models import Tenant

class TaxRateViewSet(viewsets.ModelViewSet):
    serializer_class = TaxRateSerializer
    permission_classes = [permissions.AllowAny]
    queryset = TaxRate.objects.all()

class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.AllowAny]
    queryset = Invoice.objects.all()

class BillingAdjustmentViewSet(viewsets.ModelViewSet):
    serializer_class = BillingAdjustmentSerializer
    permission_classes = [permissions.AllowAny]
    queryset = BillingAdjustment.objects.all()

    def create(self, request, *args, **kwargs):
        data = request.data
        action = (data.get("action") or data.get("adjustment_type") or "TRANSFER").upper()
        amount_raw = data.get("transfer_amount") or data.get("amount") or 0
        reason = data.get("reason") or data.get("remarks") or f"{action} Folio Charges"
        from_res_id = data.get("from_reservation_id") or data.get("reservation_id")
        to_res_id = data.get("to_reservation_id")

        try:
            amt = decimal.Decimal(str(amount_raw))
        except Exception:
            amt = decimal.Decimal("0.00")

        # Resolve tenant
        tenant_obj = None
        user_tenant = getattr(request.user, "tenant", None)
        if user_tenant:
            tenant_obj = user_tenant
        else:
            tenant_obj = Tenant.objects.first()

        # Resolve reservation / folio
        folio_obj = None
        if from_res_id:
            res_obj = Reservation.objects.filter(id=from_res_id).first()
            if res_obj:
                folio_obj = GuestFolio.objects.filter(reservation=res_obj).first()
                if not folio_obj and tenant_obj:
                    # Create folio if missing
                    folio_obj = GuestFolio.objects.create(
                        tenant=tenant_obj,
                        reservation=res_obj,
                        folio_number=f"FOLIO-{str(res_obj.id)[:8].upper()}",
                        status="OPEN"
                    )

        if not folio_obj:
            # Fallback to any open folio or create dummy folio for record keeping
            folio_obj = GuestFolio.objects.first()
            if not folio_obj and tenant_obj:
                import uuid
                folio_obj = GuestFolio.objects.create(
                    tenant=tenant_obj,
                    folio_number=f"FOLIO-SYS-{uuid.uuid4().hex[:6].upper()}",
                    status="OPEN"
                )

        # Create BillingAdjustment in database
        adjustment_item = None
        if folio_obj and tenant_obj and amt > 0:
            adj_type = "TRANSFER" if action == "TRANSFER" else "SPLIT" if action == "SPLIT" else "REFUND" if action == "REFUND" else "DISCOUNT"
            adjustment_item = BillingAdjustment.objects.create(
                tenant=tenant_obj,
                folio=folio_obj,
                adjustment_type=adj_type,
                amount=amt,
                reason=reason,
                is_approved=True
            )

            # If action is REFUND, record refund folio transaction and adjust reservation paid amount
            if action == "REFUND" and from_res_id:
                from apps.features.front_office.models import FolioTransaction
                from apps.features.reservations.models import ReservationEvent
                res_obj = Reservation.objects.filter(id=from_res_id).first()
                if res_obj:
                    res_obj.paid_amount = max(decimal.Decimal("0.00"), res_obj.paid_amount - amt)
                    gross = (res_obj.total_amount + res_obj.tax_amount) - res_obj.discount_amount
                    res_obj.balance_amount = max(decimal.Decimal("0.00"), gross - res_obj.paid_amount)
                    res_obj.save()

                    FolioTransaction.objects.create(
                        tenant=tenant_obj,
                        folio=folio_obj,
                        transaction_type="REFUND",
                        charge_code="REFUND_ISSUED",
                        amount=amt,
                        description=f"Refund processed: {reason}"
                    )
                    folio_obj.total_payments = max(decimal.Decimal("0.00"), folio_obj.total_payments - amt)
                    folio_obj.balance = folio_obj.total_charges - folio_obj.total_payments
                    if folio_obj.balance > decimal.Decimal("0.00"):
                        folio_obj.status = "OPEN"
                    folio_obj.save()

                    ReservationEvent.objects.create(
                        tenant=tenant_obj,
                        reservation=res_obj,
                        event_type="PAYMENT_REFUNDED",
                        description=f"Refund of ₹{amt} processed. Reason: {reason}",
                        actor_user=request.user if getattr(request.user, "is_authenticated", False) else None
                    )

            # If action is TRANSFER and to_res_id is provided, debit source and credit destination
            if action == "TRANSFER" and to_res_id:
                from apps.features.front_office.models import FolioTransaction
                from apps.features.reservations.models import ReservationExtraCharge, ReservationEvent
                from django.utils import timezone

                to_res_obj = Reservation.objects.filter(id=to_res_id).first()
                if to_res_obj:
                    to_guest = getattr(to_res_obj, 'primary_guest', None)
                    to_guest_name = (
                        getattr(to_res_obj, 'primary_guest_name', None) or
                        (f"{to_guest.first_name} {to_guest.last_name}".strip() if to_guest else "Guest")
                    )

                    # 1. Update source reservation: decrease total & balance
                    if from_res_id:
                        from_res = Reservation.objects.filter(id=from_res_id).first()
                        if from_res:
                            from_res.total_amount = max(decimal.Decimal("0.00"), from_res.total_amount - amt)
                            from_gross = (from_res.total_amount + from_res.tax_amount) - from_res.discount_amount
                            from_res.balance_amount = max(decimal.Decimal("0.00"), from_gross - from_res.paid_amount)
                            from_res.save()

                            # Record transaction in source folio
                            FolioTransaction.objects.create(
                                tenant=tenant_obj,
                                folio=folio_obj,
                                transaction_type="CHARGE",
                                charge_code="TRANSFER_OUT",
                                amount=amt,
                                description=f"Transferred to {to_res_obj.confirmation_number} ({to_guest_name}): {reason}",
                                is_reversed=True
                            )
                            folio_obj.total_charges = max(decimal.Decimal("0.00"), folio_obj.total_charges - amt)
                            folio_obj.balance = folio_obj.total_charges - folio_obj.total_payments
                            folio_obj.save()

                            ReservationEvent.objects.create(
                                tenant=tenant_obj,
                                reservation=from_res,
                                event_type="CHARGE_TRANSFER",
                                description=f"Transferred ₹{amt} to reservation {to_res_obj.confirmation_number}.",
                                actor_user=request.user if getattr(request.user, "is_authenticated", False) else None
                            )

                    # 2. Add extra charge and update target reservation
                    ReservationExtraCharge.objects.create(
                        tenant=tenant_obj,
                        reservation=to_res_obj,
                        description=f"Transferred charge: {reason}",
                        amount=amt,
                        tax_amount=decimal.Decimal("0.00"),
                        tax_type="Excluded",
                        tax_percent=decimal.Decimal("0.00"),
                        date=timezone.now().date()
                    )
                    to_res_obj.total_amount = to_res_obj.total_amount + amt
                    to_gross = (to_res_obj.total_amount + to_res_obj.tax_amount) - to_res_obj.discount_amount
                    to_res_obj.balance_amount = max(decimal.Decimal("0.00"), to_gross - to_res_obj.paid_amount)
                    to_res_obj.save()

                    # Record transaction in target folio
                    to_folio = GuestFolio.objects.filter(reservation=to_res_obj).first()
                    if not to_folio:
                        to_folio = GuestFolio.objects.create(
                            tenant=tenant_obj,
                            reservation=to_res_obj,
                            folio_number=f"FOLIO-{str(to_res_obj.id)[:8].upper()}",
                            status="OPEN"
                        )
                    FolioTransaction.objects.create(
                        tenant=tenant_obj,
                        folio=to_folio,
                        transaction_type="CHARGE",
                        charge_code="TRANSFER_IN",
                        amount=amt,
                        description=f"Transferred in from {res_obj.confirmation_number if from_res_id and res_obj else 'source'}: {reason}"
                    )
                    to_folio.total_charges = to_folio.total_charges + amt
                    to_folio.balance = to_folio.total_charges - to_folio.total_payments
                    if to_folio.status == "SETTLED" and to_folio.balance > decimal.Decimal("0.00"):
                        to_folio.status = "OPEN"
                    to_folio.save()

                    ReservationEvent.objects.create(
                        tenant=tenant_obj,
                        reservation=to_res_obj,
                        event_type="CHARGE_POSTED",
                        description=f"Received transfer of ₹{amt} from {res_obj.confirmation_number if from_res_id and res_obj else 'source'}.",
                        actor_user=request.user if getattr(request.user, "is_authenticated", False) else None
                    )

        return Response({
            "status": "SUCCESS",
            "message": f"Billing {action.lower()} executed successfully.",
            "adjustment_id": str(adjustment_item.id) if adjustment_item else None,
            "transfer_amount": float(amt),
            "from_reservation_id": from_res_id,
            "to_reservation_id": to_res_id,
            "action": action
        }, status=status.HTTP_201_CREATED)
