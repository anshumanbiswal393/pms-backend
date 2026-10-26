import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from apps.core.common.models import BaseModel


class POSOutletConfig(BaseModel):
    """
    Comprehensive persistent settings and configuration for a POS Outlet.
    Stores structured sections matching the Retrod POS Management specification:
    Details, Contact, Timings, Payment, Invoice Sequences, Display,
    Print Logo, Calculations, Connected Services, Print, and Customer settings.
    """
    outlet = models.OneToOneField(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='pos_config'
    )
    details = models.JSONField(default=dict, blank=True)
    contact = models.JSONField(default=dict, blank=True)
    timings = models.JSONField(default=dict, blank=True)
    payment = models.JSONField(default=dict, blank=True)
    invoice_sequences = models.JSONField(default=list, blank=True)
    billing_display = models.JSONField(default=dict, blank=True)
    print_logo = models.JSONField(default=dict, blank=True)
    calculations = models.JSONField(default=dict, blank=True)
    connected_services = models.JSONField(default=dict, blank=True)
    print_settings = models.JSONField(default=dict, blank=True)
    customer_settings = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-created_at']
        verbose_name = 'POS Outlet Configuration'
        verbose_name_plural = 'POS Outlet Configurations'

    def __str__(self):
        return f"Config for {self.outlet.name} ({self.outlet.code})"


class POSSubOrderType(BaseModel):
    """
    Sub-Order Type masters (e.g. Delivery, Pick Up, Dine In, Bar Counter, Dining, Room Service).
    """
    TYPE_CHOICES = (
        ('Default Order Type', 'Default Order Type'),
        ('Area', 'Area'),
        ('Third Party Integration', 'Third Party Integration'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='sub_order_types'
    )
    name = models.CharField(max_length=80)
    type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        default='Default Order Type'
    )
    order_type = models.CharField(max_length=40, default='Dine In')
    status = models.CharField(max_length=16, default='Active')  # Active / Inactive
    display_order = models.IntegerField(default=0)
    description = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['display_order', 'name']
        unique_together = ('outlet', 'name')
        verbose_name = 'POS Sub Order Type'
        verbose_name_plural = 'POS Sub Order Types'

    def __str__(self):
        return f"{self.name} ({self.type}) - {self.outlet.name}"


class POSAreaDeliveryCharge(BaseModel):
    """
    Configured delivery charges per geographical neighborhood/area.
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='area_delivery_charges'
    )
    area_name = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=16, blank=True, null=True)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    free_delivery_above = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    estimated_delivery_time_mins = models.IntegerField(default=35)
    status = models.CharField(max_length=16, default='Active')

    class Meta:
        app_label = 'pos'
        ordering = ['area_name']
        unique_together = ('outlet', 'area_name')
        verbose_name = 'POS Area Delivery Charge'
        verbose_name_plural = 'POS Area Delivery Charges'

    def __str__(self):
        return f"{self.area_name}: ₹{self.delivery_charge} (Min: ₹{self.min_order_amount})"


class POSDeliveryDistanceSlab(BaseModel):
    """
    Distance-based tiered delivery fee matrix (e.g. 0-3km: ₹30, 3-7km: ₹60).
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='distance_slabs'
    )
    min_distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    max_distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('30.00'))
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('150.00'))
    estimated_delivery_time_mins = models.IntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'pos'
        ordering = ['min_distance_km']
        verbose_name = 'POS Delivery Distance Slab'
        verbose_name_plural = 'POS Delivery Distance Slabs'

    def __str__(self):
        return f"{self.min_distance_km}-{self.max_distance_km}km: ₹{self.delivery_fee}"


class POSEmailTemplate(BaseModel):
    """
    Configurable email templates for reports, bill copies, and notifications.
    """
    TEMPLATE_TYPES = (
        ('DAY_END', 'Day End Z-Report Summary'),
        ('BILL', 'Guest Bill / Tax Invoice Copy'),
        ('KOT', 'Kitchen Order Alert'),
        ('PO', 'Purchase Order to Vendor'),
        ('RESERVATION', 'Table Reservation Confirmation'),
        ('SETTLEMENT', 'Shift Settlement Audit'),
        ('CUSTOM', 'Custom Notification'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='email_templates'
    )
    template_type = models.CharField(max_length=32, choices=TEMPLATE_TYPES, default='DAY_END')
    name = models.CharField(max_length=120)
    subject = models.CharField(max_length=255)
    body_html = models.TextField()
    body_text = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    cc_emails = models.CharField(max_length=255, blank=True, default='')
    bcc_emails = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['name']
        unique_together = ('outlet', 'template_type', 'name')
        verbose_name = 'POS Email Template'
        verbose_name_plural = 'POS Email Templates'

    def __str__(self):
        return f"{self.name} ({self.template_type})"


class POSBankAccount(BaseModel):
    """
    Outlet settlement bank accounts and UPI VPA configurations.
    """
    ACCOUNT_TYPE_CHOICES = (
        ('CURRENT', 'Current Account'),
        ('SAVINGS', 'Savings Account'),
        ('OVERDRAFT', 'Cash Credit / Overdraft'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='bank_accounts'
    )
    account_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=40)
    bank_name = models.CharField(max_length=120)
    ifsc_code = models.CharField(max_length=20)
    branch_name = models.CharField(max_length=120, blank=True, default='')
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='CURRENT')
    upi_id = models.CharField(max_length=100, blank=True, default='')
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-is_primary', 'bank_name']
        verbose_name = 'POS Bank Account'
        verbose_name_plural = 'POS Bank Accounts'

    def __str__(self):
        return f"{self.bank_name} - {self.account_number[-4:]} ({self.account_name})"


class POSCashierShift(BaseModel):
    """
    Cashier register shift lifecycle (Epic 8). Tracks opening float,
    sales collections, mid-shift top-ups, payouts, and final cash reconciliation.
    """
    STATUS_CHOICES = (
        ('OPEN', 'Open / Active'),
        ('CLOSED', 'Closed'),
        ('AUDITED', 'Audited & Verified'),
    )

    register = models.ForeignKey(
        'pos.POSRegister',
        on_delete=models.CASCADE,
        related_name='shifts'
    )
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='shifts'
    )
    cashier_name = models.CharField(max_length=120)
    cashier_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_cashier_shifts'
    )
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    opening_float = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    actual_cash_counted = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discrepancy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    denominations = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='OPEN')
    notes = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-start_time']
        verbose_name = 'POS Cashier Shift'
        verbose_name_plural = 'POS Cashier Shifts'

    def __str__(self):
        return f"Shift #{self.id} - {self.cashier_name} ({self.status})"


class POSCashDrawerMovement(BaseModel):
    """
    Petty cash movements, mid-shift drawer additions, and cash drops to safe.
    """
    MOVEMENT_TYPES = (
        ('FLOAT', 'Opening Float'),
        ('TOP_UP', 'Cash Drawer Top-Up / Float Addition'),
        ('WITHDRAWAL', 'Cash Drop / Withdrawal to Safe'),
        ('PETTY_EXPENSE', 'Petty Cash Expense Payout'),
    )

    shift = models.ForeignKey(
        POSCashierShift,
        on_delete=models.CASCADE,
        related_name='movements'
    )
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='drawer_movements'
    )
    movement_type = models.CharField(max_length=24, choices=MOVEMENT_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=255)
    authorized_by_name = models.CharField(max_length=120, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-timestamp']
        verbose_name = 'POS Cash Drawer Movement'
        verbose_name_plural = 'POS Cash Drawer Movements'

    def __str__(self):
        return f"{self.movement_type}: ₹{self.amount} ({self.reason})"


class POSCashDenomination(BaseModel):
    """
    Detailed physical currency denomination count record.
    Supports shift-end, day-end Z-report audits, and spot drawer counts.
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='denominations'
    )
    register = models.ForeignKey(
        'pos.POSRegister',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='denominations'
    )
    shift = models.ForeignKey(
        POSCashierShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='denominations_entries'
    )
    date = models.DateField(default=timezone.localdate)
    session_type = models.CharField(max_length=32, default='DAY_END')
    count_2000 = models.IntegerField(default=0)
    count_500 = models.IntegerField(default=0)
    count_200 = models.IntegerField(default=0)
    count_100 = models.IntegerField(default=0)
    count_50 = models.IntegerField(default=0)
    count_20 = models.IntegerField(default=0)
    count_10 = models.IntegerField(default=0)
    count_5 = models.IntegerField(default=0)
    count_2 = models.IntegerField(default=0)
    count_1 = models.IntegerField(default=0)
    coins = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    counted_by_name = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-date', '-created_at']
        verbose_name = 'POS Cash Denomination'
        verbose_name_plural = 'POS Cash Denominations'

    def calculate_total(self):
        total = (
            (self.count_2000 * 2000) +
            (self.count_500 * 500) +
            (self.count_200 * 200) +
            (self.count_100 * 100) +
            (self.count_50 * 50) +
            (self.count_20 * 20) +
            (self.count_10 * 10) +
            (self.count_5 * 5) +
            (self.count_2 * 2) +
            (self.count_1 * 1) +
            Decimal(str(self.coins or 0))
        )
        self.total_amount = Decimal(str(total))
        return self.total_amount

    def save(self, *args, **kwargs):
        self.calculate_total()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Denominations {self.date}: ₹{self.total_amount}"


class POSExpense(BaseModel):
    """
    Petty cash & restaurant operational expense records.
    """
    CATEGORY_CHOICES = (
        ('RAW_MATERIALS', 'Raw Materials & Kitchen Groceries'),
        ('VEGETABLES_GROCERY', 'Fresh Produce & Dairy'),
        ('GAS_FUEL', 'Commercial Gas & Fuel'),
        ('STAFF_FOOD', 'Staff Meals & Welfare'),
        ('MAINTENANCE_REPAIRS', 'Repairs & Maintenance'),
        ('PRINTING_STATIONERY', 'Thermal Rolls & Stationery'),
        ('OFFICE_EXPENSE', 'Office & Administration'),
        ('MARKETING', 'Local Promotion & Marketing'),
        ('MISCELLANEOUS', 'Miscellaneous Expenses'),
    )

    STATUS_CHOICES = (
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('PAID', 'Paid'),
        ('REJECTED', 'Rejected'),
    )

    PAYMENT_MODE_CHOICES = (
        ('CASH', 'Cash (Petty Cash Float)'),
        ('UPI', 'UPI Payment'),
        ('CARD', 'Debit / Credit Card'),
        ('NET_BANKING', 'Bank Transfer / NEFT'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='expenses'
    )
    expense_number = models.CharField(max_length=32, db_index=True)
    category = models.CharField(max_length=64, choices=CATEGORY_CHOICES, default='MISCELLANEOUS')
    payee_name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_mode = models.CharField(max_length=32, choices=PAYMENT_MODE_CHOICES, default='CASH')
    bill_invoice_number = models.CharField(max_length=64, blank=True, default='')
    receipt_attachment_url = models.CharField(max_length=255, blank=True, default='')
    expense_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='APPROVED')
    approved_by_name = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-expense_date', '-created_at']
        unique_together = ('outlet', 'expense_number')
        verbose_name = 'POS Expense'
        verbose_name_plural = 'POS Expenses'

    def __str__(self):
        return f"{self.expense_number} - {self.payee_name}: ₹{self.amount} ({self.status})"


class POSGstSetting(BaseModel):
    """
    GST compliance profile for the restaurant outlet.
    """
    outlet = models.OneToOneField(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='gst_setting'
    )
    gstin = models.CharField(max_length=20)
    legal_name = models.CharField(max_length=160)
    trade_name = models.CharField(max_length=160)
    pan_number = models.CharField(max_length=15, blank=True, default='')
    state = models.CharField(max_length=64, default='Maharashtra')
    state_code = models.CharField(max_length=8, default='27')
    is_composition = models.BooleanField(default=False)
    filing_frequency = models.CharField(max_length=24, default='MONTHLY')
    default_hsn_code = models.CharField(max_length=16, default='996331')
    turnover_slab = models.CharField(max_length=64, blank=True, default='Up to ₹1.5 Cr')

    class Meta:
        app_label = 'pos'
        verbose_name = 'POS GST Setting'
        verbose_name_plural = 'POS GST Settings'

    def __str__(self):
        return f"GSTIN {self.gstin} - {self.trade_name}"


class POSKycDocument(BaseModel):
    """
    Regulatory and statutory KYC licenses (FSSAI, Liquor, Fire NOC, PAN).
    """
    DOC_TYPES = (
        ('FSSAI', 'FSSAI Food License'),
        ('GST_CERTIFICATE', 'GST Registration Certificate'),
        ('PAN', 'Company / Proprietor PAN'),
        ('AADHAAR', 'Authorized Signatory Aadhaar'),
        ('LIQUOR_LICENSE', 'Excise / Liquor Serving License'),
        ('TRADE_LICENSE', 'Municipal Trade License'),
        ('FIRE_NOC', 'Fire Department NOC'),
        ('OTHER', 'Other Statutory License'),
    )

    STATUS_CHOICES = (
        ('VERIFIED', 'Verified & Active'),
        ('PENDING', 'Under Review'),
        ('REJECTED', 'Rejected'),
        ('EXPIRED', 'Expired'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='kyc_documents'
    )
    doc_type = models.CharField(max_length=32, choices=DOC_TYPES)
    document_name = models.CharField(max_length=120)
    document_number = models.CharField(max_length=64)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    file_url = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='VERIFIED')
    remarks = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['doc_type', '-valid_to']
        verbose_name = 'POS KYC Document'
        verbose_name_plural = 'POS KYC Documents'

    def __str__(self):
        return f"{self.document_name} ({self.document_number}) - {self.status}"


class POSLoanFacility(BaseModel):
    """
    Working capital facilities, term loans, and POS daily swipe advances.
    """
    FACILITY_TYPES = (
        ('Working Capital', 'Working Capital'),
        ('Kitchen & Equipment Finance', 'Kitchen & Equipment Finance'),
        ('POS Daily Swipe Advance', 'POS Daily Swipe Advance'),
        ('Term Loan', 'Term Loan'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='loan_facilities'
    )
    facility_name = models.CharField(max_length=120)
    facility_type = models.CharField(max_length=64, choices=FACILITY_TYPES, default='Working Capital')
    lender_bank = models.CharField(max_length=120)
    account_number = models.CharField(max_length=40, blank=True, default='')
    sanctioned_amount = models.DecimalField(max_digits=12, decimal_places=2)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    outstanding_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('12.00'))
    emi_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    daily_deduction_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tenure_months = models.IntegerField(default=12)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=24, default='ACTIVE')

    class Meta:
        app_label = 'pos'
        ordering = ['-start_date']
        verbose_name = 'POS Loan Facility'
        verbose_name_plural = 'POS Loan Facilities'

    def __str__(self):
        return f"{self.facility_name} ({self.lender_bank}): Outstanding ₹{self.outstanding_amount}"


class POSOnlineReconciliation(BaseModel):
    """
    Aggregator (Zomato/Swiggy) weekly payout reconciliation records.
    """
    AGGREGATOR_CHOICES = (
        ('ZOMATO', 'Zomato'),
        ('SWIGGY', 'Swiggy'),
        ('MAGICPIN', 'MagicPin'),
        ('DIRECT_ONLINE', 'Direct Store Online Ordering'),
        ('OTHER', 'Other Aggregator'),
    )

    STATUS_CHOICES = (
        ('RECONCILED', 'Reconciled & Settled'),
        ('PENDING', 'Pending Payout'),
        ('DISPUTED', 'Discrepancy / Disputed'),
        ('SETTLED', 'Transferred to Bank'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='online_reconciliations'
    )
    aggregator = models.CharField(max_length=32, choices=AGGREGATOR_CHOICES)
    payout_cycle_start = models.DateField()
    payout_cycle_end = models.DateField()
    payout_date = models.DateField(null=True, blank=True)
    total_orders_count = models.IntegerField(default=0)
    gross_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    aggregator_commission = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission_gst = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    logistics_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    cancellation_penalty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_payout_expected = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    net_payout_received = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discrepancy = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    utr_number = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='RECONCILED')
    notes = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-payout_cycle_end']
        verbose_name = 'POS Online Reconciliation'
        verbose_name_plural = 'POS Online Reconciliations'

    def __str__(self):
        return f"{self.aggregator} ({self.payout_cycle_start} to {self.payout_cycle_end}): Net ₹{self.net_payout_received}"


class POSPaymentGatewayConfig(BaseModel):
    """
    Card terminal EDC machines, payment gateways and QR providers.
    """
    PROVIDER_CHOICES = (
        ('RAZORPAY', 'Razorpay POS / QR'),
        ('PAYTM', 'Paytm EDC / Soundbox'),
        ('PINELABS', 'PineLabs Plutus EDC Terminal'),
        ('PHONEPE', 'PhonePe Business Dynamic QR'),
        ('CASHFREE', 'Cashfree Payments'),
        ('UPI_QR', 'Static UPI QR Standee'),
        ('EDC_CARD_MACHINE', 'Standalone Bank EDC Machine'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='payment_configs'
    )
    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES)
    terminal_merchant_id = models.CharField(max_length=64)
    api_key = models.CharField(max_length=120, blank=True, default='')
    api_secret = models.CharField(max_length=120, blank=True, default='')
    settlement_cycle = models.CharField(max_length=16, default='T+1')
    mdr_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.75'))
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['provider']
        unique_together = ('outlet', 'provider', 'terminal_merchant_id')
        verbose_name = 'POS Payment Gateway Config'
        verbose_name_plural = 'POS Payment Gateway Configs'

    def __str__(self):
        return f"{self.provider} (MID: {self.terminal_merchant_id})"


class POSServicePaymentRecord(BaseModel):
    """
    SaaS service subscription invoices & payments for Retrod POS modules.
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='service_payments'
    )
    invoice_number = models.CharField(max_length=40, db_index=True)
    plan_name = models.CharField(max_length=120, default='Retrod POS Enterprise')
    billing_period = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_on = models.DateTimeField(default=timezone.now)
    payment_method = models.CharField(max_length=32, default='UPI / Auto-Debit')
    status = models.CharField(max_length=24, default='SUCCESS')
    receipt_pdf_url = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-paid_on']
        verbose_name = 'POS Service Payment Record'
        verbose_name_plural = 'POS Service Payment Records'

    def __str__(self):
        return f"{self.invoice_number} - {self.plan_name}: ₹{self.total_amount}"


class POSUtilityBill(BaseModel):
    """
    Recurring restaurant utility expenses (Electricity, Water, Gas, Commercial WiFi).
    """
    UTILITY_TYPES = (
        ('Electricity', 'Electricity (MSEDCL / State Board)'),
        ('Water', 'Commercial Water Supply / Tankers'),
        ('Gas Pipe / Cylinders', 'Commercial LPG Cylinders / Pipeline'),
        ('Broadband Internet', 'High-Speed POS Internet / WiFi'),
        ('Telephone', 'Landline / EPABX'),
        ('Municipal Taxes', 'Municipal Property Taxes'),
        ('Rent', 'Premises Lease / Rent'),
    )

    STATUS_CHOICES = (
        ('DUE', 'Payment Due'),
        ('PAID', 'Paid'),
        ('OVERDUE', 'Overdue'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='utility_bills'
    )
    utility_type = models.CharField(max_length=64, choices=UTILITY_TYPES)
    provider_name = models.CharField(max_length=120)
    consumer_number = models.CharField(max_length=64)
    bill_number = models.CharField(max_length=64, blank=True, default='')
    billing_month = models.CharField(max_length=32)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    payment_date = models.DateField(null=True, blank=True)
    payment_status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='DUE')
    payment_reference = models.CharField(max_length=64, blank=True, default='')
    bill_document_url = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-due_date']
        verbose_name = 'POS Utility Bill'
        verbose_name_plural = 'POS Utility Bills'

    def __str__(self):
        return f"{self.utility_type} ({self.provider_name}) - {self.billing_month}: ₹{self.amount}"


class POSVirtualWallet(BaseModel):
    """
    Prepaid guest credit wallets, VIP deposits, and corporate tabs.
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='wallets'
    )
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=32, db_index=True)
    customer_email = models.CharField(max_length=120, blank=True, default='')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'pos'
        ordering = ['customer_name']
        unique_together = ('outlet', 'customer_phone')
        verbose_name = 'POS Virtual Wallet'
        verbose_name_plural = 'POS Virtual Wallets'

    def __str__(self):
        return f"{self.customer_name} ({self.customer_phone}): Balance ₹{self.balance}"


class POSVirtualWalletTransaction(BaseModel):
    """
    Audit ledger of all credits, top-ups, and order debits against virtual wallet.
    """
    TRANSACTION_TYPES = (
        ('TOP_UP', 'Wallet Top-Up / Deposit'),
        ('DEBIT', 'Order Settlement Debit'),
        ('REFUND', 'Order Refund Credit'),
        ('ADJUSTMENT', 'Manual Balance Adjustment'),
    )

    wallet = models.ForeignKey(
        POSVirtualWallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=24, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    order_id = models.CharField(max_length=64, blank=True, default='')
    reference_note = models.CharField(max_length=255, blank=True, default='')
    performed_by_name = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        app_label = 'pos'
        ordering = ['-created_at']
        verbose_name = 'POS Wallet Transaction'
        verbose_name_plural = 'POS Wallet Transactions'

    def __str__(self):
        return f"{self.transaction_type}: ₹{self.amount} (Balance: ₹{self.balance_after})"


class POSBillerGroup(BaseModel):
    """
    Staff role groups and granular functional permissions for billing terminals (Epic 7).
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='biller_groups'
    )
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True, default='')
    can_give_discount = models.BooleanField(default=False)
    max_discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    can_void_kot = models.BooleanField(default=False)
    can_reprint_bill = models.BooleanField(default=True)
    can_modify_menu = models.BooleanField(default=False)
    can_settle_due = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)
    can_open_drawer = models.BooleanField(default=False)
    can_change_table_status = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = 'pos'
        ordering = ['name']
        unique_together = ('outlet', 'name')
        verbose_name = 'POS Biller Group'
        verbose_name_plural = 'POS Biller Groups'

    def __str__(self):
        return f"{self.name} - {self.outlet.name}"


class POSStaffUser(BaseModel):
    """
    Biller app staff user with 4-digit PIN for rapid terminal login.
    """
    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='staff_users'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_staff_profiles'
    )
    name = models.CharField(max_length=120)
    username = models.CharField(max_length=64)
    user_code = models.CharField(max_length=16, db_index=True)
    passcode_pin_hash = models.CharField(max_length=128)
    phone = models.CharField(max_length=32, blank=True, default='')
    email = models.CharField(max_length=120, blank=True, default='')
    biller_group = models.ForeignKey(
        POSBillerGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_members'
    )
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['name']
        unique_together = ('outlet', 'user_code')
        verbose_name = 'POS Staff User'
        verbose_name_plural = 'POS Staff Users'

    def set_pin(self, raw_pin: str):
        self.passcode_pin_hash = make_password(str(raw_pin).strip())

    def check_pin(self, raw_pin: str) -> bool:
        return check_password(str(raw_pin).strip(), self.passcode_pin_hash)

    def __str__(self):
        return f"{self.name} ({self.user_code}) - {self.biller_group.name if self.biller_group else 'No Group'}"


class POSManagementLog(BaseModel):
    """
    Consolidated operational event logs across all POS subsystems.
    """
    LOG_TYPE_CHOICES = (
        ('AUTO_ACCEPT', 'Online Orders Auto-Accept'),
        ('CASH_TOPUP', 'Cash Top-Up / Float Added'),
        ('CLOSING_HOURS', 'Closing / Opening Hours Override'),
        ('EXPENSE', 'Expense Recorded / Approved'),
        ('MENU_TRIGGER', 'Menu Item Toggle / Price Change'),
        ('NOTIFICATIONS', 'Customer Notification Dispatched'),
        ('ONLINE_ITEMS', 'Aggregator Item Availability Changed'),
        ('ONLINE_STORE', 'Aggregator Store On/Off Toggle'),
        ('SUPPORT', 'Support Query / Ticket Action'),
        ('WITHDRAWAL', 'Cash Drop / Withdrawal'),
        ('AUDIT', 'Security & Audit Action'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='management_logs'
    )
    log_type = models.CharField(max_length=32, choices=LOG_TYPE_CHOICES, db_index=True)
    event_title = models.CharField(max_length=255)
    actor_name = models.CharField(max_length=120, blank=True, default='System')
    reference_id = models.CharField(max_length=64, blank=True, default='')
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-created_at']
        verbose_name = 'POS Management Log'
        verbose_name_plural = 'POS Management Logs'

    def __str__(self):
        return f"[{self.log_type}] {self.event_title} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class POSSupportTicket(BaseModel):
    """
    Direct technical and operational support tickets.
    """
    CATEGORY_CHOICES = (
        ('BILLING_HARDWARE', 'Billing Terminal / Thermal Printer Hardware'),
        ('KDS_SYNC', 'Kitchen Display Sync / WebSocket Issues'),
        ('MENU_UPDATE', 'Menu Catalog & Pricing Help'),
        ('AGGREGATOR_ISSUE', 'Swiggy / Zomato Webhook Integration'),
        ('PAYMENT_GATEWAY', 'EDC Machine / UPI Gateway Settlement'),
        ('OTHER', 'General Support & Feedback'),
    )

    PRIORITY_CHOICES = (
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical / Store Halted'),
    )

    STATUS_CHOICES = (
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='support_tickets'
    )
    ticket_number = models.CharField(max_length=32, db_index=True)
    category = models.CharField(max_length=64, choices=CATEGORY_CHOICES, default='BILLING_HARDWARE')
    subject = models.CharField(max_length=255)
    description = models.TextField()
    priority = models.CharField(max_length=24, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='OPEN')
    contact_phone = models.CharField(max_length=32, blank=True, default='')
    contact_email = models.CharField(max_length=120, blank=True, default='')
    response_notes = models.TextField(blank=True, default='')
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-created_at']
        unique_together = ('outlet', 'ticket_number')
        verbose_name = 'POS Support Ticket'
        verbose_name_plural = 'POS Support Tickets'

    def __str__(self):
        return f"{self.ticket_number} - {self.subject} ({self.status})"


class POSMarketplaceIntegration(BaseModel):
    """
    Marketplace apps and food delivery aggregator connectors (Swiggy, Zomato, Magicpin, Retrod Capital).
    """
    PLATFORM_CHOICES = (
        ('ZOMATO', 'Zomato Online Delivery'),
        ('SWIGGY', 'Swiggy Online Delivery'),
        ('MAGICPIN', 'Magicpin Dine-In & Offers'),
        ('DOTPE', 'DotPe QR & Direct Delivery'),
        ('RETROD_CAPITAL', 'Retrod Restaurant Capital & Finance'),
        ('TALLY', 'Tally Prime Financial Sync'),
        ('PETPOOJA_SYNC', 'Petpooja Migration Bridge'),
        ('WHATSAPP_ORDERING', 'WhatsApp Direct Storefront'),
    )

    STATUS_CHOICES = (
        ('CONNECTED', 'Connected & Active'),
        ('DISCONNECTED', 'Disconnected'),
        ('SYNC_ERROR', 'Sync Error / Auth Expired'),
        ('PENDING_AUTH', 'Pending Authorization'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='marketplace_integrations'
    )
    platform = models.CharField(max_length=32, choices=PLATFORM_CHOICES)
    name = models.CharField(max_length=120)
    is_connected = models.BooleanField(default=False)
    store_id = models.CharField(max_length=64, blank=True, default='')
    merchant_id = models.CharField(max_length=64, blank=True, default='')
    api_key = models.CharField(max_length=255, blank=True, default='')
    auto_accept_orders = models.BooleanField(default=False)
    default_prep_time_mins = models.IntegerField(default=20)
    sync_menu_automatically = models.BooleanField(default=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='DISCONNECTED')
    last_sync_at = models.DateTimeField(null=True, blank=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'pos'
        ordering = ['platform']
        unique_together = ('outlet', 'platform')
        verbose_name = 'POS Marketplace Integration'
        verbose_name_plural = 'POS Marketplace Integrations'

    def __str__(self):
        return f"{self.name} ({self.platform}) - {self.status}"


class POSAuditTrail(BaseModel):
    """
    Immutable audit trail capturing all supervisor overrides, KOT voids, discounts,
    bill reprints, and cash drawer openings.
    """
    ACTION_CHOICES = (
        ('VOID_KOT', 'Void Kitchen Order Ticket'),
        ('APPLY_DISCOUNT', 'Apply Special Discount'),
        ('BILL_REPRINT', 'Reprint Settled Bill'),
        ('PRICE_OVERRIDE', 'Manual Price Override'),
        ('DRAWER_OPEN', 'Emergency Cash Drawer Open'),
        ('TABLE_TRANSFER', 'Transfer / Merge Tables'),
        ('SETTINGS_CHANGE', 'Management Configuration Change'),
        ('LOGIN', 'User Terminal Sign-In'),
        ('SHIFT_CLOSE', 'Shift Reconciled & Closed'),
        ('EXPENSE_CREATE', 'Expense Recorded'),
    )

    outlet = models.ForeignKey(
        'pos.Outlet',
        on_delete=models.CASCADE,
        related_name='audit_trails'
    )
    actor_name = models.CharField(max_length=120)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pos_audit_actions'
    )
    action = models.CharField(max_length=64, choices=ACTION_CHOICES, db_index=True)
    entity_type = models.CharField(max_length=64, blank=True, default='')
    entity_id = models.CharField(max_length=64, blank=True, default='')
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_name = models.CharField(max_length=120, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'pos'
        ordering = ['-timestamp']
        verbose_name = 'POS Audit Trail'
        verbose_name_plural = 'POS Audit Trails'

    def __str__(self):
        return f"[{self.action}] {self.actor_name}: {self.description[:60]}"
