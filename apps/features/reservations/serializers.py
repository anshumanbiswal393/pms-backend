from rest_framework import serializers
from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationRateSnapshot, ReservationGuest, ReservationEvent
)

class CorporateAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorporateAccount
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class GroupBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroupBlock
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class ReservationRateSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationRateSnapshot
        fields = '__all__'


class ReservationGuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationGuest
        fields = '__all__'


class ReservationEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor_user.username', read_only=True)

    class Meta:
        model = ReservationEvent
        fields = '__all__'


class ReservationInventorySerializer(serializers.ModelSerializer):
    rate_snapshots = ReservationRateSnapshotSerializer(many=True, read_only=True)
    guests = ReservationGuestSerializer(many=True, read_only=True)
    unit_name = serializers.CharField(source='inventory_unit.name', read_only=True)
    unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)

    class Meta:
        model = ReservationInventory
        fields = '__all__'


class ReservationSerializer(serializers.ModelSerializer):
    room_allocations = ReservationInventorySerializer(many=True, read_only=True)
    primary_guest_name = serializers.SerializerMethodField()
    reservation_source_name = serializers.CharField(source='reservation_source.name', read_only=True)

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = (
            'id', 'tenant', 'confirmation_number', 'total_amount', 'tax_amount',
            'booking_date', 'status', 'created_at', 'updated_at'
        )

    def get_primary_guest_name(self, obj):
        return f"{obj.primary_guest.first_name} {obj.primary_guest.last_name}"


class CreateBookingSerializer(serializers.Serializer):
    primary_guest_id = serializers.UUIDField(required=False, allow_null=True)
    reservation_source_id = serializers.UUIDField(required=False, allow_null=True)
    group_block_id = serializers.UUIDField(required=False, allow_null=True)
    corporate_account_id = serializers.UUIDField(required=False, allow_null=True)
    reservation_type = serializers.CharField(max_length=32, required=False, default="Individual")
    market_segment = serializers.CharField(max_length=32, required=False, default="Direct")
    origin_country_id = serializers.UUIDField(required=False, allow_null=True)
    arrival_date = serializers.DateField()
    departure_date = serializers.DateField()
    booking_reference = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    remarks = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    special_requests = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    
    # Inline Guest & Source Details
    fullName = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    idType = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    idNumber = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dynamicPricingPct = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Nested Allocations
    allocations = serializers.ListField(
        child=serializers.JSONField()
    )

    # Extra Items
    packages = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    services = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Corporate fields
    corporate_po_ref = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_billing_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_employee_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_cost_center = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_gst_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_travel_purpose = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PriceEstimationSerializer(serializers.Serializer):
    arrival_date = serializers.DateField()
    departure_date = serializers.DateField()
    allocations = serializers.ListField(child=serializers.JSONField())
    packages = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    services = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AssignRoomSerializer(serializers.Serializer):
    allocation_id = serializers.UUIDField()
    room_id = serializers.UUIDField()
    upgrade_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ModifyRemarksSerializer(serializers.Serializer):
    remarks = serializers.CharField(max_length=1000)
    special_requests = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CancelReservationSerializer(serializers.Serializer):
    cancellation_reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class SplitReservationSerializer(serializers.Serializer):
    allocation_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="List of ReservationInventory IDs to split into a new child reservation"
    )


class MergeReservationSerializer(serializers.Serializer):
    secondary_reservation_id = serializers.UUIDField(
        help_text="The ID of the reservation that will be merged and then cancelled"
    )


class RoomUpgradeSerializer(serializers.Serializer):
    allocation_id = serializers.UUIDField()
    new_inventory_type_id = serializers.UUIDField()
    upgrade_reason = serializers.CharField(max_length=500)


class RoomChangeSerializer(serializers.Serializer):
    allocation_id = serializers.UUIDField()
    new_room_id = serializers.UUIDField()


class WaitlistEntrySerializer(serializers.ModelSerializer):
    guest_name = serializers.SerializerMethodField()
    room_type_display = serializers.SerializerMethodField()
    dates_display = serializers.SerializerMethodField()
    priority_display = serializers.SerializerMethodField()
    wl_number = serializers.SerializerMethodField()

    class Meta:
        from apps.features.availability.models import WaitlistEntry
        model = WaitlistEntry
        fields = [
            'id', 'wl_number', 'guest', 'guest_name', 'email_snapshot', 'phone_snapshot',
            'inventory_unit_type', 'room_type_display',
            'check_in_date', 'check_out_date', 'dates_display',
            'priority', 'priority_display', 'status', 'created_at',
        ]
        read_only_fields = ('id', 'created_at', 'wl_number', 'guest_name', 'room_type_display', 'dates_display', 'priority_display')

    def get_wl_number(self, obj):
        """Generate a WL display number from the object's ID sequence."""
        # Use the integer representation of part of the UUID for a stable short ID
        return f"WL-{str(obj.id)[:6].upper()}"

    def get_guest_name(self, obj):
        if obj.guest:
            return f"{obj.guest.first_name} {obj.guest.last_name}".strip()
        return obj.email_snapshot or 'Unknown Guest'

    def get_room_type_display(self, obj):
        if obj.inventory_unit_type:
            return obj.inventory_unit_type.name
        return ''

    def get_dates_display(self, obj):
        import datetime
        ci = obj.check_in_date
        co = obj.check_out_date
        if not ci or not co:
            return ''
            
        if isinstance(ci, str):
            try:
                ci = datetime.date.fromisoformat(ci)
            except ValueError:
                pass
        if isinstance(co, str):
            try:
                co = datetime.date.fromisoformat(co)
            except ValueError:
                pass
                
        if hasattr(ci, 'month') and hasattr(co, 'month'):
            months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
            if ci.month == co.month:
                return f"{ci.day}–{co.day} {months[ci.month - 1]}"
            return f"{ci.day} {months[ci.month - 1]}–{co.day} {months[co.month - 1]}"
        return f"{ci}–{co}"

    def get_priority_display(self, obj):
        p = obj.priority
        if p >= 3:
            return 'High'
        elif p == 2:
            return 'Normal'
        return 'Low'

