from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from apps.core.tenants.models import Tenant
import re

class TenantResolutionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        path = request.path_info
        
        # Paths that bypass tenant resolution
        bypass_paths = [
            '/admin/',
            '/api/schema/',
            '/api/auth/',
            '/favicon.ico',
        ]
        
        if any(path.startswith(bp) for bp in bypass_paths):
            request.tenant = None
            return None

        tenant = None

        # 1. First priority: Check JWT Authorization token to resolve authenticated user's tenant
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token_str = auth_header.split(' ')[1]
                from rest_framework_simplejwt.tokens import AccessToken
                from django.contrib.auth import get_user_model
                token = AccessToken(token_str)
                user_id = token.payload.get('user_id')
                if user_id:
                    User = get_user_model()
                    user = User.objects.select_related('tenant').filter(id=user_id).first()
                    if user and user.tenant:
                        tenant = user.tenant
            except Exception:
                pass

        # 2. Second priority: Explicit Tenant ID Header (e.g. from superadmin or switcher)
        if not tenant:
            tenant_id = request.headers.get('X-Tenant-ID') or request.GET.get('tenant_id')
            if tenant_id:
                try:
                    tenant = Tenant.objects.filter(id=tenant_id).first()
                except Exception:
                    pass

        # 3. Third priority: Subdomain Header or Query Param / Host
        if not tenant:
            subdomain = request.headers.get('X-Tenant-Subdomain')
            if not subdomain:
                host = request.get_host().split(':')[0]
                is_ip_or_localhost = host == 'localhost' or re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', host)
                if not is_ip_or_localhost:
                    host_parts = host.split('.')
                    if len(host_parts) >= 3:
                        subdomain = host_parts[0]
            if not subdomain:
                subdomain = request.GET.get('subdomain')

            if subdomain and subdomain != 'grandpalace':
                tenant = Tenant.objects.filter(subdomain=subdomain).first()

        # 4. Fallback in DEBUG mode only if not authenticated and no subdomain matched
        if not tenant and settings.DEBUG:
            tenant = Tenant.objects.first()

        if not tenant:
            request.tenant = None
            return None

        # 5. Check tenant status
        if tenant.status == 'suspended':
            return JsonResponse({'error': 'Tenant account is suspended.'}, status=403)
        elif tenant.status == 'terminated':
            return JsonResponse({'error': 'Tenant account has been terminated.'}, status=403)
        elif tenant.status != 'active':
            return JsonResponse({'error': 'Tenant account is inactive.'}, status=403)

        request.tenant = tenant
        return None
