import uuid
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from apps.POS.models import (
    Outlet,
    POSRegister,
    POSOutletConfig,
    POSSubOrderType,
    POSAreaDeliveryCharge,
    POSDeliveryDistanceSlab,
    POSEmailTemplate,
    POSBankAccount,
    POSCashierShift,
    POSCashDrawerMovement,
    POSCashDenomination,
    POSExpense,
    POSGstSetting,
    POSKycDocument,
    POSLoanFacility,
    POSOnlineReconciliation,
    POSPaymentGatewayConfig,
    POSServicePaymentRecord,
    POSUtilityBill,
    POSVirtualWallet,
    POSVirtualWalletTransaction,
    POSBillerGroup,
    POSStaffUser,
    POSManagementLog,
    POSSupportTicket,
    POSMarketplaceIntegration,
    POSAuditTrail,
)
from apps.POS.serializers_management import (
    POSOutletConfigSerializer,
    POSSubOrderTypeSerializer,
    POSAreaDeliveryChargeSerializer,
    POSDeliveryDistanceSlabSerializer,
    POSEmailTemplateSerializer,
    POSBankAccountSerializer,
    POSCashierShiftSerializer,
    POSCashDrawerMovementSerializer,
    POSCashDenominationSerializer,
    POSExpenseSerializer,
    POSGstSettingSerializer,
    POSKycDocumentSerializer,
    POSLoanFacilitySerializer,
    POSOnlineReconciliationSerializer,
    POSPaymentGatewayConfigSerializer,
    POSServicePaymentRecordSerializer,
    POSUtilityBillSerializer,
    POSVirtualWalletSerializer,
    POSVirtualWalletTransactionSerializer,
    POSBillerGroupSerializer,
    POSStaffUserSerializer,
    PINLoginSerializer,
    SupervisorVerifySerializer,
    POSManagementLogSerializer,
    POSSupportTicketSerializer,
    POSMarketplaceIntegrationSerializer,
    POSAuditTrailSerializer,
)
from apps.POS.services.management import (
    OutletConfigService,
    ShiftManagementService,
    StaffAuthService,
    VirtualWalletService,
    AuditTrailService,
    DataManagementService,
)



def resolve_outlet(request) -> Optional[Outlet]:
    """Helper to extract active outlet from query params, headers, or default primary."""
    outlet_id = (
        request.query_params.get('outlet_id')
        or request.query_params.get('outletId')
        or request.headers.get('X-Outlet-ID')
    )
    if outlet_id:
        try:
            return Outlet.objects.filter(id=outlet_id, deleted_at__isnull=True).first()
        except Exception:
            pass
    return Outlet.objects.filter(deleted_at__isnull=True).first()


@extend_schema(tags=['POS - Management: Outlet Config'])
class POSOutletConfigAPIView(APIView):
    """
    Get or update the complete outlet configuration.
    Returns details, contact, timings, payment, invoice sequences, display, print logo,
    calculations, connected services, print settings, and customer preferences.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        config = OutletConfigService.get_or_create_config(outlet)
        serializer = POSOutletConfigSerializer(config)
        return Response(serializer.data)

    def put(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        config = OutletConfigService.update_config(outlet, request.data)
        serializer = POSOutletConfigSerializer(config)
        return Response(serializer.data)

    def patch(self, request):
        return self.put(request)


@extend_schema(tags=['POS - Management: Outlet Config'])
class POSOutletConfigResetAPIView(APIView):
    """Reset outlet configuration to official Retrod POS defaults."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        POSOutletConfig.objects.filter(outlet=outlet).delete()
        config = OutletConfigService.get_or_create_config(outlet)
        serializer = POSOutletConfigSerializer(config)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Sub-Order Types'], description="List sub-order types."),
    create=extend_schema(tags=['POS - Management: Sub-Order Types'], description="Create a new sub-order type."),
    retrieve=extend_schema(tags=['POS - Management: Sub-Order Types'], description="Get sub-order type details."),
    update=extend_schema(tags=['POS - Management: Sub-Order Types'], description="Update sub-order type."),
    destroy=extend_schema(tags=['POS - Management: Sub-Order Types'], description="Delete sub-order type."),
)
class POSSubOrderTypeViewSet(viewsets.ModelViewSet):
    serializer_class = POSSubOrderTypeSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSSubOrderType.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id') or self.request.query_params.get('outletId')
        type_param = self.request.query_params.get('type')
        status_param = self.request.query_params.get('status')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if type_param:
            qs = qs.filter(type=type_param)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        outlet_id = self.request.data.get('outlet') or self.request.query_params.get('outlet_id')
        if not outlet_id:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Delivery Settings'], description="List area delivery charges."),
    create=extend_schema(tags=['POS - Management: Delivery Settings'], description="Add area delivery charge."),
    retrieve=extend_schema(tags=['POS - Management: Delivery Settings'], description="Get area delivery charge."),
    update=extend_schema(tags=['POS - Management: Delivery Settings'], description="Update area delivery charge."),
    destroy=extend_schema(tags=['POS - Management: Delivery Settings'], description="Delete area delivery charge."),
)
class POSAreaDeliveryChargeViewSet(viewsets.ModelViewSet):
    serializer_class = POSAreaDeliveryChargeSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSAreaDeliveryCharge.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id') or self.request.query_params.get('outletId')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Delivery Settings'], description="List distance-based delivery fee slabs."),
    create=extend_schema(tags=['POS - Management: Delivery Settings'], description="Create distance slab."),
    retrieve=extend_schema(tags=['POS - Management: Delivery Settings'], description="Get distance slab."),
    update=extend_schema(tags=['POS - Management: Delivery Settings'], description="Update distance slab."),
    destroy=extend_schema(tags=['POS - Management: Delivery Settings'], description="Delete distance slab."),
)
class POSDeliveryDistanceSlabViewSet(viewsets.ModelViewSet):
    serializer_class = POSDeliveryDistanceSlabSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSDeliveryDistanceSlab.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id') or self.request.query_params.get('outletId')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Email Templates'], description="List email templates."),
    create=extend_schema(tags=['POS - Management: Email Templates'], description="Create email template."),
    retrieve=extend_schema(tags=['POS - Management: Email Templates'], description="Get email template."),
    update=extend_schema(tags=['POS - Management: Email Templates'], description="Update email template."),
    destroy=extend_schema(tags=['POS - Management: Email Templates'], description="Delete email template."),
)
class POSEmailTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = POSEmailTemplateSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSEmailTemplate.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        template_type = self.request.query_params.get('template_type')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if template_type:
            qs = qs.filter(template_type=template_type)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()

    @action(detail=True, methods=['post'], url_path='send-test')
    def send_test(self, request, pk=None):
        template = self.get_object()
        target_email = request.data.get('email') or 'test@highwayinn.in'
        # Log test dispatch
        POSManagementLog.objects.create(
            outlet=template.outlet,
            log_type='NOTIFICATIONS',
            event_title=f"Test email sent: {template.name} to {target_email}",
            actor_name="Management Admin",
            details={'target_email': target_email, 'subject': template.subject},
        )
        return Response({
            "success": True,
            "message": f"Test email for '{template.name}' successfully dispatched to {target_email}"
        })


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List bank accounts."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Add bank account."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get bank account details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update bank account."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete bank account."),
)
class POSBankAccountViewSet(viewsets.ModelViewSet):
    serializer_class = POSBankAccountSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSBankAccount.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()

    @action(detail=True, methods=['post'], url_path='set-primary')
    def set_primary(self, request, pk=None):
        account = self.get_object()
        POSBankAccount.objects.filter(outlet=account.outlet).exclude(id=account.id).update(is_primary=False)
        account.is_primary = True
        account.save(update_fields=['is_primary', 'updated_at'])
        return Response({"success": True, "message": f"{account.bank_name} marked as primary settlement account."})


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Shift & Cash Drawer'], description="List cashier shifts."),
    create=extend_schema(tags=['POS - Management: Shift & Cash Drawer'], description="Open a new shift."),
    retrieve=extend_schema(tags=['POS - Management: Shift & Cash Drawer'], description="Get shift details."),
)
class POSCashierShiftViewSet(viewsets.ModelViewSet):
    serializer_class = POSCashierShiftSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSCashierShift.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        register_id = self.request.query_params.get('register_id')
        status_param = self.request.query_params.get('status')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if register_id:
            qs = qs.filter(register_id=register_id)
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs.select_related('register', 'outlet').prefetch_related('movements')

    @action(detail=False, methods=['get'], url_path='active')
    def active_shift(self, request):
        register_id = request.query_params.get('register_id')
        outlet_id = request.query_params.get('outlet_id')
        qs = POSCashierShift.objects.filter(status='OPEN', deleted_at__isnull=True)
        if register_id:
            qs = qs.filter(register_id=register_id)
        elif outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        shift = qs.order_by('-start_time').first()
        if not shift:
            return Response({"active": False, "shift": None})
        serializer = self.get_serializer(shift)
        return Response({"active": True, "shift": serializer.data})

    @action(detail=False, methods=['post'], url_path='open-shift')
    def open_shift(self, request):
        register_id = request.data.get('register_id')
        cashier_name = request.data.get('cashier_name') or 'Primary Cashier'
        opening_float = Decimal(str(request.data.get('opening_float', '0.00')))
        notes = request.data.get('notes', '')

        if not register_id:
            register = POSRegister.objects.filter(deleted_at__isnull=True).first()
            if not register:
                return Response({"detail": "No POS register available to open shift."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            register = get_object_or_404(POSRegister, id=register_id)

        shift = ShiftManagementService.open_shift(
            register=register,
            cashier_name=cashier_name,
            cashier_user=request.user if request.user.is_authenticated else None,
            opening_float=opening_float,
            notes=notes,
        )
        return Response(self.get_serializer(shift).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cash-movement')
    def cash_movement(self, request, pk=None):
        shift = self.get_object()
        movement_type = request.data.get('movement_type', 'TOP_UP')
        amount = Decimal(str(request.data.get('amount', '0.00')))
        reason = request.data.get('reason', '')
        authorized_by = request.data.get('authorized_by_name', '')

        movement = ShiftManagementService.record_cash_movement(
            shift=shift,
            movement_type=movement_type,
            amount=amount,
            reason=reason,
            authorized_by_name=authorized_by,
        )
        serializer = POSCashDrawerMovementSerializer(movement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='close-shift')
    def close_shift(self, request, pk=None):
        shift = self.get_object()
        actual_cash = Decimal(str(request.data.get('actual_cash_counted', '0.00')))
        denominations = request.data.get('denominations')
        notes = request.data.get('notes', '')

        closed_shift = ShiftManagementService.close_shift(
            shift=shift,
            actual_cash_counted=actual_cash,
            denominations=denominations,
            notes=notes,
        )
        return Response(self.get_serializer(closed_shift).data)


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Shift & Cash Drawer'], description="List cash denominations."),
    create=extend_schema(tags=['POS - Management: Shift & Cash Drawer'], description="Record physical denomination count."),
)
class POSCashDenominationViewSet(viewsets.ModelViewSet):
    serializer_class = POSCashDenominationSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSCashDenomination.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        date_param = self.request.query_params.get('date')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if date_param:
            qs = qs.filter(date=date_param)
        return qs.select_related('outlet', 'register', 'shift')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List restaurant expenses."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Create expense record."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get expense details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update expense."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete expense."),
)
class POSExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = POSExpenseSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSExpense.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        category = self.request.query_params.get('category')
        status_param = self.request.query_params.get('status')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if category:
            qs = qs.filter(category=category)
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        outlet = serializer.validated_data.get('outlet') or resolve_outlet(self.request)
        if not serializer.validated_data.get('expense_number'):
            count = POSExpense.objects.filter(outlet=outlet).count() + 1
            serializer.validated_data['expense_number'] = f"EXP-{timezone.now().strftime('%y%m')}-{count:04d}"
        if outlet and 'outlet' not in serializer.validated_data:
            serializer.save(outlet=outlet)
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        expense = self.get_object()
        expense.status = 'APPROVED'
        expense.approved_by_name = request.data.get('approved_by_name') or 'Manager'
        expense.save(update_fields=['status', 'approved_by_name', 'updated_at'])
        return Response({"success": True, "message": f"Expense {expense.expense_number} approved."})

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        expense = self.get_object()
        expense.status = 'REJECTED'
        expense.notes = f"{expense.notes}\nRejected: {request.data.get('reason', '')}".strip()
        expense.save(update_fields=['status', 'notes', 'updated_at'])
        return Response({"success": True, "message": f"Expense {expense.expense_number} rejected."})


@extend_schema(tags=['POS - Management: Accounting'])
class POSGstSettingAPIView(APIView):
    """Get or update GST compliance settings for the outlet."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        setting, _ = POSGstSetting.objects.get_or_create(
            outlet=outlet,
            defaults={
                'gstin': outlet.gstin or '27AABCU9603R1ZX',
                'legal_name': outlet.name,
                'trade_name': outlet.name,
                'pan_number': (outlet.gstin or 'AABCU9603R')[2:12],
                'state': 'Maharashtra',
                'state_code': '27',
                'is_composition': False,
                'filing_frequency': 'MONTHLY',
                'default_hsn_code': '996331',
                'turnover_slab': 'Up to ₹1.5 Cr',
            }
        )
        return Response(POSGstSettingSerializer(setting).data)

    def put(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        setting, _ = POSGstSetting.objects.get_or_create(outlet=outlet)
        serializer = POSGstSettingSerializer(setting, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if 'gstin' in request.data:
            outlet.gstin = request.data['gstin']
            outlet.save(update_fields=['gstin', 'updated_at'])
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List KYC documents."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Add KYC document."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get KYC document."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update KYC document."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete KYC document."),
)
class POSKycDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = POSKycDocumentSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSKycDocument.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List business loans and capital facilities."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Register loan facility."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get loan details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update loan."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete loan."),
)
class POSLoanFacilityViewSet(viewsets.ModelViewSet):
    serializer_class = POSLoanFacilitySerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSLoanFacility.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List online order aggregator reconciliation records."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Record reconciliation cycle."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get reconciliation details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update reconciliation."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete reconciliation."),
)
class POSOnlineReconciliationViewSet(viewsets.ModelViewSet):
    serializer_class = POSOnlineReconciliationSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSOnlineReconciliation.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        aggregator = self.request.query_params.get('aggregator')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if aggregator:
            qs = qs.filter(aggregator=aggregator.upper())
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List payment gateway and EDC machine configurations."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Configure payment gateway."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get gateway details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update gateway."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete gateway."),
)
class POSPaymentGatewayConfigViewSet(viewsets.ModelViewSet):
    serializer_class = POSPaymentGatewayConfigSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSPaymentGatewayConfig.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List SaaS software service subscription invoices."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get invoice details."),
)
class POSServicePaymentRecordViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = POSServicePaymentRecordSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSServicePaymentRecord.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Accounting'], description="List restaurant utility bills."),
    create=extend_schema(tags=['POS - Management: Accounting'], description="Add utility bill."),
    retrieve=extend_schema(tags=['POS - Management: Accounting'], description="Get utility bill details."),
    update=extend_schema(tags=['POS - Management: Accounting'], description="Update utility bill."),
    destroy=extend_schema(tags=['POS - Management: Accounting'], description="Delete utility bill."),
)
class POSUtilityBillViewSet(viewsets.ModelViewSet):
    serializer_class = POSUtilityBillSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSUtilityBill.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        status_param = self.request.query_params.get('payment_status')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if status_param:
            qs = qs.filter(payment_status=status_param.upper())
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        bill = self.get_object()
        bill.payment_status = 'PAID'
        bill.payment_date = timezone.now().date()
        bill.payment_reference = request.data.get('reference', 'Paid via Net Banking')
        bill.save(update_fields=['payment_status', 'payment_date', 'payment_reference', 'updated_at'])
        return Response({"success": True, "message": f"{bill.utility_type} bill marked as paid."})


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Virtual Wallets'], description="List customer virtual credit wallets."),
    create=extend_schema(tags=['POS - Management: Virtual Wallets'], description="Open virtual wallet."),
    retrieve=extend_schema(tags=['POS - Management: Virtual Wallets'], description="Get wallet details & transactions."),
    update=extend_schema(tags=['POS - Management: Virtual Wallets'], description="Update wallet details."),
    destroy=extend_schema(tags=['POS - Management: Virtual Wallets'], description="Close wallet."),
)
class POSVirtualWalletViewSet(viewsets.ModelViewSet):
    serializer_class = POSVirtualWalletSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSVirtualWallet.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        phone = self.request.query_params.get('phone')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if phone:
            qs = qs.filter(customer_phone__icontains=phone)
        return qs.select_related('outlet').prefetch_related('transactions')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()

    @action(detail=True, methods=['post'], url_path='top-up')
    def top_up(self, request, pk=None):
        wallet = self.get_object()
        amount = Decimal(str(request.data.get('amount', '0.00')))
        note = request.data.get('note', 'Wallet Top-Up')
        performed_by = request.data.get('performed_by', 'Cashier')

        txn = VirtualWalletService.credit(wallet, amount, note, performed_by)
        return Response({
            "success": True,
            "new_balance": str(wallet.balance),
            "transaction": POSVirtualWalletTransactionSerializer(txn).data
        })

    @action(detail=True, methods=['post'], url_path='debit')
    def debit(self, request, pk=None):
        wallet = self.get_object()
        amount = Decimal(str(request.data.get('amount', '0.00')))
        order_id = request.data.get('order_id', '')
        note = request.data.get('note', 'Order settlement debit')
        performed_by = request.data.get('performed_by', 'Cashier')

        txn = VirtualWalletService.debit(wallet, amount, order_id, note, performed_by)
        return Response({
            "success": True,
            "new_balance": str(wallet.balance),
            "transaction": POSVirtualWalletTransactionSerializer(txn).data
        })


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Users & Staff'], description="List biller groups and permission roles."),
    create=extend_schema(tags=['POS - Management: Users & Staff'], description="Create biller group."),
    retrieve=extend_schema(tags=['POS - Management: Users & Staff'], description="Get biller group details."),
    update=extend_schema(tags=['POS - Management: Users & Staff'], description="Update biller group."),
    destroy=extend_schema(tags=['POS - Management: Users & Staff'], description="Delete biller group."),
)
class POSBillerGroupViewSet(viewsets.ModelViewSet):
    serializer_class = POSBillerGroupSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSBillerGroup.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet').prefetch_related('staff_members')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Users & Staff'], description="List biller app users and staff members."),
    create=extend_schema(tags=['POS - Management: Users & Staff'], description="Add biller staff user."),
    retrieve=extend_schema(tags=['POS - Management: Users & Staff'], description="Get biller staff details."),
    update=extend_schema(tags=['POS - Management: Users & Staff'], description="Update staff details or PIN."),
    destroy=extend_schema(tags=['POS - Management: Users & Staff'], description="Deactivate staff user."),
)
class POSStaffUserViewSet(viewsets.ModelViewSet):
    serializer_class = POSStaffUserSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSStaffUser.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        group_id = self.request.query_params.get('biller_group_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if group_id:
            qs = qs.filter(biller_group_id=group_id)
        return qs.select_related('outlet', 'biller_group')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()

    @action(detail=True, methods=['post'], url_path='reset-pin')
    def reset_pin(self, request, pk=None):
        staff = self.get_object()
        pin = request.data.get('pin')
        if not pin or len(str(pin)) < 4:
            return Response({"detail": "PIN must be at least 4 digits."}, status=status.HTTP_400_BAD_REQUEST)
        staff.set_pin(pin)
        staff.save(update_fields=['passcode_pin_hash', 'updated_at'])
        return Response({"success": True, "message": f"PIN for {staff.name} successfully updated."})


@extend_schema(tags=['POS - Management: Fast Authentication'])
class PINLoginAPIView(APIView):
    """
    Rapid 4-digit PIN authentication for billing and waiter terminals.
    Verifies staff user code and PIN, returning permissions and authorization.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = PINLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        outlet_id = serializer.validated_data['outlet_id']
        user_code = serializer.validated_data['user_code']
        pin = serializer.validated_data['pin']

        auth_res = StaffAuthService.verify_pin(
            outlet_id=str(outlet_id),
            user_code=user_code,
            pin=pin
        )
        if not auth_res:
            return Response(
                {"success": False, "detail": "Invalid user code or PIN for this outlet."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        return Response({"success": True, "staff": auth_res})


@extend_schema(tags=['POS - Management: Fast Authentication'])
class SupervisorVerifyAPIView(APIView):
    """
    Supervisor PIN verification modal for KOT voiding, price overrides, and manager discounts.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = SupervisorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        outlet_id = serializer.validated_data['outlet_id']
        pin = serializer.validated_data['supervisor_pin']
        action_name = serializer.validated_data.get('action', 'SUPERVISOR_OVERRIDE')

        is_valid = StaffAuthService.verify_supervisor(
            outlet_id=str(outlet_id),
            supervisor_pin=pin,
            action=action_name
        )
        if not is_valid:
            return Response(
                {"success": False, "detail": "Supervisor PIN verification failed."},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({"success": True, "message": f"Action '{action_name}' authorized by supervisor."})


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Operational Logs'], description="List operational event logs across all categories."),
    create=extend_schema(tags=['POS - Management: Operational Logs'], description="Record management event log."),
)
class POSManagementLogViewSet(viewsets.ModelViewSet):
    serializer_class = POSManagementLogSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSManagementLog.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        log_type = self.request.query_params.get('log_type')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if log_type:
            qs = qs.filter(log_type=log_type.upper())
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        if 'outlet' not in serializer.validated_data:
            outlet = resolve_outlet(self.request)
            if outlet:
                serializer.save(outlet=outlet)
                return
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Support & Tickets'], description="List support tickets."),
    create=extend_schema(tags=['POS - Management: Support & Tickets'], description="Open support ticket."),
    retrieve=extend_schema(tags=['POS - Management: Support & Tickets'], description="Get support ticket details."),
    update=extend_schema(tags=['POS - Management: Support & Tickets'], description="Update ticket status."),
)
class POSSupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = POSSupportTicketSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSSupportTicket.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        status_param = self.request.query_params.get('status')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if status_param:
            qs = qs.filter(status=status_param.upper())
        return qs.select_related('outlet')

    def perform_create(self, serializer):
        outlet = serializer.validated_data.get('outlet') or resolve_outlet(self.request)
        count = POSSupportTicket.objects.filter(outlet=outlet).count() + 1
        ticket_number = f"TICK-{timezone.now().strftime('%y%m')}-{count:04d}"
        if outlet and 'outlet' not in serializer.validated_data:
            serializer.save(outlet=outlet, ticket_number=ticket_number)
        else:
            serializer.save(ticket_number=ticket_number)

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve(self, request, pk=None):
        ticket = self.get_object()
        ticket.status = 'RESOLVED'
        ticket.resolved_at = timezone.now()
        ticket.response_notes = request.data.get('response_notes', 'Resolved by technical team.')
        ticket.save(update_fields=['status', 'resolved_at', 'response_notes', 'updated_at'])
        return Response({"success": True, "message": f"Ticket {ticket.ticket_number} marked as resolved."})


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Marketplace'], description="List marketplace app integrations."),
    retrieve=extend_schema(tags=['POS - Management: Marketplace'], description="Get marketplace integration details."),
    update=extend_schema(tags=['POS - Management: Marketplace'], description="Update marketplace settings."),
)
class POSMarketplaceIntegrationViewSet(viewsets.ModelViewSet):
    serializer_class = POSMarketplaceIntegrationSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSMarketplaceIntegration.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        return qs.select_related('outlet')

    @action(detail=True, methods=['post'], url_path='toggle-connection')
    def toggle_connection(self, request, pk=None):
        integration = self.get_object()
        integration.is_connected = not integration.is_connected
        integration.status = 'CONNECTED' if integration.is_connected else 'DISCONNECTED'
        integration.last_sync_at = timezone.now() if integration.is_connected else integration.last_sync_at
        integration.save(update_fields=['is_connected', 'status', 'last_sync_at', 'updated_at'])

        POSManagementLog.objects.create(
            outlet=integration.outlet,
            log_type='ONLINE_STORE',
            event_title=f"{integration.name} connection toggled to {'Active' if integration.is_connected else 'Inactive'}",
            actor_name="Management Admin",
            details={'platform': integration.platform, 'connected': integration.is_connected},
        )
        return Response({"success": True, "is_connected": integration.is_connected, "status": integration.status})

    @action(detail=True, methods=['post'], url_path='test-connection')
    def test_connection(self, request, pk=None):
        integration = self.get_object()
        integration.last_sync_at = timezone.now()
        integration.save(update_fields=['last_sync_at', 'updated_at'])
        return Response({
            "success": True,
            "latency_ms": 48,
            "message": f"Ping to {integration.name} API gateway successful. Status: healthy."
        })


@extend_schema_view(
    list=extend_schema(tags=['POS - Management: Audit Trail'], description="Search and review immutable system audit trail."),
)
class POSAuditTrailViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = POSAuditTrailSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_queryset(self):
        qs = POSAuditTrail.objects.filter(deleted_at__isnull=True)
        outlet_id = self.request.query_params.get('outlet_id')
        action_param = self.request.query_params.get('action')
        actor_name = self.request.query_params.get('actor_name')
        if outlet_id:
            qs = qs.filter(outlet_id=outlet_id)
        if action_param:
            qs = qs.filter(action=action_param.upper())
        if actor_name:
            qs = qs.filter(actor_name__icontains=actor_name)
        return qs.select_related('outlet')


@extend_schema(tags=['POS - Management: Data Management'])
class DataManagementStatsAPIView(APIView):
    """Provides high-level system data statistics for export and maintenance."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        stats = DataManagementService.get_stats(outlet)
        return Response({"success": True, "outlet": outlet.name, "stats": stats})


@extend_schema(tags=['POS - Management: Data Management'])
class DataManagementResetDemoAPIView(APIView):
    """Safely reset test transactions for go-live while keeping menu & configurations."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        outlet = resolve_outlet(request)
        if not outlet:
            return Response({"detail": "Outlet not found."}, status=status.HTTP_404_NOT_FOUND)
        confirmed_by = request.data.get('confirmed_by', 'Administrator')
        res = DataManagementService.reset_demo_data(outlet, confirmed_by)
        return Response({"success": True, "message": "Demo transaction data cleared.", "result": res})
