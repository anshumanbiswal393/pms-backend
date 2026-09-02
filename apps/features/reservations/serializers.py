from rest_framework import serializers
from apps.features.reservations.models import (
    CorporateAccount, GroupBlock, Reservation, ReservationInventory,
    ReservationRateSnapshot, ReservationGuest, ReservationEvent,
    ReservationServiceAddon, ReservationPackage, ReservationExtraCharge
)
from apps.features.crm.services import EncryptionHelper

class ReservationServiceAddonSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)

    class Meta:
        model = ReservationServiceAddon
        fields = ('id', 'service', 'service_name', 'price')


class ReservationPackageSerializer(serializers.ModelSerializer):
    package_name = serializers.CharField(source='package.name', read_only=True)

    class Meta:
        model = ReservationPackage
        fields = ('id', 'package', 'package_name', 'price')


class ReservationExtraChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationExtraCharge
        fields = ('id', 'description', 'amount', 'tax_amount', 'tax_type', 'tax_percent', 'date', 'created_at')


class CorporateAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorporateAccount
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')


class GroupBlockSerializer(serializers.ModelSerializer):
    id_type_name = serializers.SerializerMethodField()
    nationality_name = serializers.SerializerMethodField()
    property_details = serializers.SerializerMethodField()

    class Meta:
        model = GroupBlock
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at')

    def get_property_details(self, obj):
        if not obj.property:
            return None
        p = obj.property
        return {
            'id': str(p.id),
            'name': p.name,
            'address_line_1': p.address_line_1 or "",
            'address_line_2': p.address_line_2 or "",
            'city': p.city or "",
            'state': p.state or "",
            'country': p.country or "",
            'postal_code': p.postal_code or "",
            'contact_phone': p.contact_phone or "",
            'contact_email': p.contact_email or "",
            'tax_id': p.tax_id or "",
            'website_logo': p.website_logo or "",
        }

    def get_id_type_name(self, obj):
        if not obj.id_type:
            return ""
        from apps.core.reference.models import DocumentType
        import uuid
        try:
            val = str(obj.id_type).strip()
            if len(val) == 36 and '-' in val:
                doc = DocumentType.objects.filter(id=uuid.UUID(val)).first()
                if doc:
                    return doc.name
            doc = DocumentType.objects.filter(code__iexact=val).first()
            if doc:
                return doc.name
            doc = DocumentType.objects.filter(name__iexact=val).first()
            if doc:
                return doc.name
        except Exception:
            pass
        return str(obj.id_type)

    def get_nationality_name(self, obj):
        if not obj.nationality:
            return "Indian"
        from apps.core.reference.models import Nationality
        import uuid
        try:
            val = str(obj.nationality).strip()
            if len(val) == 36 and '-' in val:
                nat = Nationality.objects.filter(id=uuid.UUID(val)).first()
                if nat:
                    return nat.name
            nat = Nationality.objects.filter(code__iexact=val).first()
            if nat:
                return nat.name
            nat = Nationality.objects.filter(name__iexact=val).first()
            if nat:
                return nat.name
        except Exception:
            pass
        return str(obj.nationality)


class ReservationRateSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationRateSnapshot
        fields = '__all__'


class ReservationGuestSerializer(serializers.ModelSerializer):
    guest_name = serializers.SerializerMethodField()
    guest_first_name = serializers.CharField(source='guest.first_name', read_only=True)
    guest_last_name = serializers.CharField(source='guest.last_name', read_only=True)
    guest_email = serializers.SerializerMethodField()
    guest_phone = serializers.SerializerMethodField()
    guest_address = serializers.SerializerMethodField()
    guest_id_type = serializers.SerializerMethodField()
    guest_id_number = serializers.SerializerMethodField()
    guest_id_proof_url = serializers.SerializerMethodField()

    class Meta:
        model = ReservationGuest
        fields = '__all__'

    def get_guest_name(self, obj):
        if obj.guest:
            return f"{obj.guest.first_name} {obj.guest.last_name}".strip()
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('name', '')
        return ""

    def get_guest_email(self, obj):
        if obj.guest:
            contacts = list(obj.guest.contacts.all()) if hasattr(obj.guest, 'contacts') else []
            contact = next((c for c in contacts if getattr(c, 'is_primary', False)), None) or (contacts[0] if contacts else None)
            if contact and contact.email:
                return contact.email
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('email', '')
        return ""

    def get_guest_phone(self, obj):
        if obj.guest:
            contacts = list(obj.guest.contacts.all()) if hasattr(obj.guest, 'contacts') else []
            contact = next((c for c in contacts if getattr(c, 'is_primary', False)), None) or (contacts[0] if contacts else None)
            if contact and contact.phone:
                return contact.phone
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('phone', '')
        return ""

    def get_guest_address(self, obj):
        if obj.guest:
            contacts = list(obj.guest.contacts.all()) if hasattr(obj.guest, 'contacts') else []
            contact = next((c for c in contacts if getattr(c, 'is_primary', False)), None) or (contacts[0] if contacts else None)
            if contact:
                parts = [contact.address_line_1, contact.address_line_2, contact.city, contact.state, contact.country]
                return ", ".join([p for p in parts if p])
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('address', '')
        return ""

    def get_guest_id_type(self, obj):
        if obj.guest:
            docs = list(obj.guest.documents.all()) if hasattr(obj.guest, 'documents') else []
            doc = docs[0] if docs else None
            if doc and doc.document_type:
                return doc.document_type
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('id_type', '')
        return ""

    def get_guest_id_number(self, obj):
        if obj.guest:
            docs = list(obj.guest.documents.all()) if hasattr(obj.guest, 'documents') else []
            doc = docs[0] if docs else None
            if doc and doc.document_number:
                try:
                    return EncryptionHelper.decrypt(doc.document_number)
                except Exception:
                    return doc.document_number
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('id_number', '')
        return ""

    def get_guest_id_proof_url(self, obj):
        if obj.guest:
            docs = list(obj.guest.documents.all()) if hasattr(obj.guest, 'documents') else []
            doc = docs[0] if docs else None
            if doc and doc.attachment_url:
                return doc.attachment_url
        if obj.guest_snapshot:
            return obj.guest_snapshot.get('id_proof_url', '')
        return ""


class ReservationEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor_user.username', read_only=True)
    actor_name = serializers.SerializerMethodField()
    actor_role = serializers.SerializerMethodField()

    class Meta:
        model = ReservationEvent
        fields = '__all__'

    def get_actor_name(self, obj):
        if not obj.actor_user:
            return "System"
        return getattr(obj.actor_user, 'name', None) or obj.actor_user.username or "Staff"

    def get_actor_role(self, obj):
        if not obj.actor_user:
            return "System"
        if getattr(obj.actor_user, 'role', None) and hasattr(obj.actor_user.role, 'name'):
            return obj.actor_user.role.name
        if getattr(obj.actor_user, 'is_superuser', False):
            return "Super Admin"
        if getattr(obj.actor_user, 'is_staff', False):
            return "Owner"
        return "Staff"


class ReservationInventorySerializer(serializers.ModelSerializer):
    rate_snapshots = ReservationRateSnapshotSerializer(many=True, read_only=True)
    guests = ReservationGuestSerializer(many=True, read_only=True)
    unit_name = serializers.CharField(source='inventory_unit.name', read_only=True)
    unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)

    class Meta:
        model = ReservationInventory
        fields = '__all__'


# Cached in-memory booking sources for ultra-fast lookup
_booking_sources_cache = None
_booking_sources_cache_time = 0

def get_cached_booking_sources():
    global _booking_sources_cache, _booking_sources_cache_time
    import time
    now = time.time()
    if _booking_sources_cache is None or (now - _booking_sources_cache_time) > 60:
        try:
            from apps.core.common.models import BookingSource
            _booking_sources_cache = list(BookingSource.objects.all())
            _booking_sources_cache_time = now
        except Exception:
            _booking_sources_cache = []
    return _booking_sources_cache

def resolve_booking_source_icon(source_name):
    if not source_name:
        source_name = "Direct"
    sources = get_cached_booking_sources()
    src_norm = source_name.lower().replace(" ", "").replace("_", "").replace("-", "")
    for bs in sources:
        bs_norm = bs.name.lower().replace(" ", "").replace("_", "").replace("-", "")
        if bs_norm == src_norm:
            return bs.icon
    for bs in sources:
        bs_norm = bs.name.lower().replace(" ", "").replace("_", "").replace("-", "")
        if bs_norm in src_norm or src_norm in bs_norm:
            if bs.icon:
                return bs.icon
        if bs.details:
            details_norm = bs.details.lower().replace(" ", "").replace("_", "").replace("-", "")
            if details_norm in src_norm or src_norm in details_norm:
                if bs.icon:
                    return bs.icon
    return None


class ReservationListInventorySerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='inventory_unit.name', read_only=True)
    unit_type_code = serializers.CharField(source='inventory_unit_type.code', read_only=True)

    class Meta:
        model = ReservationInventory
        fields = [
            'id', 'inventory_unit', 'inventory_unit_type', 'unit_name', 'unit_type_code',
            'check_in_date', 'check_out_date', 'adult_count', 'child_count', 'status', 'assigned_at'
        ]


class ReservationListSerializer(serializers.ModelSerializer):
    """
    High-performance lean serializer for list and timeline views.
    Executes in < 0.01s without deep audit or event history serialization.
    """
    room_allocations = ReservationListInventorySerializer(many=True, read_only=True)
    primary_guest_name = serializers.SerializerMethodField()
    primary_guest_phone = serializers.SerializerMethodField()
    primary_guest_email = serializers.SerializerMethodField()
    primary_guest_id_type = serializers.SerializerMethodField()
    primary_guest_id_number = serializers.SerializerMethodField()
    primary_guest_nationality = serializers.SerializerMethodField()
    primary_guest_tier = serializers.SerializerMethodField()
    primary_guest_city = serializers.SerializerMethodField()
    reservation_source_name = serializers.CharField(source='reservation_source.name', read_only=True)
    reservation_source_icon = serializers.SerializerMethodField()
    property_name = serializers.CharField(source='property.name', read_only=True)
    grand_total = serializers.SerializerMethodField()
    adults = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    checked_in_by_name = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()
    rate_plan_name = serializers.SerializerMethodField()
    rate_plan_code = serializers.SerializerMethodField()

    property_business_date = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'property', 'property_name', 'property_business_date', 'confirmation_number', 'booking_reference', 'status', 'reservation_type',
            'market_segment', 'booking_date', 'arrival_date', 'departure_date',
            'check_in_time', 'check_out_time', 'adults', 'children',
            'total_amount', 'tax_amount', 'discount_amount', 'paid_amount', 'balance_amount', 'grand_total',
            'primary_guest', 'primary_guest_name', 'primary_guest_phone', 'primary_guest_email',
            'primary_guest_id_type', 'primary_guest_id_number', 'primary_guest_nationality', 'primary_guest_tier', 'primary_guest_city',
            'reservation_source', 'reservation_source_name', 'reservation_source_icon',
            'corporate_account', 'group_block', 'room_allocations', 'rate_plan_name', 'rate_plan_code',
            'created_by_name', 'checked_in_by_name', 'actor_name', 'created_at', 'updated_at'
        ]

    def get_rate_plan_name(self, obj):
        try:
            for alloc in obj.room_allocations.all():
                snap = alloc.rate_snapshots.first()
                if snap and snap.rate_plan:
                    return snap.rate_plan.name
        except Exception:
            pass
        return "AP Plan"

    def get_rate_plan_code(self, obj):
        try:
            for alloc in obj.room_allocations.all():
                snap = alloc.rate_snapshots.first()
                if snap and snap.rate_plan:
                    return snap.rate_plan.code or snap.rate_plan.name
        except Exception:
            pass
        return "AP_PLAN"

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name or ''} {obj.created_by.last_name or ''}".strip()
            return name or obj.created_by.username or "Admin"
        return "Admin"

    def get_checked_in_by_name(self, obj):
        try:
            if obj.status in ["CHECKED_IN", "CHECKED_OUT"]:
                if hasattr(obj, 'timeline_events'):
                    ci_event = obj.timeline_events.filter(event_type__icontains="CHECK_IN").first()
                    if ci_event:
                        actor = getattr(ci_event, 'actor_user', None) or getattr(ci_event, 'actor', None)
                        if actor:
                            name = f"{getattr(actor, 'first_name', '') or ''} {getattr(actor, 'last_name', '') or ''}".strip()
                            if name:
                                return name
                if obj.updated_by:
                    name = f"{obj.updated_by.first_name or ''} {obj.updated_by.last_name or ''}".strip()
                    if name:
                        return name
            if obj.created_by:
                name = f"{obj.created_by.first_name or ''} {obj.created_by.last_name or ''}".strip()
                if name:
                    return name
        except Exception:
            pass
        return "Frontdesk Agent"

    def get_actor_name(self, obj):
        return self.get_checked_in_by_name(obj)

    def get_property_business_date(self, obj):
        if obj.property and obj.property.business_date:
            return str(obj.property.business_date)
        from django.utils import timezone
        return str(timezone.localdate())

    def get_reservation_source_icon(self, obj):
        source_name = obj.reservation_source.name if obj.reservation_source else "Direct"
        return resolve_booking_source_icon(source_name)

    def get_grand_total(self, obj):
        from decimal import Decimal
        total = (obj.total_amount or Decimal('0.00')) + (obj.tax_amount or Decimal('0.00')) - (obj.discount_amount or Decimal('0.00'))
        return str(total)

    def get_primary_guest_name(self, obj):
        if not obj.primary_guest:
            return "Guest"
        return f"{obj.primary_guest.first_name} {obj.primary_guest.last_name}".strip()

    def get_primary_guest_phone(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.phone if contact and contact.phone else ""

    def get_primary_guest_email(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.email if contact and contact.email else ""

    def get_primary_guest_id_type(self, obj):
        if not obj.primary_guest:
            return "NATIONAL_ID"
        docs = obj.primary_guest.documents.all()
        doc = docs[0] if docs else None
        return doc.document_type if doc and doc.document_type else "NATIONAL_ID"

    def get_primary_guest_id_number(self, obj):
        if not obj.primary_guest:
            return ""
        docs = obj.primary_guest.documents.all()
        doc = docs[0] if docs else None
        if not doc or not doc.document_number:
            return ""
        doc_num = str(doc.document_number)
        import base64
        try:
            decoded = base64.b64decode(doc_num).decode('utf-8')
            if decoded.isalnum() or len(decoded) >= 4:
                return decoded
        except Exception:
            pass
        return doc_num

    def get_primary_guest_nationality(self, obj):
        if not obj.primary_guest:
            return "Indian"
        return obj.primary_guest.nationality or "Indian"

    def get_primary_guest_tier(self, obj):
        if not obj.primary_guest:
            return "STANDARD"
        return obj.primary_guest.loyalty_tier or "STANDARD"

    def get_primary_guest_city(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.city if contact and contact.city else ""

    def get_adults(self, obj):
        allocs = obj.room_allocations.all()
        return sum(getattr(a, 'adult_count', 0) for a in allocs) or 1

    def get_children(self, obj):
        allocs = obj.room_allocations.all()
        return sum(getattr(a, 'child_count', 0) for a in allocs) or 0


class ReservationSerializer(serializers.ModelSerializer):
    room_allocations = ReservationInventorySerializer(many=True, read_only=True)
    services = ReservationServiceAddonSerializer(many=True, read_only=True)
    packages = ReservationPackageSerializer(many=True, read_only=True)
    extra_charges = ReservationExtraChargeSerializer(many=True, read_only=True)
    timeline_events = ReservationEventSerializer(many=True, read_only=True)
    all_guests = serializers.SerializerMethodField()
    primary_guest_name = serializers.SerializerMethodField()
    primary_guest_phone = serializers.SerializerMethodField()
    primary_guest_email = serializers.SerializerMethodField()
    primary_guest_id_type = serializers.SerializerMethodField()
    primary_guest_id_number = serializers.SerializerMethodField()
    primary_guest_nationality = serializers.SerializerMethodField()
    primary_guest_tier = serializers.SerializerMethodField()
    primary_guest_city = serializers.SerializerMethodField()
    reservation_source_name = serializers.CharField(source='reservation_source.name', read_only=True)
    reservation_source_icon = serializers.SerializerMethodField()
    grand_total = serializers.SerializerMethodField()
    property_business_date = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    checked_in_by_name = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = (
            'id', 'tenant', 'confirmation_number', 'total_amount', 'tax_amount',
            'booking_date', 'status', 'created_at', 'updated_at'
        )

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name or ''} {obj.created_by.last_name or ''}".strip()
            return name or obj.created_by.username or "Admin"
        return "Admin"

    def get_checked_in_by_name(self, obj):
        try:
            if obj.status in ["CHECKED_IN", "CHECKED_OUT"]:
                if hasattr(obj, 'timeline_events'):
                    ci_event = obj.timeline_events.filter(event_type__icontains="CHECK_IN").first()
                    if ci_event:
                        actor = getattr(ci_event, 'actor_user', None) or getattr(ci_event, 'actor', None)
                        if actor:
                            name = f"{getattr(actor, 'first_name', '') or ''} {getattr(actor, 'last_name', '') or ''}".strip()
                            if name:
                                return name
                if obj.updated_by:
                    name = f"{obj.updated_by.first_name or ''} {obj.updated_by.last_name or ''}".strip()
                    if name:
                        return name
            if obj.created_by:
                name = f"{obj.created_by.first_name or ''} {obj.created_by.last_name or ''}".strip()
                if name:
                    return name
        except Exception:
            pass
        return "Frontdesk Agent"

    def get_actor_name(self, obj):
        return self.get_checked_in_by_name(obj)

    def get_property_business_date(self, obj):
        if obj.property and obj.property.business_date:
            return str(obj.property.business_date)
        from django.utils import timezone
        return str(timezone.localdate())

    def get_reservation_source_icon(self, obj):
        source_name = obj.reservation_source.name if obj.reservation_source else "Direct"
        return resolve_booking_source_icon(source_name)

    def get_grand_total(self, obj):
        from decimal import Decimal
        total = (obj.total_amount or Decimal('0.00')) + (obj.tax_amount or Decimal('0.00')) - (obj.discount_amount or Decimal('0.00'))
        return str(total)

    def get_primary_guest_name(self, obj):
        if not obj.primary_guest:
            return "Guest"
        return f"{obj.primary_guest.first_name} {obj.primary_guest.last_name}".strip()

    def get_primary_guest_phone(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.phone if contact and contact.phone else ""

    def get_primary_guest_email(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.email if contact and contact.email else ""

    def get_primary_guest_id_type(self, obj):
        if not obj.primary_guest:
            return "NATIONAL_ID"
        docs = obj.primary_guest.documents.all()
        doc = docs[0] if docs else None
        return doc.document_type if doc and doc.document_type else "NATIONAL_ID"

    def get_primary_guest_id_number(self, obj):
        if not obj.primary_guest:
            return ""
        docs = obj.primary_guest.documents.all()
        doc = docs[0] if docs else None
        if not doc or not doc.document_number:
            return ""
        doc_num = str(doc.document_number)
        import base64
        try:
            decoded = base64.b64decode(doc_num).decode('utf-8')
            if decoded.isalnum() or len(decoded) >= 4:
                return decoded
        except Exception:
            pass
        return doc_num

    def get_primary_guest_nationality(self, obj):
        if not obj.primary_guest:
            return "Indian"
        return obj.primary_guest.nationality or "Indian"

    def get_primary_guest_tier(self, obj):
        if not obj.primary_guest:
            return "STANDARD"
        return obj.primary_guest.loyalty_tier or "STANDARD"

    def get_primary_guest_city(self, obj):
        if not obj.primary_guest:
            return ""
        contacts = obj.primary_guest.contacts.all()
        contact = contacts[0] if contacts else None
        return contact.city if contact and contact.city else ""

    def get_all_guests(self, obj):
        guests = []
        for alloc in obj.room_allocations.all():
            for rg in alloc.guests.all():
                guests.append(ReservationGuestSerializer(rg).data)
        return guests



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
    couponCode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    paid_amount = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    paidAmount = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_method = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    paymentMethod = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payment_remark = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    paymentRemark = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Corporate fields
    corporate_po_ref = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_billing_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_employee_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_cost_center = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_gst_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    corporate_travel_purpose = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Check-in and Check-out custom times
    check_in_time = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    check_out_time = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Event fields
    event_venue = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_pax = serializers.IntegerField(required=False, default=0)
    event_start_time = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_end_time = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_organizer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_organizer_contact = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_organizer_email = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_organizer_billing_address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_seating_arrangement = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_catering_menu = serializers.CharField(required=False, allow_blank=True, allow_null=True)


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
    new_check_in_date = serializers.DateField(required=False, allow_null=True)
    new_check_out_date = serializers.DateField(required=False, allow_null=True)


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

