from rest_framework import serializers
from apps.features.billing.models import TaxRate, Invoice, InvoiceLineItem, CreditNote, BillingAdjustment

class TaxRateSerializer(serializers.ModelSerializer):
    rate = serializers.DecimalField(source='percentage', max_digits=5, decimal_places=2, required=False)
    ratePercent = serializers.DecimalField(source='percentage', max_digits=5, decimal_places=2, required=False)
    status = serializers.SerializerMethodField()

    gstSlabMin = serializers.DecimalField(source='min_tariff', max_digits=12, decimal_places=2, required=False, allow_null=True)
    gstSlabMax = serializers.DecimalField(source='max_tariff', max_digits=12, decimal_places=2, required=False, allow_null=True)
    flatAmount = serializers.DecimalField(source='flat_amount', max_digits=12, decimal_places=2, required=False, allow_null=True)
    calculationBase = serializers.CharField(source='calculation_base', required=False)

    class Meta:
        model = TaxRate
        fields = '__all__'
        extra_kwargs = {
            'code': {'required': False},
            'name': {'required': False},
            'percentage': {'required': False},
        }

    def get_status(self, obj):
        return "active" if obj.is_active else "inactive"

    def to_internal_value(self, data):
        internal = super().to_internal_value(data)
        if 'ratePercent' in data and data['ratePercent'] is not None:
            internal['percentage'] = data['ratePercent']
        elif 'rate' in data and data['rate'] is not None:
            internal['percentage'] = data['rate']
        if 'gstSlabMin' in data:
            internal['min_tariff'] = data['gstSlabMin']
        if 'gstSlabMax' in data:
            internal['max_tariff'] = data['gstSlabMax']
        if 'flatAmount' in data:
            internal['flat_amount'] = data['flatAmount']
        if 'calculationBase' in data and data['calculationBase']:
            internal['calculation_base'] = data['calculationBase']
        if 'status' in data:
            internal['is_active'] = str(data['status']).lower() in ['active', 'true', '1']
        return internal

class InvoiceLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLineItem
        fields = '__all__'

class InvoiceSerializer(serializers.ModelSerializer):
    line_items = InvoiceLineItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Invoice
        fields = '__all__'

class CreditNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditNote
        fields = '__all__'

class BillingAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingAdjustment
        fields = '__all__'
