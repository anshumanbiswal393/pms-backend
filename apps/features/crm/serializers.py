from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from apps.features.crm.models import (
    GuestProfile, GuestContact, GuestDocument, GuestPreference,
    GuestTag, GuestProfileTag, GuestActivity
)
from apps.features.crm.services import EncryptionHelper

class GuestProfileSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    primary_email = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    primary_phone = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    primary_address = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()
    visits = serializers.SerializerMethodField()
    ltv = serializers.SerializerMethodField()
    nps = serializers.SerializerMethodField()
    stays = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    id_type = serializers.SerializerMethodField()
    id_number = serializers.SerializerMethodField()
    id_proof_url = serializers.SerializerMethodField()

    class Meta:
        model = GuestProfile
        fields = (
            'id', 'tenant', 'master_guest', 'first_name', 'last_name', 'name', 'date_of_birth',
            'gender', 'nationality', 'preferred_language', 'guest_type', 'loyalty_tier', 'tier',
            'loyalty_points', 'nps_score', 'nps', 'vip_notes', 'email_opt_in', 'sms_opt_in',
            'whatsapp_opt_in', 'total_stays', 'visits', 'total_nights', 'last_stay_date', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by', 'primary_email', 'email',
            'primary_phone', 'phone', 'primary_address', 'address', 'country', 'ltv',
            'stays', 'notes', 'preferences', 'tags',
            'id_type', 'id_number', 'id_proof_url'
        )
        read_only_fields = ('id', 'tenant', 'master_guest', 'created_at', 'updated_at', 'created_by', 'updated_by')

    def get_name(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return full_name or "Unnamed Guest"

    def get_primary_email(self, obj):
        primary_contact = obj.contacts.filter(is_primary=True).first()
        return primary_contact.email if primary_contact else ""

    def get_email(self, obj):
        return self.get_primary_email(obj)

    def get_primary_phone(self, obj):
        primary_contact = obj.contacts.filter(is_primary=True).first()
        return primary_contact.phone if primary_contact else ""

    def get_phone(self, obj):
        return self.get_primary_phone(obj)

    def get_primary_address(self, obj):
        primary_contact = obj.contacts.filter(is_primary=True).first()
        if primary_contact:
            parts = [primary_contact.address_line_1, primary_contact.address_line_2, primary_contact.city, primary_contact.state, primary_contact.country]
            return ", ".join([p for p in parts if p])
        return ""

    def get_address(self, obj):
        return self.get_primary_address(obj)

    def get_country(self, obj):
        primary_contact = obj.contacts.filter(is_primary=True).first()
        if primary_contact and primary_contact.country:
            return primary_contact.country
        return obj.nationality or "India"

    def get_tier(self, obj):
        tier_map = {
            'PLATINUM': 'Platinum',
            'GOLD': 'Gold',
            'SILVER': 'Silver',
            'BRONZE': 'Bronze',
            'STANDARD': 'Standard'
        }
        return tier_map.get(str(obj.loyalty_tier).upper(), str(obj.loyalty_tier).title() if obj.loyalty_tier else 'Standard')

    def get_visits(self, obj):
        from apps.features.reservations.models import Reservation
        count = Reservation.objects.filter(tenant=obj.tenant, primary_guest=obj).count()
        return max(count, obj.total_stays or 0, 1)

    def get_ltv(self, obj):
        from apps.features.reservations.models import Reservation
        from django.db.models import Sum
        res = Reservation.objects.filter(tenant=obj.tenant, primary_guest=obj)
        total = res.aggregate(total=Sum('paid_amount'))['total'] or 0
        if total == 0:
            total = res.aggregate(total=Sum('total_amount'))['total'] or 0
        return float(total)

    def get_nps(self, obj):
        return obj.nps_score if obj.nps_score is not None else 8

    def get_stays(self, obj):
        from apps.features.reservations.models import Reservation
        reservations = Reservation.objects.filter(tenant=obj.tenant, primary_guest=obj).order_by('-created_at')[:10]
        stays_list = []
        for r in reservations:
            first_alloc = r.room_allocations.first()
            room_name = "Room"
            if first_alloc:
                if first_alloc.inventory_unit:
                    room_name = first_alloc.inventory_unit.name
                elif first_alloc.inventory_snapshot and isinstance(first_alloc.inventory_snapshot, dict):
                    room_name = first_alloc.inventory_snapshot.get('name', 'Room')
                elif first_alloc.inventory_unit_type:
                    room_name = first_alloc.inventory_unit_type.name

            stays_list.append({
                'id': str(r.id),
                'room': room_name,
                'ci': str(r.arrival_date),
                'co': str(r.departure_date),
                'amount': float(r.paid_amount or r.total_amount or 0),
                'status': r.status
            })
        return stays_list

    def get_notes(self, obj):
        notes_list = []
        if obj.vip_notes:
            notes_list.append({
                'at': obj.created_at.strftime('%d %b %Y') if obj.created_at else 'Recent',
                'author': 'Staff',
                'text': obj.vip_notes
            })
        for act in obj.activities.order_by('-timestamp')[:5]:
            notes_list.append({
                'at': act.timestamp.strftime('%d %b %Y') if act.timestamp else 'Recent',
                'author': act.staff.username if act.staff else 'System',
                'text': f"{act.activity_type}: {act.details or ''}"
            })
        return notes_list

    def get_preferences(self, obj):
        return list(obj.preferences.values_list('preference_value', flat=True))

    def get_tags(self, obj):
        return list(obj.profile_tags.values_list('tag__name', flat=True))

    def get_id_type(self, obj):
        primary_doc = obj.documents.first()
        return primary_doc.document_type if primary_doc else ""

    def get_id_proof_url(self, obj):
        primary_doc = obj.documents.first()
        return primary_doc.attachment_url if primary_doc else ""

    def get_id_number(self, obj):
        primary_doc = obj.documents.first()
        if primary_doc:
            return EncryptionHelper.decrypt(primary_doc.document_number)
        return ""

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if request:
            email = request.data.get('primary_email')
            phone = request.data.get('primary_phone')
            address = request.data.get('primary_address')
            
            if email is not None or phone is not None or address is not None:
                contact = instance.contacts.filter(is_primary=True).first()
                if contact:
                    if email is not None: contact.email = email
                    if phone is not None: contact.phone = phone
                    if address is not None: contact.address_line_1 = address
                    contact.save()
                else:
                    GuestContact.objects.create(
                        tenant=instance.tenant,
                        guest=instance,
                        email=email or "",
                        phone=phone or "",
                        address_line_1=address or "",
                        is_primary=True
                    )
            
            id_type = request.data.get('id_type')
            id_number = request.data.get('id_number')
            id_proof_url = request.data.get('id_proof_url')
            
            if id_type is not None or id_number is not None or id_proof_url is not None:
                doc = instance.documents.first()
                doc_type = 'PASSPORT'
                if id_type:
                    id_type_upper = id_type.upper()
                    if 'ID' in id_type_upper or 'CARD' in id_type_upper or 'AADHAAR' in id_type_upper:
                        doc_type = 'NATIONAL_ID'
                    elif 'LICENSE' in id_type_upper or 'LICENCE' in id_type_upper or 'DRIVING' in id_type_upper:
                        doc_type = 'DRIVING_LICENCE'
                
                if doc:
                    if id_type is not None: doc.document_type = doc_type
                    if id_number is not None: doc.document_number = id_number
                    if id_proof_url is not None: doc.attachment_url = id_proof_url
                    doc.save()
                else:
                    GuestDocument.objects.create(
                        tenant=instance.tenant,
                        guest=instance,
                        document_type=doc_type,
                        document_number=id_number or "",
                        attachment_url=id_proof_url or "",
                        is_verified=False
                    )
                    
        return super().update(instance, validated_data)

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = request.user if request and request.user.is_authenticated else None
        return super().create(validated_data)


class GuestContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestContact
        fields = '__all__'
        read_only_fields = ('id', 'tenant')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        guest = data.get('guest')
        if guest and guest.tenant != tenant:
            raise ValidationError("Guest must belong to the resolved tenant context.")

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class GuestDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestDocument
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'is_verified')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        guest = data.get('guest')
        if guest and guest.tenant != tenant:
            raise ValidationError("Guest must belong to the resolved tenant context.")

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        
        # Encrypt document number
        doc_num = validated_data.get('document_number')
        if doc_num:
            validated_data['document_number'] = EncryptionHelper.encrypt(doc_num)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        doc_num = validated_data.get('document_number')
        if doc_num:
            validated_data['document_number'] = EncryptionHelper.encrypt(doc_num)
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['document_number'] = EncryptionHelper.decrypt(instance.document_number)
        return ret


class GuestPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestPreference
        fields = '__all__'
        read_only_fields = ('id', 'tenant')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)

        guest = data.get('guest')
        if guest and guest.tenant != tenant:
            raise ValidationError("Guest must belong to the resolved tenant context.")

        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class GuestTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestTag
        fields = '__all__'
        read_only_fields = ('id', 'tenant')

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        validated_data['tenant'] = tenant
        return super().create(validated_data)


class GuestProfileTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestProfileTag
        fields = '__all__'
        read_only_fields = ('id',)

    def validate(self, data):
        guest = data.get('guest')
        tag = data.get('tag')
        
        if tag.tenant and tag.tenant != guest.tenant:
            raise ValidationError("Custom tags must belong to the same tenant as the guest profile.")

        return data


class GuestActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestActivity
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'timestamp')


class MergeProfilesRequestSerializer(serializers.Serializer):
    duplicate_guest_id = serializers.UUIDField()


class AddLoyaltyPointsSerializer(serializers.Serializer):
    points = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(max_length=255)


class AssignTagRequestSerializer(serializers.Serializer):
    tag_code = serializers.CharField(max_length=32)
