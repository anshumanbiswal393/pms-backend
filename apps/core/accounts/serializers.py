from rest_framework import serializers
from apps.core.accounts.models import (
    AppUser, UserInvitation, UserAssignment, PasswordPolicy, LoginAttempt,
    AccountLock, UserMFA, UserSession, IPWhitelist, SSOConfiguration
)

class AppUserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    shift_name = serializers.CharField(source='shift.name', read_only=True)
    password = serializers.CharField(write_only=True, required=False)

    subscription_plan = serializers.SerializerMethodField()
    subscription_expiry = serializers.SerializerMethodField()
    license_key = serializers.SerializerMethodField()

    def get_subscription_plan(self, obj):
        if not obj.tenant:
            return "Platform Admin"
        from apps.core.subscriptions.models import TenantSubscription
        sub = TenantSubscription.objects.filter(tenant=obj.tenant, status='ACTIVE').first()
        return sub.plan.name if sub else "Lite Plan"

    def get_subscription_expiry(self, obj):
        if not obj.tenant:
            return "Unlimited"
        from apps.core.subscriptions.models import TenantSubscription
        sub = TenantSubscription.objects.filter(tenant=obj.tenant, status='ACTIVE').first()
        return str(sub.end_date) if sub else "N/A"

    def get_license_key(self, obj):
        if not obj.tenant:
            return "PLATFORM-ADMIN-KEY"
        from apps.core.subscriptions.models import TenantProductLicense
        lic = TenantProductLicense.objects.filter(tenant_product__tenant=obj.tenant, tenant_product__product__code='PMS', status='ACTIVE').first()
        if not lic:
            lic = TenantProductLicense.objects.filter(tenant_product__tenant=obj.tenant, status='ACTIVE').first()
        return lic.license_key if lic else "N/A"


    assigned_properties = serializers.SerializerMethodField()
    assigned_property_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    def get_assigned_properties(self, obj):
        assignments = UserAssignment.objects.filter(user=obj).select_related('property')
        res = []
        for a in assignments:
            if a.property:
                res.append({
                    'id': str(a.property.id),
                    'name': a.property.name,
                    'city': a.property.city
                })
        return res

    class Meta:
        model = AppUser
        fields = (
            'id', 'tenant', 'name', 'username', 'email', 'phone', 
            'avatar_url', 'preferred_language', 'preferred_timezone', 
            'is_active', 'is_staff', 'role', 'role_name', 'department', 
            'department_name', 'shift', 'shift_name', 'created_at', 'updated_at', 'password',
            'subscription_plan', 'subscription_expiry', 'license_key',
            'assigned_properties', 'assigned_property_ids'
        )
        read_only_fields = ('id', 'created_at', 'updated_at', 'is_staff')

    def create(self, validated_data):
        assigned_prop_ids = validated_data.pop('assigned_property_ids', None)
        password = validated_data.pop('password', None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()

        if assigned_prop_ids is not None and user.tenant:
            from apps.core.tenants.models import Property
            UserAssignment.objects.filter(user=user).delete()
            for pid in assigned_prop_ids:
                prop_obj = Property.objects.filter(id=pid, tenant=user.tenant).first()
                if prop_obj:
                    UserAssignment.objects.create(
                        user=user,
                        tenant=user.tenant,
                        property=prop_obj,
                        role=user.role
                    )
        return user

    def update(self, instance, validated_data):
        assigned_prop_ids = validated_data.pop('assigned_property_ids', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()

        if assigned_prop_ids is not None and instance.tenant:
            from apps.core.tenants.models import Property
            UserAssignment.objects.filter(user=instance).delete()
            for pid in assigned_prop_ids:
                prop_obj = Property.objects.filter(id=pid, tenant=instance.tenant).first()
                if prop_obj:
                    UserAssignment.objects.create(
                        user=instance,
                        tenant=instance.tenant,
                        property=prop_obj,
                        role=instance.role
                    )
        return instance

class PlatformUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppUser
        fields = (
            'id', 'tenant', 'name', 'username', 'email', 'phone', 
            'avatar_url', 'preferred_language', 'preferred_timezone', 
            'is_active', 'is_staff', 'is_superuser', 'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class AppUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = AppUser
        fields = (
            'id', 'tenant', 'name', 'username', 'email', 'phone', 
            'avatar_url', 'preferred_language', 'preferred_timezone', 
            'is_active', 'password'
        )
        read_only_fields = ('id',)

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        email = validated_data.pop('email', None)
        user = AppUser.objects.create_user(
            email=email,
            password=password,
            **validated_data
        )
        return user

class PasswordLoginRequestSerializer(serializers.Serializer):
    email_or_username = serializers.CharField(required=True, help_text="Email or Username of staff member")
    password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

class RequestOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, help_text="Email to dispatch code")
    phone = serializers.CharField(required=False, help_text="Phone to dispatch code")
    contact = serializers.CharField(required=False, help_text="General contact identifier")
    provider = serializers.ChoiceField(choices=['mock', 'email', 'sms'], required=False, help_text="OTP provider backend to use (defaults to configured system provider)")

class VerifyOTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    contact = serializers.CharField(required=False)
    otp_code = serializers.CharField(required=True, help_text="6-digit verification code")

class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True, help_text="SimpleJWT refresh token to blacklist")


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})
    new_password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True, help_text="Email of user requesting password reset")
    reset_method = serializers.ChoiceField(choices=['email', 'otp'], default='email', help_text="Reset flow type")


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    token = serializers.CharField(required=True, help_text="One-time token or OTP code received")
    new_password = serializers.CharField(required=True, write_only=True, style={'input_type': 'password'})

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        return value


class UserInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInvitation
        fields = '__all__'


class UserAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAssignment
        fields = '__all__'


class PasswordPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PasswordPolicy
        fields = '__all__'


class LoginAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginAttempt
        fields = '__all__'


class AccountLockSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountLock
        fields = '__all__'


class UserMFASerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMFA
        fields = '__all__'


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = '__all__'


class IPWhitelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPWhitelist
        fields = '__all__'


class SSOConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SSOConfiguration
        fields = '__all__'


