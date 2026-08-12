from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from apps.core.common.models import (
    SystemLanguage, SystemTax, SystemDocumentType,
    SystemCurrency, SystemDateFormat, SystemTimeFormat,
    Department, Shift, OccupancyType, BookingSource,
    PaymentGateway, TenantPaymentGateway
)
from apps.core.common.serializers import (
    SystemLanguageSerializer, SystemTaxSerializer,
    SystemDocumentTypeSerializer, SystemCurrencySerializer,
    SystemDateFormatSerializer, SystemTimeFormatSerializer,
    DepartmentSerializer, ShiftSerializer, OccupancyTypeSerializer,
    BookingSourceSerializer, PaymentGatewaySerializer, TenantPaymentGatewaySerializer
)

class PaymentGatewayViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentGatewaySerializer
    queryset = PaymentGateway.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def list(self, request, *args, **kwargs):
        # Auto-seed default gateways if empty
        if not PaymentGateway.objects.exists():
            default_gateways = [
                {
                    "name": "Razorpay Checkout",
                    "code": "razorpay",
                    "subtitle": "UPI, Cards, NetBanking, Wallets",
                    "badge": "RECOMMENDED",
                    "is_active": True,
                    "is_default": True,
                },
                {
                    "name": "HDFC Bank Gateway",
                    "code": "hdfc",
                    "subtitle": "HDFC Debit / Credit Card Direct PG",
                    "badge": "DIRECT",
                    "is_active": True,
                    "is_default": False,
                },
                {
                    "name": "CCAvenue Payment",
                    "code": "ccavenue",
                    "subtitle": "Multi-Currency Payment Gateway",
                    "badge": "SECURE",
                    "is_active": True,
                    "is_default": False,
                },
                {
                    "name": "PayU Money",
                    "code": "payu",
                    "subtitle": "Instant One-Click Checkout",
                    "badge": "FAST",
                    "is_active": True,
                    "is_default": False,
                },
                {
                    "name": "Easebuzz Gateway",
                    "code": "easebuzz",
                    "subtitle": "UPI, QR Code & Auto-Debit",
                    "badge": "UPI",
                    "is_active": True,
                    "is_default": False,
                },
                {
                    "name": "PhonePe PG",
                    "code": "phonepe",
                    "subtitle": "Direct PhonePe UPI & QR",
                    "badge": "UPI QR",
                    "is_active": True,
                    "is_default": False,
                },
            ]
            for gw in default_gateways:
                PaymentGateway.objects.get_or_create(code=gw["code"], defaults=gw)

        return super().list(request, *args, **kwargs)


class TenantPaymentGatewayViewSet(viewsets.ModelViewSet):
    serializer_class = TenantPaymentGatewaySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            return TenantPaymentGateway.objects.filter(tenant=tenant)
        return TenantPaymentGateway.objects.all()

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)


class SystemLanguageViewSet(viewsets.ModelViewSet):
    serializer_class = SystemLanguageSerializer
    queryset = SystemLanguage.objects.all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        is_default = serializer.validated_data.get('is_default', False)
        if is_default:
            SystemLanguage.objects.filter(is_default=True).update(is_default=False)
        serializer.save()

    def perform_update(self, serializer):
        is_default = serializer.validated_data.get('is_default', False)
        if is_default:
            SystemLanguage.objects.filter(is_default=True).update(is_default=False)
        serializer.save()


class TenantAwareSettingsViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        is_superuser = getattr(user, 'is_superuser', False) if user else False
        if is_superuser:
            return self.queryset

        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            return self.queryset.filter(Q(tenant__isnull=True) | Q(tenant=tenant))
        return self.queryset.filter(tenant__isnull=True)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        user = self.request.user
        is_super = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') == 'SUPERADMIN'
        
        if is_super:
            tenant_id = self.request.data.get('tenant')
            if tenant_id:
                serializer.save(tenant_id=tenant_id)
            else:
                serializer.save(tenant=None)
        else:
            serializer.save(tenant=tenant)


class SystemTaxViewSet(TenantAwareSettingsViewSet):
    serializer_class = SystemTaxSerializer
    queryset = SystemTax.objects.all()


class SystemDocumentTypeViewSet(TenantAwareSettingsViewSet):
    serializer_class = SystemDocumentTypeSerializer
    queryset = SystemDocumentType.objects.all()



class SystemCurrencyViewSet(TenantAwareSettingsViewSet):
    serializer_class = SystemCurrencySerializer
    queryset = SystemCurrency.objects.all()


class SystemDateFormatViewSet(TenantAwareSettingsViewSet):
    serializer_class = SystemDateFormatSerializer
    queryset = SystemDateFormat.objects.all()


class SystemTimeFormatViewSet(TenantAwareSettingsViewSet):
    serializer_class = SystemTimeFormatSerializer
    queryset = SystemTimeFormat.objects.all()


class DepartmentViewSet(TenantAwareSettingsViewSet):
    serializer_class = DepartmentSerializer
    queryset = Department.objects.all()


class ShiftViewSet(TenantAwareSettingsViewSet):
    serializer_class = ShiftSerializer
    queryset = Shift.objects.all()


class OccupancyTypeViewSet(TenantAwareSettingsViewSet):
    serializer_class = OccupancyTypeSerializer
    queryset = OccupancyType.objects.all()


class BookingSourceViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSourceSerializer
    queryset = BookingSource.objects.all()
    permission_classes = [permissions.IsAuthenticated]


class UnifiedSendEmailView(APIView):
    """
    Single unified API endpoint for dispatching all email types:
    - OTP_VERIFICATION
    - RESERVATION_CONFIRMATION
    - INVOICE_FOLIO
    - PAYMENT_RECEIPT
    - STAFF_INVITATION
    - LOST_FOUND_NOTIFICATION
    - GENERIC
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email_type = request.data.get("email_type") or request.data.get("type") or "GENERIC"
        recipient_email = request.data.get("recipient_email") or request.data.get("to") or request.data.get("email")
        recipient_name = request.data.get("recipient_name") or request.data.get("name", "")
        subject = request.data.get("subject")
        property_id = request.data.get("property_id") or request.data.get("property")
        data = request.data.get("data") or request.data.get("payload") or request.data

        if not recipient_email:
            return Response(
                {"detail": "recipient_email is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.core.common.email_service import UnifiedMailService

        res = UnifiedMailService.send_email(
            email_type=email_type,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            property_id=property_id,
            data=data
        )

        if res.get("success"):
            return Response(res, status=status.HTTP_200_OK)
        return Response(res, status=status.HTTP_400_BAD_REQUEST)

