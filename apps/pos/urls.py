from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.POS.views import (
    OutletViewSet,
    FloorSectionViewSet,
    RestaurantTableViewSet,
    POSRegisterViewSet,
    DeviceMappingViewSet,
    OccupiedRoomsAPIView,
    TaxProfileViewSet,
    MenuCategoryViewSet,
    MenuItemViewSet,
    ModifierGroupViewSet,
    SpecialNoteViewSet,
    BillingMenuCatalogAPIView,
    POSOrderViewSet,
    KOTListAPIView,
    KOTTicketReadyAPIView,
    KOTTicketServedAPIView,
    DayEndSummaryAPIView,
    DayEndCloseAPIView,
    StockItemAPIView,
    StockItemDetailAPIView,
    StockAdjustAPIView,
    StockMovementListAPIView,
    StockOverviewAPIView,
    StockAlertsAPIView,
    StockSettingsAPIView,
    StockUnitListCreateAPIView,
    StockUnitDetailAPIView,
    RecipeListCreateAPIView,
    RecipeAPIView,
    SalesReportAPIView,
    StockReportAPIView,
    ConsumptionReportAPIView,
    AggregatorWebhookAPIView,
    ProductionRecipeListCreateAPIView,
    ProductionRecipeDetailAPIView,
    ProductionBatchListCreateAPIView,
    ProductionBatchDetailAPIView,
    PurchaseListCreateAPIView,
    PurchaseDetailAPIView,
    PurchaseRecordPaymentAPIView,
    POSVendorListCreateAPIView,
    POSVendorDetailAPIView,
    WastageListCreateAPIView,
    WastageDetailAPIView,
    ClosingStockAPIView,
    PurchaseOrderListCreateAPIView,
    PurchaseOrderDetailAPIView,
    PurchaseOrderReceiveAPIView,
    PurchaseReturnListCreateAPIView,
    PurchaseReturnDetailAPIView,
)

router = DefaultRouter()
router.register(r'outlets', OutletViewSet, basename='pos-outlet')
router.register(r'sections', FloorSectionViewSet, basename='pos-section')
router.register(r'tables', RestaurantTableViewSet, basename='pos-table')
router.register(r'registers', POSRegisterViewSet, basename='pos-register')
router.register(r'devices', DeviceMappingViewSet, basename='pos-device')
router.register(r'menu/tax-profiles', TaxProfileViewSet, basename='pos-tax-profile')
router.register(r'menu/categories', MenuCategoryViewSet, basename='pos-menu-category')
router.register(r'menu/items', MenuItemViewSet, basename='pos-menu-item')
router.register(r'menu/modifier-groups', ModifierGroupViewSet, basename='pos-modifier-group')
router.register(r'menu/special-notes', SpecialNoteViewSet, basename='pos-special-note')
router.register(r'orders', POSOrderViewSet, basename='pos-order')

from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response as DRFResponse


@api_view(["GET"])
@drf_permission_classes([AllowAny])
def pos_dashboard_stub(request):
    """Lightweight stub so UI polling does not hit a heavy 404 HTML page."""
    return DRFResponse(
        {
            "success": True,
            "dateRange": request.query_params.get("dateRange") or "today",
            "metrics": {},
            "message": "POS dashboard metrics stub",
        }
    )


urlpatterns = [
    path(
        'dashboard/',
        pos_dashboard_stub,
        name='pos-dashboard',
    ),
    path(
        'integrations/occupied-rooms/',
        OccupiedRoomsAPIView.as_view(),
        name='pos-occupied-rooms',
    ),
    path(
        'integrations/aggregator/webhook/',
        AggregatorWebhookAPIView.as_view(),
        name='pos-aggregator-webhook',
    ),
    path(
        'billing/menu/',
        BillingMenuCatalogAPIView.as_view(),
        name='pos-billing-menu',
    ),
    path(
        'kot/',
        KOTListAPIView.as_view(),
        name='pos-kot-list',
    ),
    path(
        'kot/<uuid:pk>/ready/',
        KOTTicketReadyAPIView.as_view(),
        name='pos-kot-ready',
    ),
    path(
        'kot/<uuid:pk>/served/',
        KOTTicketServedAPIView.as_view(),
        name='pos-kot-served',
    ),
    path(
        'stock/items/',
        StockItemAPIView.as_view(),
        name='pos-stock-items',
    ),
    path(
        'stock/items/<uuid:pk>/adjust/',
        StockAdjustAPIView.as_view(),
        name='pos-stock-adjust',
    ),
    path(
        'stock/items/<uuid:pk>/',
        StockItemDetailAPIView.as_view(),
        name='pos-stock-item-detail',
    ),
    path(
        'stock/movements/',
        StockMovementListAPIView.as_view(),
        name='pos-stock-movements',
    ),
    path(
        'stock/overview/',
        StockOverviewAPIView.as_view(),
        name='pos-stock-overview',
    ),
    path(
        'stock/alerts/',
        StockAlertsAPIView.as_view(),
        name='pos-stock-alerts',
    ),
    path(
        'stock/settings/',
        StockSettingsAPIView.as_view(),
        name='pos-stock-settings',
    ),
    path(
        'stock/units/',
        StockUnitListCreateAPIView.as_view(),
        name='pos-stock-units',
    ),
    path(
        'stock/units/<uuid:pk>/',
        StockUnitDetailAPIView.as_view(),
        name='pos-stock-unit-detail',
    ),
    path(
        'stock/recipes/',
        RecipeListCreateAPIView.as_view(),
        name='pos-recipes',
    ),
    path(
        'stock/recipes/<uuid:menu_item_id>/',
        RecipeAPIView.as_view(),
        name='pos-recipe',
    ),
    path(
        'stock/wastage/',
        WastageListCreateAPIView.as_view(),
        name='pos-stock-wastage',
    ),
    path(
        'stock/wastage/<uuid:pk>/',
        WastageDetailAPIView.as_view(),
        name='pos-stock-wastage-detail',
    ),
    path(
        'stock/closing/',
        ClosingStockAPIView.as_view(),
        name='pos-stock-closing',
    ),
    path(
        'stock/purchase-orders/',
        PurchaseOrderListCreateAPIView.as_view(),
        name='pos-purchase-orders',
    ),
    path(
        'stock/purchase-orders/<uuid:pk>/receive/',
        PurchaseOrderReceiveAPIView.as_view(),
        name='pos-purchase-order-receive',
    ),
    path(
        'stock/purchase-orders/<uuid:pk>/',
        PurchaseOrderDetailAPIView.as_view(),
        name='pos-purchase-order-detail',
    ),
    path(
        'stock/purchase-returns/',
        PurchaseReturnListCreateAPIView.as_view(),
        name='pos-purchase-returns',
    ),
    path(
        'stock/purchase-returns/<uuid:pk>/',
        PurchaseReturnDetailAPIView.as_view(),
        name='pos-purchase-return-detail',
    ),
    path(
        'stock/production/recipes/',
        ProductionRecipeListCreateAPIView.as_view(),
        name='pos-production-recipes',
    ),
    path(
        'stock/production/recipes/<uuid:pk>/',
        ProductionRecipeDetailAPIView.as_view(),
        name='pos-production-recipe-detail',
    ),
    path(
        'stock/production/batches/',
        ProductionBatchListCreateAPIView.as_view(),
        name='pos-production-batches',
    ),
    path(
        'stock/production/batches/<uuid:pk>/',
        ProductionBatchDetailAPIView.as_view(),
        name='pos-production-batch-detail',
    ),
    path(
        'stock/purchases/',
        PurchaseListCreateAPIView.as_view(),
        name='pos-purchases',
    ),
    path(
        'stock/purchases/<uuid:pk>/',
        PurchaseDetailAPIView.as_view(),
        name='pos-purchase-detail',
    ),
    path(
        'stock/purchases/<uuid:pk>/payment/',
        PurchaseRecordPaymentAPIView.as_view(),
        name='pos-purchase-record-payment',
    ),
    path(
        'stock/vendors/',
        POSVendorListCreateAPIView.as_view(),
        name='pos-vendors',
    ),
    path(
        'stock/vendors/<uuid:pk>/',
        POSVendorDetailAPIView.as_view(),
        name='pos-vendor-detail',
    ),
    path(
        'reports/day-end/',
        DayEndSummaryAPIView.as_view(),
        name='pos-day-end',
    ),
    path(
        'reports/day-end/close/',
        DayEndCloseAPIView.as_view(),
        name='pos-day-end-close',
    ),
    path(
        'reports/sales/',
        SalesReportAPIView.as_view(),
        name='pos-report-sales',
    ),
    path(
        'reports/stock/',
        StockReportAPIView.as_view(),
        name='pos-report-stock',
    ),
    path(
        'reports/consumption/',
        ConsumptionReportAPIView.as_view(),
        name='pos-report-consumption',
    ),
    path('', include(router.urls)),
]
