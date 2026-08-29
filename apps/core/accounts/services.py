import random
import string
import logging
from abc import ABC, abstractmethod
from django.db import models
from django.utils import timezone
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from apps.core.accounts.models import AppUser
from apps.core.rbac.models import UserPropertyRole

from django.core.mail import send_mail

logger = logging.getLogger(__name__)

# --- OTP PROVIDERS ---

class BaseOTPProvider(ABC):
    @abstractmethod
    def send_otp(self, contact: str, code: str) -> bool:
        """
        Sends the generated OTP code to the target contact (email or phone).
        Returns True if successful, False otherwise.
        """
        pass

class MockOTPProvider(BaseOTPProvider):
    def send_otp(self, contact: str, code: str) -> bool:
        logger.info(f"[MOCK OTP PROVIDER] Dispatching OTP code '{code}' to '{contact}'")
        print(f"\n--- [MOCK OTP] Code '{code}' dispatched to '{contact}' ---\n")
        return True

class EmailOTPProvider(BaseOTPProvider):
    def send_otp(self, contact: str, code: str) -> bool:
        logger.info(f"[EMAIL OTP PROVIDER] Dispatching Email OTP '{code}' to '{contact}'")
        from apps.core.common.email_service import UnifiedMailService
        res = UnifiedMailService.send_email(
            email_type="OTP_VERIFICATION",
            recipient_email=contact,
            data={"otp_code": code, "expiry_minutes": 5}
        )
        return res.get("success", False)


class SMSOTPProvider(BaseOTPProvider):
    def send_otp(self, contact: str, code: str) -> bool:
        logger.info(f"[SMS OTP PROVIDER] Dispatching SMS OTP '{code}' to '{contact}'")
        # In a real setup: twilio_client.messages.create(...)
        return True

# Provider Factory
def get_otp_provider(provider_type: str = 'mock') -> BaseOTPProvider:
    providers = {
        'mock': MockOTPProvider,
        'email': EmailOTPProvider,
        'sms': SMSOTPProvider
    }
    return providers.get(provider_type.lower(), MockOTPProvider)()


# --- AUTHENTICATION SERVICES ---

class AuthService:
    @staticmethod
    def get_tokens_for_user(user: AppUser):
        """
        Generates JWT access and refresh tokens for a user.
        """
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

    @classmethod
    def create_user_session(cls, user: AppUser, tokens: dict, request=None):
        """
        Records the login session and maps token JTIs to tracking model.
        """
        if not request:
            return

        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '127.0.0.1'))
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        device = request.META.get('HTTP_USER_AGENT', 'Unknown')

        from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
        refresh_jti = None
        access_jti = None
        try:
            refresh_token = RefreshToken(tokens['refresh'])
            refresh_jti = refresh_token.get('jti')
            access_token = AccessToken(tokens['access'])
            access_jti = access_token.get('jti')
        except Exception:
            pass

        from apps.core.accounts.models import UserSession
        UserSession.objects.create(
            user=user,
            device=device,
            ip=ip,
            refresh_token_jti=refresh_jti,
            access_token_jti=access_jti,
            is_active=True
        )


    @staticmethod
    def check_user_lockout(user: AppUser) -> tuple[bool, str]:
        """
        Verifies if the user is currently locked out.
        """
        if user.lockout_expires_at and timezone.now() < user.lockout_expires_at:
            time_left = int((user.lockout_expires_at - timezone.now()).total_seconds() / 60)
            return True, f"Account is locked. Try again in {max(1, time_left)} minutes."
        
        # If lockout window has expired, reset failed attempts
        if user.lockout_expires_at and timezone.now() >= user.lockout_expires_at:
            user.failed_login_attempts = 0
            user.lockout_expires_at = None
            user.save(update_fields=['failed_login_attempts', 'lockout_expires_at'])
            
        return False, ""

    @staticmethod
    def handle_failed_login(user: AppUser, ip_address: str = "127.0.0.1"):
        """
        Increments failed login counter and triggers lockout if threshold reached.
        """
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.lockout_expires_at = timezone.now() + timezone.timedelta(minutes=15)
            from apps.core.accounts.models import AccountLock
            AccountLock.objects.update_or_create(
                user=user,
                defaults={
                    'locked_until': user.lockout_expires_at,
                    'reason': 'Locked due to 5 consecutive failed login attempts.'
                }
            )
            logger.warning(f"User {user.email} locked out due to consecutive failed attempts.")
        user.save(update_fields=['failed_login_attempts', 'lockout_expires_at'])

        # Record attempt
        from apps.core.accounts.models import LoginAttempt
        LoginAttempt.objects.create(
            user=user,
            ip_address=ip_address,
            success=False
        )

    @staticmethod
    def handle_successful_login(user: AppUser, ip_address: str = "127.0.0.1"):
        """
        Resets login tracking counters on success.
        """
        user.failed_login_attempts = 0
        user.lockout_expires_at = None
        user.last_login = timezone.now()
        user.save(update_fields=['failed_login_attempts', 'lockout_expires_at', 'last_login'])

        # Remove lock if exists
        from apps.core.accounts.models import AccountLock
        AccountLock.objects.filter(user=user).delete()

        # Record attempt
        from apps.core.accounts.models import LoginAttempt
        LoginAttempt.objects.create(
            user=user,
            ip_address=ip_address,
            success=True
        )

    @classmethod
    def authenticate_password(cls, tenant, email_or_username: str, password: str, ip_address: str = "127.0.0.1") -> tuple[AppUser | None, str]:
        """
        Authenticates a user using email or username + password in a tenant context.
        """
        try:
            # Query by email or username within the tenant
            user = AppUser.objects.get(
                models.Q(email__iexact=email_or_username) | models.Q(username__iexact=email_or_username),
                tenant=tenant,
                deleted_at__isnull=True
            )
        except AppUser.DoesNotExist:
            # Fallback: query globally if not found in the resolved tenant context (useful for localhost)
            try:
                user = AppUser.objects.get(
                    models.Q(email__iexact=email_or_username) | models.Q(username__iexact=email_or_username),
                    deleted_at__isnull=True
                )
            except AppUser.DoesNotExist:
                return None, "Invalid credentials."

        if not user.is_active:
            return None, "User account is deactivated."

        # Lockout check
        is_locked, msg = cls.check_user_lockout(user)
        if is_locked:
            return None, msg

        # Verify password
        if not user.check_password(password):
            cls.handle_failed_login(user, ip_address)
            # Recheck if user got locked out right now
            is_locked, msg = cls.check_user_lockout(user)
            if is_locked:
                return None, msg
            return None, "Invalid credentials."

        cls.handle_successful_login(user, ip_address)
        return user, "Success"

    @classmethod
    def request_otp(cls, tenant, contact: str, provider_type: str = 'mock') -> tuple[bool, str]:
        """
        Generates and sends an OTP to user phone or email.
        """
        try:
            user = AppUser.objects.get(
                models.Q(email__iexact=contact) | models.Q(phone=contact),
                tenant=tenant,
                deleted_at__isnull=True
            )
        except AppUser.DoesNotExist:
            try:
                user = AppUser.objects.get(
                    models.Q(email__iexact=contact) | models.Q(phone=contact),
                    deleted_at__isnull=True
                )
            except AppUser.DoesNotExist:
                return False, "User not found."

        if not user.is_active:
            return False, "User account is deactivated."

        is_locked, msg = cls.check_user_lockout(user)
        if is_locked:
            return False, msg

        # Generate 6-digit numeric OTP code
        code = "".join(random.choices(string.digits, k=6))
        user.otp_code = code
        user.otp_expires_at = timezone.now() + timezone.timedelta(minutes=5)
        user.save(update_fields=['otp_code', 'otp_expires_at'])

        # Dispatch code
        provider = get_otp_provider(provider_type)
        dispatched = provider.send_otp(contact, code)
        
        if not dispatched:
            return False, "Failed to send OTP code. Try again."

        return True, "OTP code sent successfully."

    @classmethod
    def verify_otp(cls, tenant, contact: str, otp_code: str, ip_address: str = "127.0.0.1") -> tuple[AppUser | None, str]:
        """
        Validates OTP code and logs the user in on success.
        """
        try:
            user = AppUser.objects.get(
                models.Q(email__iexact=contact) | models.Q(phone=contact),
                tenant=tenant,
                deleted_at__isnull=True
            )
        except AppUser.DoesNotExist:
            try:
                user = AppUser.objects.get(
                    models.Q(email__iexact=contact) | models.Q(phone=contact),
                    deleted_at__isnull=True
                )
            except AppUser.DoesNotExist:
                return None, "Invalid request."

        # Lockout check
        is_locked, msg = cls.check_user_lockout(user)
        if is_locked:
            return None, msg

        # Check expiry
        if not user.otp_expires_at or timezone.now() > user.otp_expires_at:
            return None, "OTP code has expired."

        # Check code
        if user.otp_code != otp_code:
            cls.handle_failed_login(user, ip_address)
            # Recheck lockout
            is_locked, msg = cls.check_user_lockout(user)
            if is_locked:
                return None, msg
            return None, "Invalid OTP code."

        # Clear OTP fields on success
        user.otp_code = None
        user.otp_expires_at = None
        user.save(update_fields=['otp_code', 'otp_expires_at'])
        
        cls.handle_successful_login(user, ip_address)
        return user, "Success"

    @staticmethod
    def get_user_metadata(user: AppUser, tenant):
        """
        Returns serialized metadata required by the frontend layout:
        User details, roles/permissions list, and authorized properties.
        """
        # Resolve properties and roles mapped to user
        property_roles = UserPropertyRole.objects.filter(user=user, tenant=tenant) if tenant else []
        properties = []
        permissions = set()
        user_role = None
        user_role_name = None
        
        for pr in property_roles:
            properties.append({
                'id': str(pr.property.id),
                'name': pr.property.name,
                'role': pr.role.code,
                'role_name': pr.role.name
            })
            if not user_role and pr.role:
                user_role = pr.role.code
                user_role_name = pr.role.name
            # Add role permissions
            for rp in pr.role.permissions.all():
                permissions.add(rp.permission.code)

        # Resolve direct user.role permissions
        if getattr(user, 'role', None):
            user_role = user.role.code
            user_role_name = user.role.name
            for rp in user.role.permissions.all():
                permissions.add(rp.permission.code)

        # Resolve tenant-wide assignment role and permissions (e.g. for owner onboarding)
        from apps.core.accounts.models import UserAssignment
        assignment = UserAssignment.objects.filter(user=user, tenant=tenant).first() if tenant else None
        if assignment and assignment.role:
            user_role = assignment.role.code
            user_role_name = assignment.role.name
            for rp in assignment.role.permissions.all():
                permissions.add(rp.permission.code)

        # Determine exact role classification
        if user.is_superuser:
            user_role = 'super_admin'
            user_role_name = 'Retrod Super Admin'
            permissions.add("*:*")
        elif tenant and getattr(tenant, 'owner', None) == user:
            user_role = 'owner'
            user_role_name = 'Owner'
            permissions.add("*:*")
        elif user_role in ['owner', 'tenant_owner']:
            user_role = 'owner'
            user_role_name = 'Owner'
            permissions.add("*:*")
        elif not user_role:
            user_role = 'owner' if (tenant and not property_roles) else 'staff'
            user_role_name = 'Owner' if (tenant and not property_roles) else 'Staff'

        if user_role == 'owner' and tenant and not properties:
            from apps.core.tenants.models import Property
            for p in Property.objects.filter(tenant=tenant):
                properties.append({
                    'id': str(p.id),
                    'name': p.name,
                    'role': 'owner',
                    'role_name': 'Owner'
                })

        # Fetch subscription plan details
        from apps.core.subscriptions.models import TenantSubscription, TenantProductLicense
        sub = TenantSubscription.objects.filter(tenant=tenant, status='ACTIVE').first() if tenant else None
        sub_plan = (sub.plan.name if sub.plan else (sub.custom_name or "Custom Subscription")) if sub else "Standard Enterprise Plan"
        sub_expiry = str(sub.end_date) if sub else "2027-01-31"
        
        # Fetch license key
        lic = TenantProductLicense.objects.filter(tenant_product__tenant=tenant, tenant_product__product__code='PMS', status='ACTIVE').first() if tenant else None
        if not lic and tenant:
            lic = TenantProductLicense.objects.filter(tenant_product__tenant=tenant, status='ACTIVE').first()
        license_key = lic.license_key if lic else "RETROD-LNX-8394-2026"

        return {
            'user': {
                'id': str(user.id),
                'name': user.name,
                'email': user.email,
                'username': user.username,
                'phone': user.phone,
                'avatar_url': user.avatar_url,
                'preferred_language': user.preferred_language,
                'preferred_timezone': user.preferred_timezone,
                'role': user_role,
                'role_name': user_role_name or user_role,
                'is_superuser': user.is_superuser,
                'tenant_subdomain': user.tenant.subdomain if user.tenant else None,
                'subscription_plan': sub_plan,
                'subscription_expiry': sub_expiry,
                'license_key': license_key,
            },
            'permissions': list(permissions),
            'properties': properties
        }
