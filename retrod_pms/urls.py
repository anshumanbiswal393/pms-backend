from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Import Views
from apps.core.tenants.views import (
    TenantViewSet, PropertyViewSet, TenantBrandingViewSet, TenantDomainViewSet,
    TenantConfigurationViewSet, TenantIsolationConfigViewSet, SuperadminPropertyViewSet,
    RequestSubscriptionView
)
from apps.features.properties.views import (
    PropertyConfigurationViewSet, PropertyContactViewSet
)
from apps.core.rbac.views import RoleViewSet, PermissionViewSet, RolePermissionViewSet, UserPropertyRoleViewSet
from apps.core.accounts.views import (
    UserViewSet, PasswordLoginView, RequestOTPView, 
    VerifyOTPView, LogoutView, CurrentUserView,
    ChangePasswordView, ForgotPasswordView, ResetPasswordView,
    UserInviteView, UserResendInvitationView, UserInvitationsListView,
    UserAssignTenantView, UserAssignPropertyView, UserAssignmentsListView,
    PasswordPolicyViewSet, LoginAttemptViewSet, FailedLoginsListView,
    LockUserView, UnlockUserView, MFAEnableView, MFADisableView, MFAVerifyView,
    SessionViewSet, SessionRevokeView, IPWhitelistViewSet, SSOConfigurationViewSet,
    PlatformUserViewSet, DashboardStatsView, LogoutAllSessionsView, ConfirmLoginView,
    CheckConfirmationStatusView, SuperadminIPWhitelistViewSet
)
from apps.core.audit.views import AuditLogViewSet, SuperadminAuditLogViewSet
from apps.features.inventory.views import BuildingViewSet, FloorViewSet, FloorPlanViewSet
from apps.core.subscriptions.views import (
    ProductViewSet, ProductFeatureViewSet, LicenseViewSet,
    EntitlementViewSet, UsageViewSet
)
from apps.core.common.views import (
    SystemLanguageViewSet, SystemTaxViewSet,
    SystemDocumentTypeViewSet, SystemCurrencyViewSet,
    SystemDateFormatViewSet, SystemTimeFormatViewSet,
    DepartmentViewSet, ShiftViewSet, OccupancyTypeViewSet,
    BookingSourceViewSet, PaymentGatewayViewSet, TenantPaymentGatewayViewSet,
    UnifiedSendEmailView
)
from apps.core.common.razorpay_views import CreateRazorpayOrderView, VerifyRazorpaySignatureView

# Initialize DRF Router
router = DefaultRouter()

router.register(r'superadmin-payment-gateways', PaymentGatewayViewSet, basename='superadminpaymentgateways')
router.register(r'tenant-payment-gateways', TenantPaymentGatewayViewSet, basename='tenantpaymentgateways')

# Tenants & Properties
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'superadmin-properties', SuperadminPropertyViewSet, basename='superadminproperty')

router.register(r'tenant-branding', TenantBrandingViewSet, basename='tenantbranding')
router.register(r'tenant-domains', TenantDomainViewSet, basename='tenantdomain')
router.register(r'tenant-configurations', TenantConfigurationViewSet, basename='tenantconfiguration')
router.register(r'tenant-isolation', TenantIsolationConfigViewSet, basename='tenantisolation')
router.register(r'property-configurations', PropertyConfigurationViewSet, basename='propertyconfiguration')
router.register(r'property-contacts', PropertyContactViewSet, basename='propertycontact')

# RBAC
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'permissions', PermissionViewSet, basename='permission')
router.register(r'role-permissions', RolePermissionViewSet, basename='rolepermission')
router.register(r'user-property-roles', UserPropertyRoleViewSet, basename='userpropertyrole')

# Accounts
router.register(r'users', UserViewSet, basename='user')
router.register(r'superadmin-users', PlatformUserViewSet, basename='superadminuser')
router.register(r'superadmin-ip-whitelist', SuperadminIPWhitelistViewSet, basename='superadminipwhitelist')

# Audit Logs
router.register(r'audit-logs', AuditLogViewSet, basename='auditlog')
router.register(r'superadmin-audit-logs', SuperadminAuditLogViewSet, basename='superadminauditlog')


# Building & Floor Management
router.register(r'buildings', BuildingViewSet, basename='building')
router.register(r'floors', FloorViewSet, basename='floor')
router.register(r'floor-plans', FloorPlanViewSet, basename='floorplan')

# Product Access & License Engine
router.register(r'products', ProductViewSet, basename='main_product')
router.register(r'product-features', ProductFeatureViewSet, basename='main_product_feature')
router.register(r'licenses', LicenseViewSet, basename='main_license')
router.register(r'entitlements', EntitlementViewSet, basename='main_entitlement')
router.register(r'usage', UsageViewSet, basename='main_usage')
router.register(r'superadmin-languages', SystemLanguageViewSet, basename='superadminlanguages')
router.register(r'superadmin-taxes', SystemTaxViewSet, basename='superadmintaxes')
router.register(r'superadmin-documents', SystemDocumentTypeViewSet, basename='superadmindocuments')

router.register(r'superadmin-currencies', SystemCurrencyViewSet, basename='superadmincurrencies')
router.register(r'superadmin-date-formats', SystemDateFormatViewSet, basename='superadmindateformats')
router.register(r'superadmin-time-formats', SystemTimeFormatViewSet, basename='superadmintimeformats')
router.register(r'superadmin-departments', DepartmentViewSet, basename='superadmindepartments')
router.register(r'superadmin-shifts', ShiftViewSet, basename='superadminshifts')
router.register(r'superadmin-occupancy-types', OccupancyTypeViewSet, basename='superadminoccupancytypes')
router.register(r'superadmin-booking-sources', BookingSourceViewSet, basename='superadminbookingsources')

from django.http import JsonResponse

def home_status_view(request):
    return JsonResponse({"status": "healthy", "service": "Retrod PMS API"})

urlpatterns = [
    path('', home_status_view, name='home_status'),
    path('admin/', admin.site.urls),
    
    # Base Viewsets
    path('api/', include(router.urls)),
    
    # Inventory Domain Endpoints
    path('api/inventory/', include('apps.features.inventory.urls')),
    
    # Availability Domain Endpoints
    path('api/', include('apps.features.availability.urls')),
    
    # Rate Management Domain Endpoints
    path('api/rates/', include('apps.features.rates.urls')),
    
    # Guest CRM Domain Endpoints
    path('api/crm/', include('apps.features.crm.urls')),
    
    # B2B Partners Endpoint
    path('api/b2b/', include('apps.features.b2b.urls')),
    
    # Billing & Financial Adjustments Domain Endpoints
    path('api/billing/', include('apps.features.billing.urls')),
    
    # Global Reference Data Endpoints
    path('api/reference/', include('apps.core.reference.urls')),

    # Unified Central Email Service Endpoint
    path('api/common/send-email/', UnifiedSendEmailView.as_view(), name='unified_send_email'),
    path('api/send-email/', UnifiedSendEmailView.as_view(), name='unified_send_email_alias'),

    # Reservation Domain Endpoints
    path('api/reservations/', include('apps.features.reservations.urls')),

    # Housekeeping Management Endpoints
    path('api/housekeeping/', include('apps.features.housekeeping.urls')),

    # Subscription & Entitlement Module Endpoints
    path('api/subscriptions/', include('apps.core.subscriptions.urls')),

    # Asset Management Endpoints
    path('api/assets/', include('apps.features.assets.urls')),

    # Maintenance Management Endpoints
    path('api/maintenance/', include('apps.features.maintenance.urls')),

    # Linen Management Endpoints
    path('api/linen/', include('apps.features.linen.urls')),

    # Lost & Found Management Endpoints
    path('api/lost-found/', include('apps.features.lost_found.urls')),

    # Compliance & Governance Endpoints
    path('api/compliance/', include('apps.core.compliance.urls')),

    # Monitoring & Administration Endpoints
    path('api/admin/', include('apps.core.monitoring.urls')),
    path('api/dashboard-stats/', DashboardStatsView.as_view(), name='dashboard_stats'),
    
    # Custom Auth Endpoints
    path('api/auth/login/', PasswordLoginView.as_view(), name='password_login'),
    path('api/auth/request-otp/', RequestOTPView.as_view(), name='request_otp'),
    path('api/auth/verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('api/auth/confirm-login/', ConfirmLoginView.as_view(), name='confirm_login'),
    path('api/auth/check-confirmation-status/', CheckConfirmationStatusView.as_view(), name='check_confirmation_status'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/auth/me/', CurrentUserView.as_view(), name='current_user'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('api/auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('api/auth/reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    
    # User Invitation & Assignment
    path('api/users/invite/', UserInviteView.as_view(), name='user_invite'),
    path('api/users/resend-invitation/', UserResendInvitationView.as_view(), name='user_resend_invite'),
    path('api/users/invitations/', UserInvitationsListView.as_view(), name='user_invitations_list'),
    path('api/users/assign-tenant/', UserAssignTenantView.as_view(), name='user_assign_tenant'),
    path('api/users/assign-property/', UserAssignPropertyView.as_view(), name='user_assign_property'),
    path('api/users/assignments/', UserAssignmentsListView.as_view(), name='user_assignments_list'),

    # Security & Protection
    path('api/security/password-policy/', PasswordPolicyViewSet.as_view({'get': 'list', 'put': 'update'}), name='password_policy'),
    path('api/security/login-attempts/', LoginAttemptViewSet.as_view({'get': 'list'}), name='login_attempts'),
    path('api/security/failed-logins/', FailedLoginsListView.as_view(), name='failed_logins'),
    path('api/security/lock-user/', LockUserView.as_view(), name='lock_user'),
    path('api/security/unlock-user/', UnlockUserView.as_view(), name='unlock_user'),
    
    # MFA & Sessions
    path('api/security/mfa/enable/', MFAEnableView.as_view(), name='mfa_enable'),
    path('api/security/mfa/disable/', MFADisableView.as_view(), name='mfa_disable'),
    path('api/security/mfa/verify/', MFAVerifyView.as_view(), name='mfa_verify'),
    path('api/security/sessions/revoke/', SessionRevokeView.as_view(), name='session_revoke'),
    path('api/security/sessions/logout-all/', LogoutAllSessionsView.as_view(), name='logout_all_sessions'),
    path('api/security/sessions/', SessionViewSet.as_view({'get': 'list'}), name='sessions'),
    
    # IP Whitelisting & SSO Config
    path('api/security/ip-whitelist/', IPWhitelistViewSet.as_view({'get': 'list', 'post': 'create'}), name='ip_whitelist'),
    path('api/security/ip-whitelist/<uuid:pk>/', IPWhitelistViewSet.as_view({'delete': 'destroy'}), name='ip_whitelist_detail'),
    path('api/security/sso/', SSOConfigurationViewSet.as_view({'get': 'list', 'post': 'create'}), name='sso_list'),
    path('api/security/sso/<uuid:pk>/', SSOConfigurationViewSet.as_view({'put': 'update'}), name='sso_detail'),
    path('api/tenant/request-subscription/', RequestSubscriptionView.as_view(), name='request_subscription'),

    # Razorpay Payment Integration
    path('api/payments/razorpay/create-order/', CreateRazorpayOrderView.as_view(), name='razorpay_create_order'),
    path('api/payments/razorpay/verify-signature/', VerifyRazorpaySignatureView.as_view(), name='razorpay_verify_signature'),
    
    # OpenAPI Schema & Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

