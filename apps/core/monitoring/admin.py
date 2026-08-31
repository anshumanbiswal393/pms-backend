from django.contrib import admin
from apps.core.monitoring.models import (
    SystemHealthSnapshot,
    SystemMetric,
    ApplicationLog,
    ErrorLog
)

@admin.register(SystemHealthSnapshot)
class SystemHealthSnapshotAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'status', 'recorded_at')
    list_filter = ('status', 'service_name')

@admin.register(SystemMetric)
class SystemMetricAdmin(admin.ModelAdmin):
    list_display = ('metric_code', 'metric_value', 'recorded_at')
    list_filter = ('metric_code',)

@admin.register(ApplicationLog)
class ApplicationLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'method', 'path', 'status_code', 'duration_ms', 'user_email', 'tenant_id', 'ip_address')
    list_filter = ('method', 'status_code', 'is_authenticated')
    search_fields = ('path', 'user_email', 'tenant_id', 'ip_address', 'request_id')
    readonly_fields = [f.name for f in ApplicationLog._meta.fields]
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'error_type', 'status_code', 'method', 'path', 'user_email', 'tenant_id', 'is_resolved')
    list_filter = ('error_type', 'status_code', 'is_resolved')
    search_fields = ('error_message', 'error_type', 'path', 'user_email', 'tenant_id', 'request_id')
    readonly_fields = [f.name for f in ErrorLog._meta.fields if f.name != 'is_resolved']
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False
