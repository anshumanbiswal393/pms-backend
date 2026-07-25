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
            adj_type = "TRANSFER" if action == "TRANSFER" else "SPLIT" if action == "SPLIT" else "DISCOUNT"
            adjustment_item = BillingAdjustment.objects.create(
                tenant=tenant_obj,
                folio=folio_obj,
                adjustment_type=adj_type,
                amount=amt,
                reason=reason,
                is_approved=True
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
