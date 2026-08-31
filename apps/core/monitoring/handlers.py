import logging
import threading
import traceback
import sys

_in_logging = threading.local()


class DatabaseErrorLogHandler(logging.Handler):
    """
    Captures all python logging ERROR and CRITICAL events across the entire application
    (console/terminal logs, background tasks, Celery jobs, service exceptions, etc.)
    and automatically persists them to the ErrorLog database table.
    """

    def emit(self, record):
        # Prevent recursive logging loops
        if getattr(_in_logging, 'active', False):
            return

        _in_logging.active = True
        try:
            from apps.core.monitoring.models import ErrorLog
            from django.db import connection

            # Only attempt if database connection is available
            if connection.connection is None and not connection.settings_dict:
                return

            # Format log message
            msg = record.getMessage()

            # Extract exception info if present
            stack_trace = None
            if record.exc_info:
                stack_trace = "".join(traceback.format_exception(*record.exc_info))
            elif record.stack_info:
                stack_trace = str(record.stack_info)

            # Extract request metadata if attached to record (e.g. django.request logger)
            request = getattr(record, 'request', None)
            path = getattr(request, 'path_info', None) if request else None
            method = getattr(request, 'method', None) if request else None
            tenant = getattr(request, 'tenant', None) if request else None
            tenant_id = str(tenant.id) if tenant and hasattr(tenant, 'id') else None
            user = getattr(request, 'user', None) if request else None
            user_id = str(user.id) if user and hasattr(user, 'id') and getattr(user, 'is_authenticated', False) else None
            user_email = getattr(user, 'email', None) if user and getattr(user, 'is_authenticated', False) else None
            
            ip_address = None
            if request and hasattr(request, 'META'):
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(',')[0].strip()
                else:
                    ip_address = request.META.get('REMOTE_ADDR')

            error_type = record.name
            if record.exc_info and record.exc_info[0]:
                error_type = record.exc_info[0].__name__

            file_info = f"{record.filename}:{record.lineno} in {record.funcName}()"

            ErrorLog.objects.create(
                error_type=error_type[:255],
                error_message=str(msg)[:4000] if msg else "Empty Error Log Message",
                stack_trace=stack_trace,
                method=method[:10] if method else None,
                path=path[:512] if path else None,
                status_code=500,
                tenant_id=tenant_id,
                user_id=user_id,
                user_email=user_email[:255] if user_email else None,
                ip_address=ip_address,
                context_data={
                    "logger_name": record.name,
                    "log_level": record.levelname,
                    "file_location": file_info,
                    "module": record.module,
                    "process_id": record.process,
                    "thread_name": record.threadName,
                }
            )
        except Exception:
            # Silently pass to avoid breaking terminal output
            pass
        finally:
            _in_logging.active = False
