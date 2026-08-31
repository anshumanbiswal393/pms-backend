import uuid
from django.db import models


class SystemHealthSnapshot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_name = models.CharField(max_length=120)
    status = models.CharField(max_length=32) # HEALTHY, DEGRADED, UNHEALTHY
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_health_snapshot'

    def __str__(self):
        return f"{self.service_name} : {self.status} at {self.recorded_at}"


class SystemMetric(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    metric_code = models.CharField(max_length=64, db_index=True) # API_CALLS, ACTIVE_USERS, FAILED_LOGINS, ACTIVE_RESERVATIONS
    metric_value = models.FloatField(default=0.0)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'system_metric'

    def __str__(self):
        return f"{self.metric_code} = {self.metric_value} at {self.recorded_at}"


class ApplicationLog(models.Model):
    """
    Stores total application HTTP request & response transactions across the entire PMS platform.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # HTTP Request & Response Details
    method = models.CharField(max_length=10, db_index=True)
    path = models.CharField(max_length=512, db_index=True)
    status_code = models.IntegerField(db_index=True)
    duration_ms = models.FloatField(default=0.0, help_text="Total execution latency in milliseconds")

    # Client Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, null=True, blank=True)

    # Tenant, Property & User Context
    tenant_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    property_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    user_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    user_email = models.CharField(max_length=255, null=True, blank=True)
    user_role = models.CharField(max_length=64, null=True, blank=True)
    is_authenticated = models.BooleanField(default=False)

    # Payloads & Headers (Sanitized with PII/Secrets masked)
    query_params = models.JSONField(null=True, blank=True)
    request_body = models.JSONField(null=True, blank=True)
    response_summary = models.JSONField(null=True, blank=True)
    headers = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'application_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'status_code']),
            models.Index(fields=['tenant_id', '-timestamp']),
            models.Index(fields=['method', 'path']),
        ]

    def __str__(self):
        return f"[{self.timestamp}] {self.method} {self.path} ({self.status_code}) - {self.duration_ms}ms"


class ErrorLog(models.Model):
    """
    Stores all runtime unhandled exceptions, 5xx server errors, and critical application faults with stack traces.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Error Classification
    error_type = models.CharField(max_length=255, db_index=True) # e.g. ValueError, IntegrityError, OperationalError
    error_message = models.TextField()
    stack_trace = models.TextField(null=True, blank=True)

    # Request Context
    method = models.CharField(max_length=10, null=True, blank=True)
    path = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    status_code = models.IntegerField(default=500, db_index=True)

    # User & Tenant Context
    tenant_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    property_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    user_id = models.CharField(max_length=120, null=True, blank=True)
    user_email = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Diagnostic Payloads
    request_payload = models.JSONField(null=True, blank=True)
    context_data = models.JSONField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'error_log'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp', 'error_type']),
            models.Index(fields=['status_code', '-timestamp']),
            models.Index(fields=['is_resolved', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.timestamp}] {self.error_type}: {self.error_message[:80]} ({self.status_code})"
