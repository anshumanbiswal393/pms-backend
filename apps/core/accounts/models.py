import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from apps.core.tenants.models import Tenant

class AppUserManager(BaseUserManager):
    def create_user(self, email, password=None, tenant=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        
        # If username is not provided, generate from email
        if 'username' not in extra_fields or not extra_fields['username']:
            extra_fields['username'] = email.split('@')[0]
            
        user = self.model(email=email, tenant=tenant, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

class AppUser(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    name = models.CharField(max_length=120)
    username = models.CharField(max_length=64)
    email = models.EmailField(max_length=255, unique=True)
    phone = models.CharField(max_length=32, null=True, blank=True)
    avatar_url = models.TextField(null=True, blank=True)
    role = models.ForeignKey('rbac.Role', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    department = models.ForeignKey('common.Department', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    shift = models.ForeignKey('common.Shift', on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    preferred_language = models.CharField(max_length=10, default='en')
    preferred_timezone = models.CharField(max_length=50, default='UTC')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    
    # OTP authentication fields
    otp_secret = models.CharField(max_length=128, null=True, blank=True)
    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Lockout controls
    failed_login_attempts = models.IntegerField(default=0)
    lockout_expires_at = models.DateTimeField(null=True, blank=True)
    
    # Audit logging
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users_created',
        db_constraint=False
    )
    updated_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users_updated',
        db_constraint=False
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = AppUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        unique_together = (
            ('tenant', 'email'),
            ('tenant', 'username'),
        )
        indexes = [
            models.Index(fields=['deleted_at']),
            models.Index(fields=['tenant', 'is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.email})"

    @property
    def password_hash(self):
        return self.password

    @password_hash.setter
    def password_hash(self, value):
        self.password = value

    def delete(self, *args, **kwargs):
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=['deleted_at', 'is_active', 'updated_at'])


class UserInvitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invitations')
    property = models.ForeignKey('tenants.Property', on_delete=models.CASCADE, related_name='invitations', null=True, blank=True)
    email = models.EmailField()
    role = models.ForeignKey('rbac.Role', on_delete=models.CASCADE, related_name='invitations')
    token = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=32, default='PENDING') # PENDING, ACCEPTED, EXPIRED, REVOKED

    class Meta:
        db_table = 'user_invitation'

    def __str__(self):
        return f"Invite to {self.email} for {self.role.code}"


class UserAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name='assignments')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='assignments')
    property = models.ForeignKey('tenants.Property', on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)
    role = models.ForeignKey('rbac.Role', on_delete=models.CASCADE, related_name='assignments', null=True, blank=True)

    class Meta:
        db_table = 'user_assignment'

    def __str__(self):
        return f"{self.user.email} -> {self.tenant.name}:{self.property.name if self.property else 'All'}"


class PasswordPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='password_policies', null=True, blank=True)
    min_length = models.IntegerField(default=8)
    complexity_required = models.BooleanField(default=True)
    expiry_days = models.IntegerField(default=90)

    class Meta:
        db_table = 'password_policy'

    def __str__(self):
        return f"PasswordPolicy ({self.tenant.name if self.tenant else 'Global'})"


class LoginAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name='login_attempts', null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    success = models.BooleanField()
    attempted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_attempt'

    def __str__(self):
        return f"{self.ip_address} -> {'Success' if self.success else 'Failed'}"


class AccountLock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE, related_name='account_lock')
    locked_until = models.DateTimeField()
    reason = models.CharField(max_length=255)

    class Meta:
        db_table = 'account_lock'

    def __str__(self):
        return f"Lock: {self.user.email} until {self.locked_until}"


class UserMFA(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE, related_name='mfa')
    secret = models.CharField(max_length=128)
    method = models.CharField(max_length=32, default='TOTP') # EMAIL, SMS, TOTP
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = 'user_mfa'

    def __str__(self):
        return f"MFA ({self.method}) - {self.user.email} (Enabled: {self.enabled})"


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    device = models.CharField(max_length=255, null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    # JWT tracking fields
    refresh_token_jti = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    access_token_jti = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'user_session'

    def __str__(self):
        return f"Session: {self.user.email} ({self.device})"


class IPWhitelist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ip_whitelist')
    ip_address = models.CharField(max_length=45)
    description = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'ip_whitelist'

    def __str__(self):
        return f"Whitelist: {self.ip_address} for {self.tenant.name}"


class SSOConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='sso_config')
    provider = models.CharField(max_length=32) # OAUTH, SAML
    client_id = models.CharField(max_length=255, null=True, blank=True)
    client_secret = models.CharField(max_length=255, null=True, blank=True)
    metadata_url = models.URLField(max_length=512, null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = 'sso_configuration'

    def __str__(self):
        return f"SSO Provider ({self.provider}) for {self.tenant.name}"


class PendingLoginConfirmation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name='pending_logins')
    ip_address = models.CharField(max_length=45)
    location = models.CharField(max_length=255, default="New Delhi, India")
    device_spec = models.CharField(max_length=512)
    status = models.CharField(max_length=32, default="pending")  # pending, approved, rejected
    created_at = models.DateTimeField(auto_now_add=True)
    tokens = models.JSONField(default=dict, blank=True)  # Stores the JWT tokens temporarily until confirmed

    class Meta:
        db_table = 'pending_login_confirmation'

    def __str__(self):
        return f"Pending login for {self.user.email} - Status: {self.status}"


class SuperadminIPWhitelist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ip_address = models.CharField(max_length=45)
    description = models.CharField(max_length=255, null=True, blank=True)
    created_by = models.ForeignKey(AppUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='superadmin_ip_whitelists')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'superadmin_ip_whitelist'
        ordering = ['-created_at']

    def __str__(self):
        return f"Superadmin Whitelist: {self.ip_address} ({'Active' if self.is_active else 'Inactive'})"


