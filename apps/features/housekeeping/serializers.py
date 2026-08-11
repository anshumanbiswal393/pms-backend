from rest_framework import serializers
from apps.features.housekeeping.models import (
    CleaningTask, RoomInspection, DeepCleaningSchedule,
    TurndownService, MinibarInventory, MinibarRefill,
    AmenityInventory, HousekeepingInventory
)

class CleaningTaskSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)
    assigned_staff_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CleaningTask
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')

    def get_assigned_staff_name(self, obj):
        if obj.assigned_staff:
            return obj.assigned_staff.name or obj.assigned_staff.username
        return None


class RoomInspectionSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)
    inspector_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RoomInspection
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')

    def get_inspector_name(self, obj):
        if obj.inspector:
            return obj.inspector.name or obj.inspector.username
        return None


class DeepCleaningScheduleSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = DeepCleaningSchedule
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class TurndownServiceSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = TurndownService
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class MinibarInventorySerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = MinibarInventory
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class MinibarRefillSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = MinibarRefill
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class AmenityInventorySerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = AmenityInventory
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class HousekeepingInventorySerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = HousekeepingInventory
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')
