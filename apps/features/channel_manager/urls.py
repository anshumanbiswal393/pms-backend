from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.features.channel_manager.views import (
    StaahConfigViewSet,
    StaahRoomMappingViewSet,
    StaahRateMappingViewSet,
    StaahSyncLogViewSet,
    StaahChannelConnectionViewSet,
    StaahReservationIngestViewSet,
    su_room_mappings_view,
    su_update_room_mapping_view,
    su_rate_plan_mappings_view,
    su_update_rate_plan_mapping_view,
    su_availability_view,
    su_rates_view,
    su_push_inventory_view,
    su_update_cell_view,
    su_inventory_view,
    su_reservation_sync_view,
    su_fetch_reservations_view,
    su_reservation_webhook_view,
    su_dashboard_view,
)

router = DefaultRouter()
router.register(r'configs', StaahConfigViewSet, basename='staah-config')
router.register(r'room-mappings', StaahRoomMappingViewSet, basename='staah-room-mapping')
router.register(r'rate-mappings', StaahRateMappingViewSet, basename='staah-rate-mapping')
router.register(r'sync-logs', StaahSyncLogViewSet, basename='staah-sync-log')
router.register(r'connections', StaahChannelConnectionViewSet, basename='staah-connection')
router.register(r'reservations/ingest', StaahReservationIngestViewSet, basename='staah-reservation-ingest')

urlpatterns = [
    # Su API UI Compatible endpoints
    path('mappings/rooms', su_room_mappings_view, name='su-room-mappings'),
    path('mappings/rooms/<str:code>', su_update_room_mapping_view, name='su-update-room-mapping'),
    path('mappings/rate-plans', su_rate_plan_mappings_view, name='su-rate-plan-mappings'),
    path('mappings/rate-plans/<str:code>', su_update_rate_plan_mapping_view, name='su-update-rate-plan-mapping'),
    
    # ARI (Availability, Rates & Inventory) Endpoints
    path('inventory', su_inventory_view, name='su-inventory'),
    path('availability', su_availability_view, name='su-availability'),
    path('rates', su_rates_view, name='su-rates'),
    path('sync/availability', su_push_inventory_view, name='su-push-inventory'),
    path('availability/update-cell', su_update_cell_view, name='su-update-cell'),
    
    # Reservation Ingestion & Confirmation Endpoints
    path('reservations/sync', su_reservation_sync_view, name='su-reservation-sync'),
    path('reservations/fetch-and-ingest', su_fetch_reservations_view, name='su-fetch-reservations'),
    path('webhook/reservation/', su_reservation_webhook_view, name='su-reservation-webhook'),
    
    # Dashboard & Stats (Live from DB)
    path('dashboard', su_dashboard_view, name='su-dashboard'),
    path('stats', su_dashboard_view, name='su-stats'),
    
    # DRF Default Router Endpoints
    path('', include(router.urls)),
]
