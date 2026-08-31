import json
import time
import traceback
import uuid
from apps.core.monitoring.models import ApplicationLog, ErrorLog

SENSITIVE_KEYS = {
    'password', 'password1', 'password2', 'new_password', 'current_password',
    'token', 'access_token', 'refresh_token', 'jwt', 'authorization',
    'otp', 'otp_code', 'pin', 'secret', 'api_key', 'apikey',
    'credit_card', 'card_number', 'cvv', 'cvv2', 'card_cvv'
}


def sanitize_data(data, max_depth=5):
    """Recursively redacts sensitive keys and truncates huge strings."""
    if max_depth <= 0:
        return "<max_depth_reached>"

    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "********"
            else:
                sanitized[k] = sanitize_data(v, max_depth - 1)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_data(item, max_depth - 1) for item in data[:50]]
    elif isinstance(data, str):
        if len(data) > 1000:
            return data[:1000] + "... [truncated]"
        return data
    elif isinstance(data, (int, float, bool)) or data is None:
        return data
    else:
        return str(data)


class ApplicationLoggingMiddleware:
    """
    Middleware that captures all application HTTP requests and responses into ApplicationLog
    and records all runtime exceptions and 5xx/4xx server faults into ErrorLog.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.process_request(request)
        response = None
        try:
            response = self.get_response(request)
        except Exception as exc:
            self.process_exception(request, exc)
            raise exc

        if response is not None:
            response = self.process_response(request, response)
        return response

    def process_request(self, request):
        request.request_id = getattr(request, 'request_id', None) or uuid.uuid4()
        request._logging_start_time = time.perf_counter()
        request._logging_body = None
        request._error_logged = False

        # Pre-cache request body safely for mutation verbs
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            try:
                if request.body:
                    body_text = request.body.decode('utf-8', errors='replace')
                    try:
                        parsed_json = json.loads(body_text)
                        request._logging_body = sanitize_data(parsed_json)
                    except Exception:
                        request._logging_body = {"raw": body_text[:1000]}
            except Exception:
                request._logging_body = None

    def process_response(self, request, response):
        # Skip static assets and favicon
        path = request.path_info
        if path.startswith(('/static/', '/media/')) or path == '/favicon.ico':
            return response

        start_time = getattr(request, '_logging_start_time', None)
        duration_ms = 0.0
        if start_time:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Extract Client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Extract User context
        user = getattr(request, 'user', None)
        is_authenticated = bool(user and user.is_authenticated)
        user_id = str(user.id) if is_authenticated and hasattr(user, 'id') else None
        user_email = getattr(user, 'email', None) if is_authenticated else None
        user_role = getattr(user, 'role', None) if is_authenticated else None

        # Extract Tenant & Property context
        tenant = getattr(request, 'tenant', None)
        tenant_id = str(tenant.id) if tenant and hasattr(tenant, 'id') else None
        property_id = request.headers.get('X-Property-ID') or request.GET.get('property_id')

        # Query Parameters
        query_params = None
        if request.GET:
            try:
                query_params = sanitize_data(dict(request.GET))
            except Exception:
                pass

        # Headers (Selective, sanitized)
        headers = {
            'host': request.headers.get('Host'),
            'content-type': request.headers.get('Content-Type'),
            'x-property-id': request.headers.get('X-Property-ID'),
        }

        # Response Summary (for JSON responses)
        response_summary = None
        if response.get('Content-Type', '').startswith('application/json'):
            try:
                if hasattr(response, 'data'):
                    response_summary = sanitize_data(response.data)
                elif hasattr(response, 'content'):
                    response_summary = sanitize_data(json.loads(response.content.decode('utf-8', errors='replace')))
            except Exception:
                pass

        # 1. Log to ApplicationLog Table
        try:
            ApplicationLog.objects.create(
                request_id=getattr(request, 'request_id', uuid.uuid4()),
                method=request.method[:10],
                path=path[:512],
                status_code=response.status_code,
                duration_ms=duration_ms,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:512],
                tenant_id=tenant_id,
                property_id=str(property_id) if property_id else None,
                user_id=user_id,
                user_email=user_email[:255] if user_email else None,
                user_role=str(user_role)[:64] if user_role else None,
                is_authenticated=is_authenticated,
                query_params=query_params,
                request_body=getattr(request, '_logging_body', None),
                response_summary=response_summary,
                headers=headers,
            )
        except Exception as e:
            import sys
            print(f"[ApplicationLog Error] Failed to record application log: {e}", file=sys.stderr)

        # 2. If status code is 5xx and not yet logged by process_exception, log to ErrorLog
        if response.status_code >= 500 and not getattr(request, '_error_logged', False):
            try:
                error_msg = "Internal Server Error"
                if isinstance(response_summary, dict) and 'detail' in response_summary:
                    error_msg = str(response_summary['detail'])
                elif isinstance(response_summary, dict) and 'error' in response_summary:
                    error_msg = str(response_summary['error'])

                ErrorLog.objects.create(
                    request_id=getattr(request, 'request_id', None),
                    error_type="Http500ServerError",
                    error_message=error_msg,
                    stack_trace=None,
                    method=request.method[:10],
                    path=path[:512],
                    status_code=response.status_code,
                    tenant_id=tenant_id,
                    property_id=str(property_id) if property_id else None,
                    user_id=user_id,
                    user_email=user_email[:255] if user_email else None,
                    ip_address=ip_address,
                    request_payload=getattr(request, '_logging_body', None),
                    context_data={"status_code": response.status_code, "query_params": query_params},
                )
            except Exception as e:
                import sys
                print(f"[ErrorLog Error] Failed to record 5xx error log: {e}", file=sys.stderr)

        return response

    def process_exception(self, request, exception):
        """Catches and logs unhandled runtime exceptions with complete stack trace."""
        request._error_logged = True

        # Extract Client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Extract User context
        user = getattr(request, 'user', None)
        is_authenticated = bool(user and user.is_authenticated)
        user_id = str(user.id) if is_authenticated and hasattr(user, 'id') else None
        user_email = getattr(user, 'email', None) if is_authenticated else None

        # Extract Tenant & Property context
        tenant = getattr(request, 'tenant', None)
        tenant_id = str(tenant.id) if tenant and hasattr(tenant, 'id') else None
        property_id = request.headers.get('X-Property-ID') or request.GET.get('property_id')

        try:
            ErrorLog.objects.create(
                request_id=getattr(request, 'request_id', None),
                error_type=exception.__class__.__name__[:255],
                error_message=str(exception),
                stack_trace=traceback.format_exc(),
                method=request.method[:10],
                path=request.path_info[:512],
                status_code=500,
                tenant_id=tenant_id,
                property_id=str(property_id) if property_id else None,
                user_id=user_id,
                user_email=user_email[:255] if user_email else None,
                ip_address=ip_address,
                request_payload=getattr(request, '_logging_body', None),
                context_data={
                    "query_params": sanitize_data(dict(request.GET)) if request.GET else {},
                    "user_agent": request.META.get('HTTP_USER_AGENT', ''),
                },
            )
        except Exception as e:
            import sys
            print(f"[ErrorLog Exception Error] Failed to write exception log: {e}", file=sys.stderr)
