from rest_framework import serializers
from apps.features.billing.models import TaxRate, Invoice, InvoiceLineItem, CreditNote, BillingAdjustment

class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = '__all__'

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
