from django.urls import path
from apps.features.front_office.views import (
    NightAuditStatusView,
    NightAuditValidateView,
    NightAuditAutoPostPreviewView,
    NightAuditExecuteView,
    NightAuditHistoryView,
    NightAuditQuickCheckinView,
    NightAuditQuickNoShowView,
)

urlpatterns = [
    # Full prefix paths
    path('night-audit/status/', NightAuditStatusView.as_view(), name='night_audit_status'),
    path('night-audit/validate/', NightAuditValidateView.as_view(), name='night_audit_validate'),
    path('night-audit/auto-post-preview/', NightAuditAutoPostPreviewView.as_view(), name='night_audit_auto_post_preview'),
    path('night-audit/execute/', NightAuditExecuteView.as_view(), name='night_audit_execute'),
    path('night-audit/history/', NightAuditHistoryView.as_view(), name='night_audit_history'),
    path('night-audit/quick-checkin/', NightAuditQuickCheckinView.as_view(), name='night_audit_quick_checkin'),
    path('night-audit/quick-noshow/', NightAuditQuickNoShowView.as_view(), name='night_audit_quick_noshow'),

    # Direct short paths (when included under /api/night-audit/)
    path('status/', NightAuditStatusView.as_view(), name='night_audit_status_short'),
    path('validate/', NightAuditValidateView.as_view(), name='night_audit_validate_short'),
    path('auto-post-preview/', NightAuditAutoPostPreviewView.as_view(), name='night_audit_auto_post_preview_short'),
    path('execute/', NightAuditExecuteView.as_view(), name='night_audit_execute_short'),
    path('history/', NightAuditHistoryView.as_view(), name='night_audit_history_short'),
    path('quick-checkin/', NightAuditQuickCheckinView.as_view(), name='night_audit_quick_checkin_short'),
    path('quick-noshow/', NightAuditQuickNoShowView.as_view(), name='night_audit_quick_noshow_short'),
]
