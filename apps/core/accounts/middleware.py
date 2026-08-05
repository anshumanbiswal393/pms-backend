from django.http import JsonResponse
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from apps.core.accounts.models import AccountLock, IPWhitelist, SuperadminIPWhitelist

class AccountLockoutMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user_id = None
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            user_id = user.id
        else:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                try:
                    token_str = auth_header.split(' ')[1]
                    from rest_framework_simplejwt.tokens import AccessToken
                    token = AccessToken(token_str)
                    user_id = token.get('user_id')
                except Exception:
                    pass

        if user_id:
            lock = AccountLock.objects.filter(user_id=user_id, locked_until__gt=timezone.now()).first()
            if lock:
                return JsonResponse({
                    'error': 'Account is temporarily locked.',
                    'reason': lock.reason,
                    'locked_until': lock.locked_until.isoformat()
                }, status=403)
        return None


class IPWhitelistMiddleware(MiddlewareMixin):
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def process_request(self, request):
        path = request.path_info
        if path.startswith('/admin/') or path.startswith('/api/schema/'):
            return None

        client_ip = self.get_client_ip(request)

        # Check Superadmin IP Whitelisting for superadmin routes
        is_superadmin_route = 'superadmin' in path
        if is_superadmin_route:
            active_superadmin_whitelists = SuperadminIPWhitelist.objects.filter(is_active=True)
            if active_superadmin_whitelists.exists():
                allowed_ips = [w.ip_address for w in active_superadmin_whitelists]
                # Allow local loopback addresses (127.0.0.1, ::1) and 0.0.0.0 automatically
                local_ips = ['127.0.0.1', '::1', 'localhost', '0.0.0.0']
                if client_ip not in allowed_ips and not any(lip in allowed_ips for lip in local_ips) and client_ip not in local_ips:
                    return JsonResponse({
                        'error': f'Access denied: IP {client_ip} is not whitelisted for Platform Superadmin operations.'
                    }, status=403)

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return None

        # Check if IP whitelist enforcement is enabled for the tenant
        config = getattr(tenant, 'configuration', None)
        if not config or not getattr(config, 'enforce_ip_whitelist', False):
            return None

        # Retrieve whitelist for tenant
        whitelist = IPWhitelist.objects.filter(tenant=tenant)
        if not whitelist.exists():
            return None

        allowed_ips = [w.ip_address for w in whitelist]

        # Simple string inclusion or exact match
        if client_ip not in allowed_ips and '0.0.0.0' not in allowed_ips:
            return JsonResponse({
                'error': f'Access denied: IP {client_ip} is not whitelisted for tenant {tenant.name}.'
            }, status=403)

        return None

