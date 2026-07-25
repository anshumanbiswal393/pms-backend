from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.features.billing.views import TaxRateViewSet, InvoiceViewSet, BillingAdjustmentViewSet

router = DefaultRouter()
router.register(r'tax-rates', TaxRateViewSet, basename='tax_rates')
router.register(r'invoices', InvoiceViewSet, basename='invoices')
router.register(r'adjustments', BillingAdjustmentViewSet, basename='billing_adjustments')

urlpatterns = [
    path('', include(router.urls)),
]
