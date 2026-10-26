import uuid
from decimal import Decimal
from rest_framework import serializers
from django.utils import timezone
from apps.POS.models_management import (
    POSOutletConfig,
    POSSubOrderType,
    POSAreaDeliveryCharge,
    POSDeliveryDistanceSlab,
    POSEmailTemplate,
    POSBankAccount,
    POSCashierShift,
    POSCashDrawerMovement,
    POSCashDenomination,
    POSExpense,
    POSGstSetting,
    POSKycDocument,
    POSLoanFacility,
    POSOnlineReconciliation,
    POSPaymentGatewayConfig,
    POSServicePaymentRecord,
    POSUtilityBill,
    POSVirtualWallet,
    POSVirtualWalletTransaction,
    POSBillerGroup,
    POSStaffUser,
    POSManagementLog,
    POSSupportTicket,
    POSMarketplaceIntegration,
    POSAuditTrail,
)


class POSOutletConfigSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    outlet_code = serializers.CharField(source='outlet.code', read_only=True)

    class Meta:
        model = POSOutletConfig
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'outlet_code',
            'details',
            'contact',
            'timings',
            'payment',
            'invoice_sequences',
            'billing_display',
            'print_logo',
            'calculations',
            'connected_services',
            'print_settings',
            'customer_settings',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSSubOrderTypeSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSSubOrderType
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'name',
            'type',
            'order_type',
            'status',
            'display_order',
            'description',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSAreaDeliveryChargeSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSAreaDeliveryCharge
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'area_name',
            'postal_code',
            'min_order_amount',
            'delivery_charge',
            'free_delivery_above',
            'estimated_delivery_time_mins',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSDeliveryDistanceSlabSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSDeliveryDistanceSlab
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'min_distance_km',
            'max_distance_km',
            'delivery_fee',
            'min_order_amount',
            'estimated_delivery_time_mins',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSEmailTemplateSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSEmailTemplate
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'template_type',
            'name',
            'subject',
            'body_html',
            'body_text',
            'is_active',
            'cc_emails',
            'bcc_emails',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSBankAccountSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSBankAccount
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'account_name',
            'account_number',
            'bank_name',
            'ifsc_code',
            'branch_name',
            'account_type',
            'upi_id',
            'is_primary',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSCashDrawerMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSCashDrawerMovement
        fields = [
            'id',
            'shift',
            'outlet',
            'movement_type',
            'amount',
            'reason',
            'authorized_by_name',
            'timestamp',
            'created_at',
        ]
        read_only_fields = ['id', 'timestamp', 'created_at']


class POSCashierShiftSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    register_name = serializers.CharField(source='register.name', read_only=True)
    movements_count = serializers.SerializerMethodField()

    class Meta:
        model = POSCashierShift
        fields = [
            'id',
            'register',
            'register_name',
            'outlet',
            'outlet_name',
            'cashier_name',
            'cashier_user',
            'start_time',
            'end_time',
            'opening_float',
            'expected_cash',
            'actual_cash_counted',
            'discrepancy_amount',
            'denominations',
            'status',
            'notes',
            'movements_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_movements_count(self, obj):
        return obj.movements.count()


class POSCashDenominationSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSCashDenomination
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'register',
            'shift',
            'date',
            'session_type',
            'count_2000',
            'count_500',
            'count_200',
            'count_100',
            'count_50',
            'count_20',
            'count_10',
            'count_5',
            'count_2',
            'count_1',
            'coins',
            'total_amount',
            'counted_by_name',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'total_amount', 'created_at', 'updated_at']


class POSExpenseSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    expense_number = serializers.CharField(required=False, default='')

    class Meta:
        model = POSExpense
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'expense_number',
            'category',
            'payee_name',
            'amount',
            'tax_amount',
            'payment_mode',
            'bill_invoice_number',
            'receipt_attachment_url',
            'expense_date',
            'status',
            'approved_by_name',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        if not validated_data.get('expense_number'):
            outlet = validated_data.get('outlet')
            count = POSExpense.objects.filter(outlet=outlet).count() + 1
            validated_data['expense_number'] = f"EXP-{count:04d}"
        return super().create(validated_data)


class POSGstSettingSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSGstSetting
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'gstin',
            'legal_name',
            'trade_name',
            'pan_number',
            'state',
            'state_code',
            'is_composition',
            'filing_frequency',
            'default_hsn_code',
            'turnover_slab',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSKycDocumentSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSKycDocument
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'doc_type',
            'document_name',
            'document_number',
            'valid_from',
            'valid_to',
            'file_url',
            'status',
            'remarks',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSLoanFacilitySerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSLoanFacility
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'facility_name',
            'facility_type',
            'lender_bank',
            'account_number',
            'sanctioned_amount',
            'disbursed_amount',
            'outstanding_amount',
            'interest_rate_pct',
            'emi_amount',
            'daily_deduction_pct',
            'tenure_months',
            'start_date',
            'end_date',
            'status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSOnlineReconciliationSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSOnlineReconciliation
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'aggregator',
            'payout_cycle_start',
            'payout_cycle_end',
            'payout_date',
            'total_orders_count',
            'gross_order_value',
            'aggregator_commission',
            'commission_gst',
            'payment_gateway_fee',
            'logistics_deductions',
            'cancellation_penalty',
            'net_payout_expected',
            'net_payout_received',
            'discrepancy',
            'utr_number',
            'status',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSPaymentGatewayConfigSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSPaymentGatewayConfig
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'provider',
            'terminal_merchant_id',
            'api_key',
            'api_secret',
            'settlement_cycle',
            'mdr_rate_pct',
            'is_active',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'api_secret': {'write_only': True}
        }


class POSServicePaymentRecordSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSServicePaymentRecord
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'invoice_number',
            'plan_name',
            'billing_period',
            'amount',
            'tax_amount',
            'total_amount',
            'paid_on',
            'payment_method',
            'status',
            'receipt_pdf_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSUtilityBillSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSUtilityBill
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'utility_type',
            'provider_name',
            'consumer_number',
            'bill_number',
            'billing_month',
            'amount',
            'due_date',
            'payment_date',
            'payment_status',
            'payment_reference',
            'bill_document_url',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSVirtualWalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = POSVirtualWalletTransaction
        fields = [
            'id',
            'wallet',
            'transaction_type',
            'amount',
            'balance_after',
            'order_id',
            'reference_note',
            'performed_by_name',
            'created_at',
        ]
        read_only_fields = ['id', 'balance_after', 'created_at']


class POSVirtualWalletSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    transactions = POSVirtualWalletTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = POSVirtualWallet
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'customer_name',
            'customer_phone',
            'customer_email',
            'balance',
            'credit_limit',
            'is_active',
            'transactions',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POSBillerGroupSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = POSBillerGroup
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'name',
            'description',
            'can_give_discount',
            'max_discount_percentage',
            'can_void_kot',
            'can_reprint_bill',
            'can_modify_menu',
            'can_settle_due',
            'can_view_reports',
            'can_open_drawer',
            'can_change_table_status',
            'is_active',
            'staff_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_staff_count(self, obj):
        return obj.staff_members.count()


class POSStaffUserSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)
    biller_group_name = serializers.CharField(source='biller_group.name', read_only=True)
    pin = serializers.CharField(write_only=True, required=False, min_length=4, max_length=6)

    class Meta:
        model = POSStaffUser
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'user',
            'name',
            'username',
            'user_code',
            'pin',
            'phone',
            'email',
            'biller_group',
            'biller_group_name',
            'is_active',
            'last_login_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'last_login_at', 'created_at', 'updated_at']

    def create(self, validated_data):
        pin = validated_data.pop('pin', None)
        instance = POSStaffUser(**validated_data)
        if pin:
            instance.set_pin(pin)
        else:
            instance.set_pin('1234')  # default initial PIN
        instance.save()
        return instance

    def update(self, instance, validated_data):
        pin = validated_data.pop('pin', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if pin:
            instance.set_pin(pin)
        instance.save()
        return instance


class PINLoginSerializer(serializers.Serializer):
    outlet_id = serializers.UUIDField(required=True)
    user_code = serializers.CharField(required=True)
    pin = serializers.CharField(required=True)


class SupervisorVerifySerializer(serializers.Serializer):
    outlet_id = serializers.UUIDField(required=True)
    supervisor_pin = serializers.CharField(required=True)
    action = serializers.CharField(required=False, default='SUPERVISOR_OVERRIDE')


class POSManagementLogSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSManagementLog
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'log_type',
            'event_title',
            'actor_name',
            'reference_id',
            'details',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class POSSupportTicketSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSSupportTicket
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'ticket_number',
            'category',
            'subject',
            'description',
            'priority',
            'status',
            'contact_phone',
            'contact_email',
            'response_notes',
            'resolved_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'ticket_number', 'resolved_at', 'created_at', 'updated_at']


class POSMarketplaceIntegrationSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSMarketplaceIntegration
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'platform',
            'name',
            'is_connected',
            'store_id',
            'merchant_id',
            'api_key',
            'auto_accept_orders',
            'default_prep_time_mins',
            'sync_menu_automatically',
            'status',
            'last_sync_at',
            'settings',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'last_sync_at', 'created_at', 'updated_at']
        extra_kwargs = {
            'api_key': {'write_only': True}
        }


class POSAuditTrailSerializer(serializers.ModelSerializer):
    outlet_name = serializers.CharField(source='outlet.name', read_only=True)

    class Meta:
        model = POSAuditTrail
        fields = [
            'id',
            'outlet',
            'outlet_name',
            'actor_name',
            'actor_user',
            'action',
            'entity_type',
            'entity_id',
            'description',
            'ip_address',
            'device_name',
            'metadata',
            'timestamp',
            'created_at',
        ]
        read_only_fields = ['id', 'timestamp', 'created_at']
