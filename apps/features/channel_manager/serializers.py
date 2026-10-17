from rest_framework import serializers
from apps.features.channel_manager.models import (
    StaahConfig,
    StaahRoomMapping,
    StaahRateMapping,
    StaahSyncLog,
    StaahChannelConnection,
    StaahReservationIngest,
)

class StaahConfigSerializer(serializers.ModelSerializer):
    property_name = serializers.ReadOnlyField(source='property.name')

    class Meta:
        model = StaahConfig
        fields = [
            'id',
            'tenant',
            'property',
            'property_name',
            'domain',
            'app_id',
            'auth_token',
            'hotel_id',
            'is_active',
            'is_live',
            'auto_sync_inventory',
            'auto_fetch_reservations',
            'last_synced_at',
            'last_error',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_synced_at', 'last_error']


class StaahRoomMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaahRoomMapping
        fields = [
            'id',
            'config',
            'pms_room_code',
            'pms_room_name',
            'staah_room_id',
            'staah_room_name',
            'status',
            'ota_mappings',
            'inventory_unit_type',
            'room_rate',
            'size_measurement',
            'size_measurement_unit',
            'facilities',
            'description',
            'last_synced_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StaahRateMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaahRateMapping
        fields = [
            'id',
            'config',
            'pms_rate_code',
            'pms_rate_name',
            'meal_plan_code',
            'staah_rate_id',
            'staah_rate_name',
            'status',
            'ota_mappings',
            'last_synced_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StaahSyncLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaahSyncLog
        fields = [
            'id',
            'config',
            'sync_type',
            'direction',
            'status',
            'endpoint',
            'request_payload',
            'response_payload',
            'error_message',
            'records_count',
            'duration_ms',
            'created_at',
        ]
        read_only_fields = '__all__'


class StaahChannelConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaahChannelConnection
        fields = [
            'id',
            'config',
            'channel_name',
            'status',
            'property_id',
            'last_sync',
            'commission',
            'bookings_mtd',
            'revenue_mtd',
            'parity',
            'parity_delta',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StaahReservationIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaahReservationIngest
        fields = [
            'id',
            'config',
            'channel_booking_id',
            'channel_name',
            'status',
            'pms_booking_reference',
            'guest_name',
            'guest_email',
            'guest_phone',
            'room_type_name',
            'check_in',
            'check_out',
            'total_amount',
            'currency',
            'is_confirmed_to_staah',
            'confirmed_at',
            'error_message',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

