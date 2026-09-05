from datetime import datetime, date
import logging
from rest_framework import views, permissions, status
from rest_framework.response import Response
from django.utils import timezone
from apps.core.tenants.models import Tenant, Property
from apps.features.front_office.models import NightAuditSession
from apps.features.front_office.services import NightAuditService
from apps.features.reservations.models import Reservation

logger = logging.getLogger(__name__)


def get_property_context(request):
    """Resolves the active property context from headers or tenant properties."""
    tenant = getattr(request, 'tenant', None)
    if not tenant and hasattr(request, 'user') and request.user and request.user.is_authenticated:
        tenant = getattr(request.user, 'tenant', None)

    property_id = (
        request.headers.get('X-Property-ID') or
        request.headers.get('X-Property-Id') or
        request.headers.get('x-property-id') or
        request.query_params.get('property_id') or
        (request.data.get('property_id') if hasattr(request, 'data') and isinstance(request.data, dict) else None)
    )
    property_obj = None

    if property_id:
        if tenant:
            property_obj = Property.objects.filter(id=property_id, tenant=tenant).first()
        if not property_obj:
            property_obj = Property.objects.filter(id=property_id).first()
            if property_obj and not tenant:
                tenant = property_obj.tenant

    if not property_obj and tenant:
        property_obj = Property.objects.filter(tenant=tenant, is_active=True).first() or Property.objects.filter(tenant=tenant).first()

    if not property_obj:
        property_obj = Property.objects.filter(is_active=True).first() or Property.objects.first()
        if property_obj and not tenant:
            tenant = property_obj.tenant

    return tenant, property_obj


class NightAuditStatusView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant, property_obj = get_property_context(request)
        if not property_obj:
            return Response(
                {"detail": "No active property found for this tenant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_date = None
        date_str = request.query_params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = None

        try:
            status_data = NightAuditService.get_audit_status(property_obj, tenant, target_date=target_date)
            return Response(status_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error fetching night audit status: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NightAuditValidateView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant, property_obj = get_property_context(request)
        if not property_obj:
            return Response(
                {"detail": "No active property found for this tenant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_date = None
        date_str = request.data.get('date') or request.data.get('audit_date') or request.query_params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = None

        try:
            val_data = NightAuditService.validate_checklist(property_obj, tenant, target_date=target_date)
            return Response(val_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error validating night audit checklist: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NightAuditAutoPostPreviewView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant, property_obj = get_property_context(request)
        if not property_obj:
            return Response(
                {"detail": "No active property found for this tenant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_date = None
        date_str = request.data.get('date') or request.data.get('audit_date') or request.query_params.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = None

        try:
            preview_data = NightAuditService.get_auto_post_preview(property_obj, tenant, target_date=target_date)
            return Response(preview_data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Error generating auto post preview: {e}")
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NightAuditExecuteView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant, property_obj = get_property_context(request)
        if not property_obj:
            return Response(
                {"detail": "No active property found for this tenant."},
                status=status.HTTP_400_BAD_REQUEST
            )

        auto_noshow = request.data.get('auto_process_noshow', True)
        auto_close_cashiers = request.data.get('auto_close_cashiers', True)

        target_date = None
        date_str = request.data.get('date') or request.data.get('audit_date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                target_date = None

        try:
            results = NightAuditService.execute_night_audit(
                property_obj=property_obj,
                tenant=tenant,
                user=request.user,
                auto_noshow=bool(auto_noshow),
                auto_close_cashiers=bool(auto_close_cashiers),
                target_date=target_date
            )
            return Response(results, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception(f"Fatal error executing night audit: {e}")
            return Response(
                {"detail": f"Night Audit Execution Failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class NightAuditHistoryView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        tenant, property_obj = get_property_context(request)
        if not property_obj:
            return Response([], status=status.HTTP_200_OK)

        sessions = NightAuditSession.objects.filter(
            property=property_obj
        ).order_by('-audit_date', '-created_at')[:30]

        data = []
        for s in sessions:
            data.append({
                'id': str(s.id),
                'audit_date': str(s.audit_date),
                'status': s.status,
                'started_at': s.started_at.isoformat() if s.started_at else None,
                'completed_at': s.completed_at.isoformat() if s.completed_at else None,
                'rooms_occupied': s.rooms_occupied,
                'rooms_total': s.rooms_total,
                'occupancy_percentage': float(s.occupancy_percentage),
                'total_charges_posted': float(s.total_charges_posted),
                'total_tax_posted': float(s.total_tax_posted),
                'no_shows_processed': s.no_shows_processed,
                'performed_by': s.performed_by.name if (s.performed_by and hasattr(s.performed_by, 'name')) else "System Admin",
                'post_audit_summary': s.post_audit_summary or {},
            })

        return Response(data, status=status.HTTP_200_OK)


class NightAuditQuickCheckinView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant, property_obj = get_property_context(request)
        reservation_id = request.data.get('reservation_id')

        res = Reservation.objects.filter(id=reservation_id, tenant=tenant).first()
        if not res:
            return Response({"detail": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)

        res.status = 'CHECKED_IN'
        res.actual_check_in = timezone.now()
        res.save(update_fields=['status', 'actual_check_in'])

        return Response({"message": f"Reservation {res.confirmation_number} checked in."}, status=status.HTTP_200_OK)


class NightAuditQuickNoShowView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tenant, property_obj = get_property_context(request)
        reservation_id = request.data.get('reservation_id')

        res = Reservation.objects.filter(id=reservation_id, tenant=tenant).first()
        if not res:
            return Response({"detail": "Reservation not found."}, status=status.HTTP_404_NOT_FOUND)

        res.status = 'CANCELLED'
        res.save(update_fields=['status'])

        return Response({"message": f"Reservation {res.confirmation_number} marked as No-Show."}, status=status.HTTP_200_OK)
