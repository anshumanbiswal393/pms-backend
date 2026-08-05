from rest_framework import serializers
from apps.core.common.models import (
    SystemLanguage, SystemTax, SystemDocumentType,
    SystemCurrency, SystemDateFormat, SystemTimeFormat,
    Department, Shift, OccupancyType, BookingSource,
    PaymentGateway, TenantPaymentGateway
)

class SystemLanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemLanguage
        fields = '__all__'

class SystemTaxSerializer(serializers.ModelSerializer):
    ratePercent = serializers.DecimalField(source='rate', max_digits=10, decimal_places=2, required=False)
    gstSlabMin = serializers.DecimalField(source='min_tariff', max_digits=12, decimal_places=2, required=False, allow_null=True)
    gstSlabMax = serializers.DecimalField(source='max_tariff', max_digits=12, decimal_places=2, required=False, allow_null=True)
    flatAmount = serializers.DecimalField(source='flat_amount', max_digits=12, decimal_places=2, required=False, allow_null=True)
    calculationBase = serializers.CharField(source='calculation_base', required=False)

    class Meta:
        model = SystemTax
        fields = '__all__'

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        if 'ratePercent' in data and data['ratePercent'] is not None:
            internal['rate'] = data['ratePercent']
        elif 'rate' in data and data['rate'] is not None:
            internal['rate'] = data['rate']
        if 'gstSlabMin' in data:
            internal['min_tariff'] = data['gstSlabMin']
        if 'gstSlabMax' in data:
            internal['max_tariff'] = data['gstSlabMax']
        if 'flatAmount' in data:
            internal['flat_amount'] = data['flatAmount']
        if 'calculationBase' in data and data['calculationBase']:
            internal['calculation_base'] = data['calculationBase']
        return internal

class SystemDocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemDocumentType
        fields = '__all__'

class SystemCurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemCurrency
        fields = '__all__'

class SystemDateFormatSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemDateFormat
        fields = '__all__'

class SystemTimeFormatSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemTimeFormat
        fields = '__all__'


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = '__all__'


class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shift
        fields = '__all__'


class OccupancyTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OccupancyType
        fields = '__all__'


class BookingSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingSource
        fields = '__all__'


class PaymentGatewaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentGateway
        fields = '__all__'


class TenantPaymentGatewaySerializer(serializers.ModelSerializer):
    gateway_details = PaymentGatewaySerializer(source='gateway', read_only=True)

    class Meta:
        model = TenantPaymentGateway
        fields = '__all__'

