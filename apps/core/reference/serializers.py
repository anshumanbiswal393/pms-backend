from rest_framework import serializers
from apps.core.reference.models import Country, Nationality, Language, Currency, DocumentType, ReservationSource, Timezone, State, PaymentMode

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


