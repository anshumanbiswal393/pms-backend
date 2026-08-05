from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.core.subscriptions.views import (
    ProductViewSet, SubscriptionPlanViewSet, SubscriptionEntitlementViewSet,
    SubscriptionAssignView, SubscriptionUpgradeView, SubscriptionDowngradeView,
    SubscriptionUsageView, ProductFeatureViewSet, LicenseViewSet,
    EntitlementViewSet, UsageViewSet, TenantSubscriptionViewSet
)

router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'plans', SubscriptionPlanViewSet, basename='plan')
router.register(r'entitlements', SubscriptionEntitlementViewSet, basename='entitlement')
router.register(r'tenant-subscriptions', TenantSubscriptionViewSet, basename='tenant-subscription')

# Expose new viewsets also in local router to ensure multiple paths work
router.register(r'product-features', ProductFeatureViewSet, basename='product-feature')
router.register(r'licenses', LicenseViewSet, basename='license')
router.register(r'tenant-entitlements', EntitlementViewSet, basename='tenant-entitlement')
router.register(r'tenant-usages', UsageViewSet, basename='tenant-usage')

urlpatterns = [
    path('', include(router.urls)),
    path('assign/', SubscriptionAssignView.as_view(), name='subscription-assign'),
    path('custom-assign/', TenantSubscriptionViewSet.as_view({'post': 'custom_assign'}), name='subscription-custom-assign'),
    path('upgrade/', SubscriptionUpgradeView.as_view(), name='subscription-upgrade'),
    path('downgrade/', SubscriptionDowngradeView.as_view(), name='subscription-downgrade'),
    path('usage/', SubscriptionUsageView.as_view(), name='subscription-usage'),
]
