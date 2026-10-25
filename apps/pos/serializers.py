from rest_framework import serializers
from apps.POS.models import (
    Outlet,
    FloorSection,
    RestaurantTable,
    POSRegister,
    DeviceMapping,
    TaxProfile,
    MenuCategory,
    MenuItem,
    MenuVariant,
    ModifierGroup,
    ModifierOption,
    SpecialNote,
)

class DeviceMappingSerializer(serializers.ModelSerializer):
    register_name = serializers.CharField(source='register.name', read_only=True)
    register_code = serializers.CharField(source='register.register_code', read_only=True)

    class Meta:
        model = DeviceMapping
        fields = [
            'id',
            'register',
            'register_name',
            'register_code',
            'device_name',
            'device_fingerprint',
            'platform',
            'ip_address',
            'mac_address',
            'app_version',
            'status',
            'last_heartbeat',
            'is_authorized',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSRegisterSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    devices_count = serializers.SerializerMethodField()
    devices = DeviceMappingSerializer(many=True, read_only=True)

    class Meta:
        model = POSRegister
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'register_code',
            'name',
            'register_type',
            'is_active',
            'meta_config',
            'devices_count',
            'devices',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_devices_count(self, obj):
        return obj.devices.count()


class RestaurantTableSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source='section.name', read_only=True)
    outlet_id = serializers.UUIDField(source='section.outlet.id', read_only=True)
    outlet_name = serializers.CharField(source='section.outlet.name', read_only=True)
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantTable
        fields = [
            'id',
            'section',
            'section_name',
            'outlet_id',
            'outlet_name',
            'table_number',
            'capacity',
            'min_capacity',
            'status',
            'shape',
            'pos_x',
            'pos_y',
            'width',
            'height',
            'qr_code_token',
            'qr_code_url',
            'is_active',
            'active_order_id',
            'active_waiter_name',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'qr_code_token', 'created_at', 'updated_at']

    def get_qr_code_url(self, obj):
        request = self.context.get('request')
        base_url = request.build_absolute_uri('/')[:-1] if request else ''
        return f"{base_url}/pos/dine-in/qr/{obj.qr_code_token}/"


class TableStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=RestaurantTable.TABLE_STATUS_CHOICES)
    notes = serializers.CharField(required=False, allow_blank=True)
    active_waiter_name = serializers.CharField(required=False, allow_blank=True)
    active_order_id = serializers.UUIDField(required=False, allow_null=True)


class TableTransferSerializer(serializers.Serializer):
    source_table_id = serializers.UUIDField(required=True)
    destination_table_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(required=False, default="Guest table transfer")


class FloorSectionSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    tables_count = serializers.SerializerMethodField()
    vacant_tables_count = serializers.SerializerMethodField()
    occupied_tables_count = serializers.SerializerMethodField()
    tables = RestaurantTableSerializer(many=True, read_only=True)

    class Meta:
        model = FloorSection
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'name',
            'code',
            'sort_order',
            'is_active',
            'tables_count',
            'vacant_tables_count',
            'occupied_tables_count',
            'tables',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_tables_count(self, obj):
        return obj.tables.filter(is_active=True).count()

    def get_vacant_tables_count(self, obj):
        return obj.tables.filter(is_active=True, status='VACANT').count()

    def get_occupied_tables_count(self, obj):
        return obj.tables.filter(is_active=True, status__in=['OCCUPIED', 'BILLED']).count()


class OutletSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    sections_count = serializers.SerializerMethodField()
    tables_count = serializers.SerializerMethodField()
    # UI form helpers (stored in meta_settings; not top-level columns)
    alias = serializers.CharField(required=False, allow_blank=True, write_only=True)
    landmark = serializers.CharField(required=False, allow_blank=True, write_only=True)
    zip_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    zipCode = serializers.CharField(required=False, allow_blank=True, write_only=True)
    fax = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tin_no = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tinNo = serializers.CharField(required=False, allow_blank=True, write_only=True)
    country = serializers.CharField(required=False, allow_blank=True, write_only=True)
    state = serializers.CharField(required=False, allow_blank=True, write_only=True)
    city = serializers.CharField(required=False, allow_blank=True, write_only=True)
    timezone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    address = serializers.CharField(required=False, allow_blank=True, write_only=True)
    area = serializers.CharField(required=False, allow_blank=True, write_only=True)
    latitude = serializers.CharField(required=False, allow_blank=True, write_only=True)
    longitude = serializers.CharField(required=False, allow_blank=True, write_only=True)
    owner_mobile = serializers.CharField(required=False, allow_blank=True, write_only=True)
    ownerMobile = serializers.CharField(required=False, allow_blank=True, write_only=True)
    direct_number = serializers.CharField(required=False, allow_blank=True, write_only=True)
    directNumber = serializers.CharField(required=False, allow_blank=True, write_only=True)
    decision_maker = serializers.CharField(required=False, allow_blank=True, write_only=True)
    decisionMaker = serializers.CharField(required=False, allow_blank=True, write_only=True)
    kitchen_code = serializers.CharField(required=False, allow_blank=True, write_only=True)
    kitchenCode = serializers.CharField(required=False, allow_blank=True, write_only=True)
    seating_capacity = serializers.CharField(required=False, allow_blank=True, write_only=True)
    seatingCapacity = serializers.CharField(required=False, allow_blank=True, write_only=True)
    additional_info = serializers.CharField(required=False, allow_blank=True, write_only=True)
    additionalInfo = serializers.CharField(required=False, allow_blank=True, write_only=True)
    form_type = serializers.CharField(required=False, allow_blank=True, write_only=True)
    formType = serializers.CharField(required=False, allow_blank=True, write_only=True)
    parent_outlet_id = serializers.CharField(required=False, allow_blank=True, write_only=True)
    parentOutletId = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Outlet
        fields = [
            'id',
            'tenant',
            'tenant_name',
            'property',
            'property_name',
            'code',
            'name',
            'outlet_type',
            'cuisine',
            'fssai_license',
            'gstin',
            'phone',
            'email',
            'service_charge_percentage',
            'default_cgst_rate',
            'default_sgst_rate',
            'default_vat_rate',
            'currency',
            'is_active',
            'opening_time',
            'closing_time',
            'meta_settings',
            'sections_count',
            'tables_count',
            'created_at',
            'updated_at',
            'alias',
            'landmark',
            'zip_code',
            'zipCode',
            'fax',
            'tin_no',
            'tinNo',
            'country',
            'state',
            'city',
            'timezone',
            'address',
            'area',
            'latitude',
            'longitude',
            'owner_mobile',
            'ownerMobile',
            'direct_number',
            'directNumber',
            'decision_maker',
            'decisionMaker',
            'kitchen_code',
            'kitchenCode',
            'seating_capacity',
            'seatingCapacity',
            'additional_info',
            'additionalInfo',
            'form_type',
            'formType',
            'parent_outlet_id',
            'parentOutletId',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'tenant': {'required': False, 'allow_null': True},
            'property': {'required': False, 'allow_null': True},
            'code': {'required': False, 'allow_blank': True},
        }
        # UniqueTogetherValidator requires property+code upfront; we resolve in validate().
        validators = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow UI create without tenant/property/code — filled in validate().
        for name in ('tenant', 'property', 'code'):
            if name in self.fields:
                self.fields[name].required = False
                if hasattr(self.fields[name], 'allow_null'):
                    self.fields[name].allow_null = True
                if hasattr(self.fields[name], 'allow_blank'):
                    self.fields[name].allow_blank = True

    def get_sections_count(self, obj):
        return obj.sections.filter(is_active=True).count()

    def get_tables_count(self, obj):
        return RestaurantTable.objects.filter(section__outlet=obj, is_active=True).count()

    def _extract_meta_extras(self, validated_data):
        """Pull UI-only fields out of validated_data into meta_settings."""
        meta = dict(validated_data.pop('meta_settings', None) or {})
        mapping = (
            ('alias', ('alias',)),
            ('landmark', ('landmark',)),
            ('zip_code', ('zip_code', 'zipCode')),
            ('fax', ('fax',)),
            ('tin_no', ('tin_no', 'tinNo')),
            ('country', ('country',)),
            ('state', ('state',)),
            ('city', ('city',)),
            ('timezone', ('timezone',)),
            ('address', ('address',)),
            ('area', ('area',)),
            ('latitude', ('latitude',)),
            ('longitude', ('longitude',)),
            ('owner_mobile', ('owner_mobile', 'ownerMobile')),
            ('direct_number', ('direct_number', 'directNumber')),
            ('decision_maker', ('decision_maker', 'decisionMaker')),
            ('kitchen_code', ('kitchen_code', 'kitchenCode')),
            ('seating_capacity', ('seating_capacity', 'seatingCapacity')),
            ('additional_info', ('additional_info', 'additionalInfo')),
            ('form_type', ('form_type', 'formType')),
            ('parent_outlet_id', ('parent_outlet_id', 'parentOutletId')),
        )
        for dest, keys in mapping:
            for key in keys:
                if key in validated_data:
                    value = validated_data.pop(key)
                    if value not in (None, ''):
                        meta[dest] = value
                    break
        return meta

    def validate(self, attrs):
        request = self.context.get('request')
        raw = getattr(request, 'data', {}) if request is not None else {}
        if hasattr(raw, 'dict'):
            raw = raw.dict()
        elif not isinstance(raw, dict):
            try:
                raw = dict(raw)
            except Exception:
                raw = {}

        seed = Outlet.objects.order_by('created_at').first()

        if not attrs.get('tenant'):
            tenant_id = (
                raw.get('tenant')
                or raw.get('tenant_id')
                or raw.get('tenantId')
                or (request.query_params.get('tenant_id') if request else None)
                or (request.headers.get('X-Tenant-ID') if request else None)
            )
            if tenant_id:
                from apps.core.tenants.models import Tenant

                attrs['tenant'] = Tenant.objects.filter(pk=tenant_id).first()
            elif seed:
                attrs['tenant'] = seed.tenant
            else:
                raise serializers.ValidationError(
                    {'tenant': 'tenant is required when no existing POS outlet exists.'}
                )

        if not attrs.get('property'):
            property_id = (
                raw.get('property')
                or raw.get('property_id')
                or raw.get('propertyId')
                or (request.query_params.get('property_id') if request else None)
                or (request.headers.get('X-Property-ID') if request else None)
            )
            if property_id:
                from apps.core.tenants.models import Property

                attrs['property'] = Property.objects.filter(pk=property_id).first()
            elif seed:
                attrs['property'] = seed.property
            else:
                raise serializers.ValidationError(
                    {'property': 'property is required when no existing POS outlet exists.'}
                )

        if not attrs.get('tenant') or not attrs.get('property'):
            raise serializers.ValidationError(
                {'detail': 'Unable to resolve tenant/property for new outlet.'}
            )

        code = (attrs.get('code') or raw.get('code') or '').strip().upper()
        property_id = attrs['property'].id
        if not code:
            alias = raw.get('alias') or raw.get('kitchenCode') or raw.get('kitchen_code') or ''
            base = ''.join(ch for ch in str(alias).upper() if ch.isalnum())[:8] or 'OUT'
            candidate = base
            n = 1
            qs = Outlet.objects.all_with_deleted()
            while qs.filter(property_id=property_id, code=candidate).exists():
                n += 1
                candidate = f'{base}-{n}'
            attrs['code'] = candidate
        else:
            attrs['code'] = code
            if (
                Outlet.objects.all_with_deleted()
                .filter(property_id=property_id, code=attrs['code'])
                .exclude(pk=getattr(self.instance, 'pk', None))
                .exists()
            ):
                raise serializers.ValidationError(
                    {'code': f'Outlet code {attrs["code"]} already exists for this property.'}
                )

        raw_type = (attrs.get('outlet_type') or raw.get('outlet_type') or '').upper().replace(' ', '_')
        type_map = {
            'HO': 'HO',
            'HEAD_OFFICE': 'HO',
            'KITCHEN': 'KITCHEN',
            'CENTRAL_KITCHEN': 'KITCHEN',
            'PRIMARY': 'PRIMARY',
            'VIRTUAL': 'VIRTUAL',
            'CLOUD_KITCHEN': 'VIRTUAL',
            'BAR': 'BAR',
            'ROOM_SERVICE': 'ROOM_SERVICE',
            'BANQUET': 'BANQUET',
            'CAFE': 'CAFE',
        }
        if raw_type:
            attrs['outlet_type'] = type_map.get(raw_type, raw_type)
        return attrs

    def create(self, validated_data):
        meta = self._extract_meta_extras(validated_data)
        validated_data['meta_settings'] = meta
        validated_data.pop('tenant_id', None)
        validated_data.pop('property_id', None)
        if not validated_data.get('phone'):
            phone = meta.get('owner_mobile') or meta.get('direct_number')
            if phone:
                validated_data['phone'] = str(phone)[:32]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        meta = self._extract_meta_extras(validated_data)
        merged = dict(instance.meta_settings or {})
        merged.update(meta)
        validated_data['meta_settings'] = merged
        if 'code' in validated_data and validated_data['code']:
            validated_data['code'] = str(validated_data['code']).strip().upper()
        return super().update(instance, validated_data)


class OutletLiveFloorMapSerializer(serializers.ModelSerializer):
    """
    High performance serializer that outputs complete live floor plan
    with sections and real-time colored tables in one JSON payload.
    """
    sections = FloorSectionSerializer(many=True, read_only=True)
    total_capacity = serializers.SerializerMethodField()

    class Meta:
        model = Outlet
        fields = [
            'id',
            'code',
            'name',
            'outlet_type',
            'is_active',
            'currency',
            'total_capacity',
            'sections',
        ]

    def get_total_capacity(self, obj):
        tables = RestaurantTable.objects.filter(section__outlet=obj, is_active=True)
        return sum(t.capacity for t in tables)


class OccupiedRoomSerializer(serializers.Serializer):
    """Read-only DTO for POS Room Service / billing room picker (PMS in-house stays)."""

    room_number = serializers.CharField()
    unit_id = serializers.CharField(allow_null=True)
    unit_type = serializers.CharField(allow_null=True, required=False)
    floor = serializers.CharField(allow_null=True, required=False)
    reservation_id = serializers.CharField()
    confirmation_number = serializers.CharField()
    allocation_id = serializers.CharField()
    guest_name = serializers.CharField()
    guest_phone = serializers.CharField()
    guest_id = serializers.CharField(allow_null=True, required=False)
    pax = serializers.IntegerField()
    adult_count = serializers.IntegerField(required=False)
    child_count = serializers.IntegerField(required=False)
    arrival_date = serializers.CharField(allow_null=True, required=False)
    departure_date = serializers.CharField(allow_null=True, required=False)
    folio_id = serializers.CharField(allow_null=True)
    folio_number = serializers.CharField(allow_null=True)
    folio_status = serializers.CharField(allow_null=True)
    balance = serializers.CharField()
    is_open_for_charges = serializers.BooleanField()
    property_id = serializers.CharField()
    tenant_id = serializers.CharField()


class OccupiedRoomsResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    rooms = OccupiedRoomSerializer(many=True)


class TaxProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxProfile
        fields = [
            'id',
            'tenant',
            'property',
            'code',
            'name',
            'rate',
            'cgst_rate',
            'sgst_rate',
            'igst_rate',
            'is_inclusive',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MenuCategorySerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    parent_name = serializers.CharField(source='parent.name', read_only=True, allow_null=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = MenuCategory
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'code',
            'name',
            'online_display_name',
            'parent',
            'parent_name',
            'sort_order',
            'image_url',
            'is_active',
            'item_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_item_count(self, obj):
        return obj.items.filter(deleted_at__isnull=True).count()


class MenuVariantSerializer(serializers.ModelSerializer):
    menu_item = serializers.PrimaryKeyRelatedField(read_only=True, required=False)

    class Meta:
        model = MenuVariant
        fields = [
            'id',
            'menu_item',
            'name',
            'price',
            'sort_order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'menu_item', 'created_at', 'updated_at']


class ModifierOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModifierOption
        fields = [
            'id',
            'group',
            'name',
            'price',
            'sort_order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ModifierGroupSerializer(serializers.ModelSerializer):
    options = ModifierOptionSerializer(many=True, read_only=True)
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = ModifierGroup
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'name',
            'code',
            'min_select',
            'max_select',
            'is_required',
            'is_active',
            'menu_items',
            'options',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MenuItemWriteSerializer(serializers.ModelSerializer):
    """Create/update payload. Accepts snake_case or POS UI camelCase."""
    variants = MenuVariantSerializer(many=True, required=False)

    class Meta:
        model = MenuItem
        fields = [
            'id',
            'outlet',
            'category',
            'tax_profile',
            'code',
            'name',
            'online_display_name',
            'item_type',
            'price',
            'description',
            'status',
            'images',
            'base_menu',
            'zomato',
            'swiggy',
            'direct',
            'sort_order',
            'next_available_at',
            'meta',
            'variants',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_internal_value(self, data):
        data = dict(data or {})
        if data.get("outletId") and not data.get("outlet"):
            data["outlet"] = data["outletId"]
        if data.get("outlet_id") and not data.get("outlet"):
            data["outlet"] = data["outlet_id"]
        category_raw = data.get("categoryId") or data.get("category_id") or data.get("category")
        outlet_raw = data.get("outlet")
        if category_raw and outlet_raw:
            cat = None
            try:
                cat = MenuCategory.objects.filter(
                    pk=category_raw, deleted_at__isnull=True
                ).first()
            except (ValueError, TypeError):
                cat = None
            if not cat:
                cat = MenuCategory.objects.filter(
                    outlet_id=outlet_raw,
                    name__iexact=str(category_raw).strip(),
                    deleted_at__isnull=True,
                ).first()
            if not cat and str(category_raw).strip():
                cat = MenuCategory.objects.create(
                    outlet_id=outlet_raw,
                    name=str(category_raw).strip(),
                    is_active=True,
                )
            if cat:
                data["category"] = str(cat.id)
        if data.get("onlineDisplayName") and not data.get("online_display_name"):
            data["online_display_name"] = data["onlineDisplayName"]
        if data.get("baseMenu") is not None and "base_menu" not in data:
            data["base_menu"] = data["baseMenu"]
        item_type = data.get("item_type") or data.get("itemType")
        if item_type:
            mapped = {
                "Veg": "VEG",
                "VEG": "VEG",
                "Non-Veg": "NON_VEG",
                "NON_VEG": "NON_VEG",
                "non_veg": "NON_VEG",
                "Egg": "EGG",
                "EGG": "EGG",
            }.get(str(item_type), str(item_type).upper().replace("-", "_").replace(" ", "_"))
            data["item_type"] = mapped
        status_val = data.get("status")
        if status_val:
            mapped_status = {
                "Active": "ACTIVE",
                "ACTIVE": "ACTIVE",
                "Inactive": "INACTIVE",
                "INACTIVE": "INACTIVE",
            }.get(str(status_val), str(status_val).upper())
            data["status"] = mapped_status
        commission_type = data.get("commissionType") or data.get("commission_type")
        commission_value = data.get("commissionValue") if "commissionValue" in data else data.get("commission_value")
        if commission_type is not None or commission_value is not None:
            meta = dict(data.get("meta") or {})
            type_map = {
                "Not Configured": "NONE",
                "NONE": "NONE",
                "Percentage": "PERCENT",
                "PERCENT": "PERCENT",
                "Fixed Amount": "FIXED",
                "FIXED": "FIXED",
            }
            meta["commission"] = {
                "type": type_map.get(str(commission_type or "NONE"), "NONE"),
                "value": commission_value,
            }
            data["meta"] = meta
        tax_rate = data.get("taxRate") if "taxRate" in data else data.get("tax_rate")
        if tax_rate is not None and not data.get("tax_profile") and not data.get("taxProfileId"):
            from apps.POS.services.menu import MenuCatalogService
            from decimal import Decimal

            outlet = None
            try:
                outlet = Outlet.objects.filter(pk=data.get("outlet")).first()
            except Exception:
                outlet = None
            if outlet:
                profile = MenuCatalogService.resolve_or_create_tax_profile(
                    tenant_id=outlet.tenant_id,
                    rate=Decimal(str(tax_rate or 0)),
                    property_id=outlet.property_id,
                )
                data["tax_profile"] = str(profile.id)
        if data.get("taxProfileId") and not data.get("tax_profile"):
            data["tax_profile"] = data["taxProfileId"]
        variants = data.get("variants")
        if isinstance(variants, list):
            clean = []
            for idx, variant in enumerate(variants):
                if not isinstance(variant, dict):
                    continue
                clean.append(
                    {
                        "name": variant.get("name") or "Regular",
                        "price": variant.get("price") or 0,
                        "sort_order": variant.get("sort_order", idx),
                        "is_active": variant.get("is_active", True),
                    }
                )
            data["variants"] = clean
        return super().to_internal_value(data)

    def _sync_variants(self, item, variants_data):
        allowed = ('name', 'price', 'sort_order', 'is_active')
        for idx, variant in enumerate(variants_data):
            payload = {k: variant[k] for k in allowed if k in variant}
            payload.setdefault('sort_order', idx)
            payload.setdefault('is_active', True)
            MenuVariant.objects.create(menu_item=item, **payload)

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        item = MenuItem.objects.create(**validated_data)
        self._sync_variants(item, variants_data)
        return item

    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if variants_data is not None:
            instance.variants.all().delete()
            self._sync_variants(instance, variants_data)
        return instance


class MenuItemUISerializer(serializers.Serializer):
    """Read DTO matching POS UI MenuItem (camelCase)."""
    id = serializers.CharField()
    outletId = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    onlineDisplayName = serializers.CharField()
    category = serializers.CharField()
    categoryId = serializers.CharField(allow_null=True, required=False)
    itemType = serializers.CharField()
    price = serializers.FloatField()
    taxRate = serializers.FloatField()
    taxProfileId = serializers.CharField(allow_null=True, required=False)
    status = serializers.CharField()
    description = serializers.CharField(allow_blank=True, required=False)
    images = serializers.ListField(child=serializers.DictField(), required=False)
    variants = serializers.ListField(child=serializers.DictField(), required=False)
    modifierGroups = serializers.ListField(child=serializers.DictField(), required=False)
    baseMenu = serializers.BooleanField()
    zomato = serializers.BooleanField()
    swiggy = serializers.BooleanField()
    direct = serializers.BooleanField()
    nextAvailableTime = serializers.CharField(allow_null=True, required=False)
    updatedAt = serializers.CharField(allow_blank=True, required=False)


class BulkPlatformUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    updates = serializers.DictField()


class SpecialNoteSerializer(serializers.ModelSerializer):
    available = serializers.BooleanField(source='is_available')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = SpecialNote
        fields = ['id', 'outlet', 'tenant', 'name', 'available', 'sort_order', 'createdAt']
        read_only_fields = ['id', 'createdAt']


class POSOrderItemInputSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_null=True)
    menu_item_id = serializers.UUIDField(required=False, allow_null=True)
    menuItemId = serializers.UUIDField(required=False, allow_null=True)
    code = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    selectedVariantName = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2)
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    taxRate = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    diet = serializers.CharField(required=False, allow_blank=True)


class POSOrderCreateSerializer(serializers.Serializer):
    outlet_id = serializers.UUIDField(required=False)
    outletId = serializers.UUIDField(required=False)
    outlet = serializers.UUIDField(required=False)
    order_type = serializers.CharField(required=False, default="DINE_IN")
    orderType = serializers.CharField(required=False)
    table_id = serializers.UUIDField(required=False, allow_null=True)
    tableId = serializers.UUIDField(required=False, allow_null=True)
    table_number = serializers.CharField(required=False, allow_blank=True)
    tableNumber = serializers.CharField(required=False, allow_blank=True)
    section = serializers.CharField(required=False, allow_blank=True)
    room_unit_id = serializers.UUIDField(required=False, allow_null=True)
    roomUnitId = serializers.UUIDField(required=False, allow_null=True)
    room_number = serializers.CharField(required=False, allow_blank=True)
    roomNumber = serializers.CharField(required=False, allow_blank=True)
    reservation_id = serializers.UUIDField(required=False, allow_null=True)
    reservationId = serializers.UUIDField(required=False, allow_null=True)
    folio_id = serializers.UUIDField(required=False, allow_null=True)
    folioId = serializers.UUIDField(required=False, allow_null=True)
    guest_name = serializers.CharField(required=False, allow_blank=True)
    guestName = serializers.CharField(required=False, allow_blank=True)
    guest_phone = serializers.CharField(required=False, allow_blank=True)
    guestPhone = serializers.CharField(required=False, allow_blank=True)
    waiter_name = serializers.CharField(required=False, allow_blank=True)
    waiterName = serializers.CharField(required=False, allow_blank=True)
    pax = serializers.IntegerField(required=False, default=1)
    order_note = serializers.CharField(required=False, allow_blank=True)
    orderNote = serializers.CharField(required=False, allow_blank=True)
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    tax_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    taxAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    service_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    serviceCharge = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    discountAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    grand_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    grandTotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    payment_mode = serializers.CharField(required=False, allow_null=True)
    paymentMode = serializers.CharField(required=False, allow_null=True)
    mark_settled = serializers.BooleanField(required=False, default=False)
    markSettled = serializers.BooleanField(required=False)
    send_kot = serializers.BooleanField(required=False, default=True)
    sendKot = serializers.BooleanField(required=False)
    items = POSOrderItemInputSerializer(many=True)

    def to_internal_value(self, data):
        data = dict(data or {})
        for key in (
            "tableId",
            "table_id",
            "table",
            "roomUnitId",
            "room_unit_id",
            "reservationId",
            "reservation_id",
            "folioId",
            "folio_id",
        ):
            if data.get(key) in ("", None):
                data.pop(key, None)
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not (
            attrs.get("outlet_id") or attrs.get("outletId") or attrs.get("outlet")
        ):
            raise serializers.ValidationError(
                {"outlet_id": "outlet_id (or outletId) is required."}
            )
        if not attrs.get("items"):
            raise serializers.ValidationError({"items": "At least one item is required."})
        return attrs


class POSOrderUpdateSerializer(serializers.Serializer):
    guest_name = serializers.CharField(required=False, allow_blank=True)
    guestName = serializers.CharField(required=False, allow_blank=True)
    guest_phone = serializers.CharField(required=False, allow_blank=True)
    guestPhone = serializers.CharField(required=False, allow_blank=True)
    waiter_name = serializers.CharField(required=False, allow_blank=True)
    waiterName = serializers.CharField(required=False, allow_blank=True)
    pax = serializers.IntegerField(required=False)
    order_note = serializers.CharField(required=False, allow_blank=True)
    orderNote = serializers.CharField(required=False, allow_blank=True)
    subtotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    grand_total = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    grandTotal = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    service_charge = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    serviceCharge = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    discountAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    items = POSOrderItemInputSerializer(many=True, required=False)


class POSSettlePaymentLegSerializer(serializers.Serializer):
    mode = serializers.CharField(required=False)
    payment_mode = serializers.CharField(required=False)
    paymentMode = serializers.CharField(required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True)


class POSOrderSettleSerializer(serializers.Serializer):
    payment_mode = serializers.CharField(required=False)
    paymentMode = serializers.CharField(required=False)
    reservation_id = serializers.UUIDField(required=False, allow_null=True)
    reservationId = serializers.UUIDField(required=False, allow_null=True)
    folio_id = serializers.UUIDField(required=False, allow_null=True)
    folioId = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    idempotencyKey = serializers.CharField(required=False, allow_blank=True)
    tendered_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    tenderedAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    reference = serializers.CharField(required=False, allow_blank=True)
    payments = POSSettlePaymentLegSerializer(many=True, required=False)

    def validate(self, attrs):
        mode = attrs.get("payment_mode") or attrs.get("paymentMode")
        if not mode:
            raise serializers.ValidationError(
                {"payment_mode": "payment_mode (or paymentMode) is required."}
            )
        return attrs


class POSDueSettleSerializer(serializers.Serializer):
    payment_mode = serializers.CharField(required=False)
    paymentMode = serializers.CharField(required=False)
    settlementMode = serializers.CharField(required=False)
    paid_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    paidAmount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    reference = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        mode = (
            attrs.get("payment_mode")
            or attrs.get("paymentMode")
            or attrs.get("settlementMode")
        )
        if not mode:
            raise serializers.ValidationError(
                {"payment_mode": "payment_mode is required."}
            )
        return attrs
