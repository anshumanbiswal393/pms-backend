from rest_framework import serializers
from apps.core.reference.models import (
    Country, Nationality, Language, Currency, DocumentType, ReservationSource,
    Timezone, State, PaymentMode, Venue, EventType
)

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = '__all__'


class NationalitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Nationality
        fields = '__all__'


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = '__all__'


class CurrencySerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = Currency
        fields = '__all__'


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentType
        fields = '__all__'


class ReservationSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationSource
        fields = '__all__'


class TimezoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timezone
        fields = '__all__'


class StateSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source='country.name', read_only=True)

    class Meta:
        model = State
        fields = '__all__'

    def create(self, validated_data):
        return super().create(validated_data)

    def to_internal_value(self, data):
        if isinstance(data, dict) and 'country' in data and isinstance(data['country'], str):
            country_val = data['country']
            try:
                import uuid
                uuid.UUID(country_val)
            except ValueError:
                from apps.core.reference.models import Country
                country_obj = Country.objects.filter(code__iexact=country_val).first()
                if country_obj:
                    data = data.copy()
                    data['country'] = str(country_obj.id)
        return super().to_internal_value(data)


class PaymentModeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMode
        fields = '__all__'


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = '__all__'

    def to_internal_value(self, data):
        if isinstance(data, dict):
            mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
            if 'name' in mutable_data and (not mutable_data.get('code') or not str(mutable_data.get('code')).strip()):
                import re, time
                cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', mutable_data['name'].strip().lower()).strip('_')
                mutable_data['code'] = cleaned or f"venue_{int(time.time())}"
            data = mutable_data
        return super().to_internal_value(data)


class EventTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventType
        fields = '__all__'

    def to_internal_value(self, data):
        if isinstance(data, dict):
            mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
            if 'name' in mutable_data and (not mutable_data.get('code') or not str(mutable_data.get('code')).strip()):
                import re, time
                cleaned = re.sub(r'[^a-zA-Z0-9]+', '_', mutable_data['name'].strip().lower()).strip('_')
                mutable_data['code'] = cleaned or f"event_type_{int(time.time())}"
            data = mutable_data
        return super().to_internal_value(data)



