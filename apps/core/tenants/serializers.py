from rest_framework import serializers
from apps.core.tenants.models import (
    Tenant, Property, TenantBranding, TenantDomain, 
    TenantConfiguration, TenantIsolationConfig
)
from apps.core.accounts.models import AppUser, UserAssignment
from apps.core.rbac.models import Role, Permission, RolePermission

class TenantSerializer(serializers.ModelSerializer):
    admin_email = serializers.EmailField(write_only=True)
    admin_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    schema_name = serializers.SerializerMethodField(read_only=True)
    domain_url = serializers.SerializerMethodField(read_only=True)
    is_active = serializers.SerializerMethodField(read_only=True)
    created_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Tenant
        fields = '__all__'

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.name or obj.created_by.email or obj.created_by.username
        return "System Admin"

    def get_schema_name(self, obj):
        try:
            return obj.isolation_config.schema_name
        except Exception:
            return obj.subdomain

    def get_domain_url(self, obj):
        try:
            primary_domain = obj.domains.filter(is_primary=True).first()
            if primary_domain and primary_domain.domain:
                return primary_domain.domain
            elif primary_domain:
                return f"{primary_domain.subdomain}.localhost:3000"
        except Exception:
            pass
        return f"{obj.subdomain}.localhost:3000"

    def get_is_active(self, obj):
        return obj.status == 'active'

    def create(self, validated_data):
        admin_email = validated_data.pop('admin_email')
        admin_password = validated_data.pop('admin_password', None) or 'Password123'
        
        # 1. Create Tenant
        tenant = super().create(validated_data)

        # 2. Create TenantDomain
        TenantDomain.objects.create(
            tenant=tenant,
            subdomain=tenant.subdomain,
            domain=f"{tenant.subdomain}.localhost:3000",
            status='ACTIVE'
        )

        # 3. Create TenantBranding
        TenantBranding.objects.create(
            tenant=tenant,
            company_name=tenant.name,
            support_email=admin_email,
            support_phone=''
        )

        # 4. Create TenantConfiguration
        TenantConfiguration.objects.create(
            tenant=tenant,
            timezone=tenant.timezone,
            currency=tenant.currency
        )

        # 5. Create TenantIsolationConfig
        TenantIsolationConfig.objects.create(
            tenant=tenant,
            isolation_mode='SHARED',
            schema_name=tenant.subdomain,
            status='PROVISIONED'
        )

        # 6. Seed Default Roles for the Tenant
        roles_data = [
            ('super_admin', 'Super Admin', 'Full master developer control'),
            ('owner', 'Owner', 'Full property group management'),
            ('general_manager', 'General Manager', 'Full property local operations management'),
            ('front_office_manager', 'Front Office Manager', 'Front desk oversight and checklists'),
            ('front_desk_agent', 'Front Desk Agent', 'Front office checkin/checkout transactions'),
            ('housekeeping_supervisor', 'Housekeeping Supervisor', 'Room status coordination'),
            ('accounts', 'Accounts', 'Invoices and balance settlement processing'),
            ('revenue_manager', 'Revenue Manager', 'Yield optimization configurations'),
        ]
        
        roles = {}
        for r_code, r_name, r_desc in roles_data:
            role, _ = Role.objects.get_or_create(
                tenant=tenant,
                code=r_code,
                defaults={'name': r_name, 'description': r_desc}
            )
            roles[r_code] = role

        # Link Permissions to Roles
        all_perms = list(Permission.objects.all())
        role_permission_mappings = {
            'owner': [p.code for p in all_perms],
            'general_manager': [p.code for p in all_perms if not p.code.startswith('settings:manage')],
            'front_office_manager': [p.code for p in all_perms if p.code.startswith(('reservations:', 'inventory:view', 'billing:', 'crm:', 'reports:view'))],
            'front_desk_agent': ['reservations:view', 'reservations:create', 'reservations:update', 'reservations:checkin', 'reservations:checkout', 'inventory:view', 'billing:view', 'billing:post', 'billing:settle', 'crm:view', 'crm:manage'],
            'housekeeping_supervisor': ['inventory:view', 'inventory:status', 'housekeeping:view', 'housekeeping:assign', 'housekeeping:status', 'maintenance:view', 'maintenance:manage'],
            'accounts': ['billing:view', 'billing:post', 'billing:settle', 'billing:refund', 'rates:view', 'services:view', 'reports:view', 'reports:export'],
            'revenue_manager': ['rates:view', 'rates:manage', 'rates:packages', 'reservations:view', 'reports:view'],
        }

        for r_code, perm_codes in role_permission_mappings.items():
            role = roles.get(r_code)
            if role:
                for p_code in perm_codes:
                    try:
                        perm = Permission.objects.get(code=p_code)
                        RolePermission.objects.get_or_create(role=role, permission=perm)
                    except Permission.DoesNotExist:
                        pass

        # 7. Create Admin User with Owner Role assigned
        owner_role = roles.get('owner')
        admin_user = AppUser.objects.create_user(
            email=admin_email,
            password=admin_password,
            tenant=tenant,
            name=tenant.name,
            username=admin_email.split('@')[0],
            role=owner_role,
            is_active=True
        )

        # 8. Assign Owner Role to the Admin User for this Tenant
        if owner_role:
            UserAssignment.objects.create(
                user=admin_user,
                tenant=tenant,
                role=owner_role
            )

        return tenant

class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = '__all__'
        read_only_fields = ('tenant', 'created_at', 'updated_at', 'deleted_at', 'created_by', 'updated_by')


class SuperadminPropertySerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)

    class Meta:
        model = Property
        fields = [
            'id', 'tenant', 'tenant_name', 'name', 'property_type',
            'address_line_1', 'address_line_2', 'city', 'state', 'country', 'postal_code',
            'contact_email', 'contact_phone', 'currency', 'timezone', 'image_url', 'is_active',
            'description', 'star_rating', 'website', 'check_in_time', 'check_out_time',
            'min_age', 'pets_allowed', 'tax_id', 'google_map_url', 'cancellation_policy',
            'refund_policy', 'house_rules', 'cgst', 'vat', 'city_tax', 'service_charge',
            'luxury_tax', 'amenities', 'website_logo', 'kot_logo', 'photos'
        ]




class TenantBrandingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantBranding
        fields = '__all__'


class TenantDomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantDomain
        fields = '__all__'


class TenantConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantConfiguration
        fields = '__all__'


class TenantIsolationConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantIsolationConfig
        fields = '__all__'

