from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.features.channel_manager.models import (
    StaahConfig,
    StaahRoomMapping,
    StaahRateMapping,
    StaahSyncLog,
    StaahChannelConnection,
    StaahReservationIngest,
)
from apps.features.channel_manager.serializers import (
    StaahConfigSerializer,
    StaahRoomMappingSerializer,
    StaahRateMappingSerializer,
    StaahSyncLogSerializer,
    StaahChannelConnectionSerializer,
    StaahReservationIngestSerializer,
)
from apps.features.channel_manager.services.staah_client import StaahSuClient
from apps.features.channel_manager.services.mapping_service import MappingService
from apps.features.channel_manager.services.reservation_engine import ReservationIngestionService

DEFAULT_CHANNELS = [
    "Booking.com",
    "Agoda",
    "Expedia",
    "Airbnb",
    "MakeMyTrip",
    "Goibibo",
    "HotelBeds",
    "Trip.com",
]


class StaahConfigViewSet(viewsets.ModelViewSet):
    queryset = StaahConfig.objects.all()
    serializer_class = StaahConfigSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        property_id = self.request.query_params.get('property')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @action(detail=True, methods=['post'], url_path='test-connection')
    def test_connection(self, request, pk=None):
        config = self.get_object()
        client = StaahSuClient(config=config)
        result = client.test_connection()
        return Response(result, status=status.HTTP_200_OK if result.get('connected') else status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='test-credentials')
    def test_credentials(self, request):
        domain = request.data.get('domain', 'https://connect.su-api.com')
        app_id = request.data.get('app_id', '')
        auth_token = request.data.get('auth_token', '')
        hotel_id = request.data.get('hotel_id', '')

        if not app_id or not auth_token or not hotel_id:
            return Response(
                {"connected": False, "message": "app_id, auth_token, and hotel_id are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        client = StaahSuClient(
            domain=domain,
            app_id=app_id,
            auth_token=auth_token,
            hotel_id=hotel_id
        )
        result = client.test_connection()
        return Response(result, status=status.HTTP_200_OK if result.get('connected') else status.HTTP_400_BAD_REQUEST)


class StaahRoomMappingViewSet(viewsets.ModelViewSet):
    queryset = StaahRoomMapping.objects.all()
    serializer_class = StaahRoomMappingSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        config_id = self.request.query_params.get('config')
        if config_id:
            qs = qs.filter(config_id=config_id)
        return qs

    @action(detail=False, methods=['post'], url_path='sync-pms-catalog')
    def sync_pms_catalog(self, request):
        config = StaahConfig.objects.first()
        if not config:
            return Response({"error": "No StaahConfig found. Create config first."}, status=status.HTTP_404_NOT_FOUND)
        service = MappingService(config)
        res = service.sync_pms_catalog_to_mappings()
        return Response(res, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='fetch-remote-rooms')
    def fetch_remote_rooms(self, request):
        config_id = request.data.get('config_id')
        config = StaahConfig.objects.filter(id=config_id).first() if config_id else StaahConfig.objects.first()
        if not config:
            return Response({"error": "StaahConfig not found."}, status=status.HTTP_404_NOT_FOUND)

        service = MappingService(config)
        res = service.fetch_and_merge_staah_rooms()
        return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='push-to-staah')
    def push_to_staah(self, request, pk=None):
        mapping = self.get_object()
        service = MappingService(mapping.config)
        res = service.push_room_to_staah(str(mapping.id))
        return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)


class StaahRateMappingViewSet(viewsets.ModelViewSet):
    queryset = StaahRateMapping.objects.all()
    serializer_class = StaahRateMappingSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        config_id = self.request.query_params.get('config')
        if config_id:
            qs = qs.filter(config_id=config_id)
        return qs

    @action(detail=False, methods=['post'], url_path='fetch-remote-rates')
    def fetch_remote_rates(self, request):
        config_id = request.data.get('config_id')
        config = StaahConfig.objects.filter(id=config_id).first() if config_id else StaahConfig.objects.first()
        if not config:
            return Response({"error": "StaahConfig not found."}, status=status.HTTP_404_NOT_FOUND)

        service = MappingService(config)
        res = service.fetch_and_merge_staah_rates()
        return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='push-to-staah')
    def push_to_staah(self, request, pk=None):
        mapping = self.get_object()
        service = MappingService(mapping.config)
        res = service.push_rate_to_staah(str(mapping.id))
        return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)


class StaahSyncLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StaahSyncLog.objects.all()
    serializer_class = StaahSyncLogSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        config_id = self.request.query_params.get('config')
        sync_type = self.request.query_params.get('sync_type')
        status_filter = self.request.query_params.get('status')
        if config_id:
            qs = qs.filter(config_id=config_id)
        if sync_type:
            qs = qs.filter(sync_type=sync_type)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs[:100]


class StaahChannelConnectionViewSet(viewsets.ModelViewSet):
    queryset = StaahChannelConnection.objects.all()
    serializer_class = StaahChannelConnectionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        config_id = self.request.query_params.get('config')
        if config_id:
            qs = qs.filter(config_id=config_id)
        return qs


# =========================================================================
# Su Client UI Compatibility Views (Formats DB rows to SuRoomMapping / SuRatePlanMapping)
# =========================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def su_room_mappings_view(request):
    """
    Returns room mappings formatted for Frontend SuChannelManagerClient.
    """
    config = StaahConfig.objects.first()
    if not config:
        return Response([], status=status.HTTP_200_OK)

    # Ensure catalog is synced
    MappingService(config).sync_pms_catalog_to_mappings()

    mappings = StaahRoomMapping.objects.filter(config=config)
    result = []
    for m in mappings:
        channels_dict = {}
        for ch in DEFAULT_CHANNELS:
            ch_data = m.ota_mappings.get(ch, {})
            channels_dict[ch] = {
                "otaRoomId": ch_data.get("otaRoomId", m.staah_room_id or "—"),
                "otaRoomName": ch_data.get("otaRoomName", m.staah_room_name or m.pms_room_name),
                "status": ch_data.get("status", m.status),
            }
        result.append({
            "pmsRoomType": m.pms_room_name,
            "pmsRoomCode": m.pms_room_code,
            "channels": channels_dict,
        })
    return Response(result, status=status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([AllowAny])
def su_update_room_mapping_view(request, code):
    """
    Updates room mapping for specific room code.
    """
    config = StaahConfig.objects.first()
    if not config:
        return Response({"error": "No config"}, status=status.HTTP_404_NOT_FOUND)

    mapping = StaahRoomMapping.objects.filter(config=config, pms_room_code=code).first()
    if not mapping:
        mapping = StaahRoomMapping.objects.create(
            config=config,
            pms_room_code=code,
            pms_room_name=request.data.get('pmsRoomType', code),
            staah_room_id=f"{config.hotel_id}-{code}",
            status='Mapped'
        )

    channels = request.data.get('channels', {})
    if channels:
        mapping.ota_mappings = channels
        mapping.status = 'Mapped'
        mapping.save(update_fields=['ota_mappings', 'status', 'updated_at'])

    return Response({"status": "success", "pmsRoomCode": code}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def su_rate_plan_mappings_view(request):
    """
    Returns rate plan mappings formatted for Frontend SuChannelManagerClient.
    """
    config = StaahConfig.objects.first()
    if not config:
        return Response([], status=status.HTTP_200_OK)

    MappingService(config).sync_pms_catalog_to_mappings()

    mappings = StaahRateMapping.objects.filter(config=config)
    result = []
    for m in mappings:
        channels_dict = {}
        for ch in DEFAULT_CHANNELS:
            ch_data = m.ota_mappings.get(ch, {})
            channels_dict[ch] = {
                "otaRatePlanId": ch_data.get("otaRatePlanId", m.staah_rate_id or "—"),
                "status": ch_data.get("status", m.status),
            }
        result.append({
            "pmsRatePlan": m.pms_rate_name,
            "pmsRatePlanCode": m.pms_rate_code,
            "mealPlan": m.meal_plan_code,
            "channels": channels_dict,
        })
    return Response(result, status=status.HTTP_200_OK)


@api_view(['PUT'])
@permission_classes([AllowAny])
def su_update_rate_plan_mapping_view(request, code):
    """
    Updates rate plan mapping for specific rate plan code.
    """
    config = StaahConfig.objects.first()
    if not config:
        return Response({"error": "No config"}, status=status.HTTP_404_NOT_FOUND)

    mapping = StaahRateMapping.objects.filter(config=config, pms_rate_code=code).first()
    if not mapping:
        mapping = StaahRateMapping.objects.create(
            config=config,
            pms_rate_code=code,
            pms_rate_name=request.data.get('pmsRatePlan', code),
            staah_rate_id=f"{config.hotel_id}-{code}",
            status='Mapped'
        )

    channels = request.data.get('channels', {})
    if channels:
        mapping.ota_mappings = channels
        mapping.status = 'Mapped'
        mapping.save(update_fields=['ota_mappings', 'status', 'updated_at'])

    return Response({"status": "success", "pmsRatePlanCode": code}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def su_availability_view(request):
    """
    Returns daily room availability cells for the calendar.
    Supports ?start_date=YYYY-MM-DD or offset days.
    Format matches SuAvailabilityCell[]: { date, roomType, available, total, stopSell, fullDate }
    """
    from datetime import date, timedelta
    from apps.booking.models import RoomType as BookingRoomType, RoomInventory

    rooms = BookingRoomType.objects.filter(is_active=True)
    today = date.today()
    start_date_str = request.query_params.get('start_date')
    days_count = int(request.query_params.get('days', 10))

    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except Exception:
            start_date = today
    else:
        from_param = request.query_params.get('from')
        if from_param:
            try:
                from_num = int(from_param)
                start_date = today.replace(day=min(from_num, 28))
            except Exception:
                start_date = today
        else:
            start_date = today

    result = []
    for day_offset in range(days_count):
        target_date = start_date + timedelta(days=day_offset)
        day_num = target_date.day

        for r in rooms:
            inv = RoomInventory.objects.filter(room_type=r, date=target_date).first()
            available = inv.available_rooms if inv else r.total_rooms
            stop_sell = inv.is_blocked if inv else False

            result.append({
                "date": day_num,
                "fullDate": target_date.strftime("%Y-%m-%d"),
                "roomType": r.name,
                "available": max(0, available),
                "total": r.total_rooms,
                "stopSell": stop_sell
            })

    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def su_rates_view(request):
    """
    Returns daily room rates cells for the calendar.
    Format matches SuRateCell[]: { date, roomType, amount, currency, fullDate }
    """
    from datetime import date, timedelta
    from apps.booking.models import RoomType as BookingRoomType, RoomInventory

    rooms = BookingRoomType.objects.filter(is_active=True)
    today = date.today()
    start_date_str = request.query_params.get('start_date')
    days_count = int(request.query_params.get('days', 10))

    if start_date_str:
        try:
            start_date = date.fromisoformat(start_date_str)
        except Exception:
            start_date = today
    else:
        from_param = request.query_params.get('from')
        if from_param:
            try:
                from_num = int(from_param)
                start_date = today.replace(day=min(from_num, 28))
            except Exception:
                start_date = today
        else:
            start_date = today

    result = []
    for day_offset in range(days_count):
        target_date = start_date + timedelta(days=day_offset)
        day_num = target_date.day

        for r in rooms:
            inv = RoomInventory.objects.filter(room_type=r, date=target_date).first()
            price = float(inv.custom_price) if (inv and inv.custom_price) else float(r.base_price)

            result.append({
                "date": day_num,
                "fullDate": target_date.strftime("%Y-%m-%d"),
                "roomType": r.name,
                "ratePlan": "BAR Flexible",
                "amount": price,
                "currency": "INR"
            })

    return Response(result, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def su_push_inventory_view(request):
    """
    Pushes inventory, availability and restrictions to STAAH Su API.
    POST /SUAPI/jservice/availability
    """
    from datetime import date, timedelta
    from apps.features.channel_manager.services.ari_sync import AriSyncService

    today = date.today()
    date_from_str = request.data.get('from_date')
    date_to_str = request.data.get('to_date')
    room_code = request.data.get('room_code')

    d_from = date.fromisoformat(date_from_str) if date_from_str else today
    d_to = date.fromisoformat(date_to_str) if date_to_str else today + timedelta(days=14)

    service = AriSyncService()
    res = service.push_inventory_range(d_from, d_to, pms_room_code=room_code)
    return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def su_update_cell_view(request):
    """
    Directly updates a single cell's available rooms or stop-sell, saving in DB and pushing to STAAH.
    """
    from datetime import date, timedelta
    from apps.booking.models import RoomType as BookingRoomType, RoomInventory
    from apps.features.channel_manager.services.ari_sync import AriSyncService

    room_type_name = request.data.get('roomType')
    day_num = request.data.get('date')
    date_str = request.data.get('fullDate') or request.data.get('dateStr')
    available = request.data.get('available')
    stop_sell = request.data.get('stopSell')
    custom_price = request.data.get('price')

    room = BookingRoomType.objects.filter(name__iexact=room_type_name).first()
    if not room:
        return Response({"error": "Room type not found"}, status=status.HTTP_404_NOT_FOUND)

    # Determine date
    today = date.today()
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except Exception:
            target_date = today
    else:
        target_date = today
        if day_num is not None:
            for i in range(31):
                d = today + timedelta(days=i)
                if d.day == int(day_num):
                    target_date = d
                    break

    inv, _ = RoomInventory.objects.get_or_create(
        room_type=room,
        date=target_date,
        defaults={'available_rooms': room.total_rooms}
    )

    if available is not None:
        inv.available_rooms = max(0, int(available))
    if stop_sell is not None:
        inv.is_blocked = bool(stop_sell)
    if custom_price is not None:
        inv.custom_price = float(custom_price)

    inv.save()

    # Trigger instant push to STAAH
    service = AriSyncService()
    pms_code = getattr(room, 'slug', None) or f"ROOM-{room.id}"
    push_res = service.push_inventory_range(target_date, target_date, pms_room_code=pms_code)

    return Response({
        "status": "success",
        "date": target_date.day,
        "fullDate": target_date.strftime("%Y-%m-%d"),
        "roomType": room.name,
        "available": inv.available_rooms,
        "stopSell": inv.is_blocked,
        "price": float(inv.custom_price) if inv.custom_price else float(room.base_price),
        "staah_push": push_res
    }, status=status.HTTP_200_OK)


# =========================================================================
# Reservation Ingestion ViewSet & Endpoints (POST /SUAPI/jservice/Reservation)
# =========================================================================

class StaahReservationIngestViewSet(viewsets.ModelViewSet):
    queryset = StaahReservationIngest.objects.all()
    serializer_class = StaahReservationIngestSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        config_id = self.request.query_params.get('config')
        channel_name = self.request.query_params.get('channel')
        status_filter = self.request.query_params.get('status')
        if config_id:
            qs = qs.filter(config_id=config_id)
        if channel_name:
            qs = qs.filter(channel_name__iexact=channel_name)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['post'], url_path='fetch-and-ingest')
    def fetch_and_ingest(self, request):
        service = ReservationIngestionService()
        res = service.fetch_and_ingest_all()
        return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def su_reservation_sync_view(request):
    """
    Returns list of ingested OTA reservations formatted for Frontend SuReservationSync[].
    Format: { id, channel, otaRef, pmsRef, guest, status, checkIn, amount, syncedAt, error }
    """
    records = StaahReservationIngest.objects.all()[:100]
    
    # If no records exist in DB yet, trigger initial ingest to populate with realistic data
    if not records.exists():
        service = ReservationIngestionService()
        service.fetch_and_ingest_all()
        records = StaahReservationIngest.objects.all()[:100]

    result = []
    for r in records:
        result.append({
            "id": str(r.id),
            "channel": r.channel_name,
            "otaRef": r.channel_booking_id,
            "pmsRef": r.pms_booking_reference or "—",
            "guest": r.guest_name,
            "status": r.status,
            "checkIn": r.check_in.strftime("%Y-%m-%d"),
            "amount": float(r.total_amount),
            "syncedAt": r.created_at.strftime("%d %b, %H:%M"),
            "error": r.error_message,
            "isConfirmed": r.is_confirmed_to_staah,
        })
    return Response(result, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def su_fetch_reservations_view(request):
    """
    Triggers on-demand polling and ingestion of pending OTA reservations from STAAH Su API.
    """
    service = ReservationIngestionService()
    res = service.fetch_and_ingest_all()
    return Response(res, status=status.HTTP_200_OK if res.get('success') else status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def su_reservation_webhook_view(request):
    """
    Webhook endpoint for receiving real-time booking push notifications from STAAH ChannelConnect.
    POST /api/v1/channel-manager/webhook/reservation/
    """
    payload = request.data
    service = ReservationIngestionService()
    if isinstance(payload, list):
        res = [service.ingest_single_reservation(item) for item in payload]
    elif isinstance(payload, dict):
        res = service.ingest_single_reservation(payload)
    else:
        res = {"error": "Invalid payload format"}

    return Response(res, status=status.HTTP_200_OK)

