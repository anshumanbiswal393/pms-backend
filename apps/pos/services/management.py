import uuid
from decimal import Decimal
from typing import Any, Optional, Dict, List
from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password

from apps.POS.models import (
    Outlet,
    POSRegister,
    POSOrder,
    POSPayment,
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

DEFAULT_CONFIG_TIMINGS = [
    {"day": "Monday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Tuesday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Wednesday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Thursday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Friday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Saturday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
    {"day": "Sunday", "closed": False, "open": "11:00", "close": "23:30", "lunchStart": "12:00", "lunchEnd": "15:30", "dinnerStart": "19:00", "dinnerEnd": "23:00"},
]

DEFAULT_PAYMENT_TYPES = [
    {"id": "pt-cash", "name": "Cash", "enabled": True, "isDefault": True, "surchargePct": "0"},
    {"id": "pt-card", "name": "Credit / Debit Card", "enabled": True, "isDefault": False, "surchargePct": "0"},
    {"id": "pt-upi", "name": "UPI / Dynamic QR", "enabled": True, "isDefault": False, "surchargePct": "0"},
    {"id": "pt-room", "name": "Charge to Room (PMS)", "enabled": True, "isDefault": False, "surchargePct": "0"},
    {"id": "pt-wallet", "name": "Virtual Wallet", "enabled": True, "isDefault": False, "surchargePct": "0"},
]

DEFAULT_INVOICE_SEQUENCES = [
    {"id": "seq-1", "name": "Main Dine-In Sequence", "orderType": "Dine In", "prefix": "INV", "nextNumber": "1001", "padding": "4", "suffix": "", "active": True},
    {"id": "seq-2", "name": "Takeaway Sequence", "orderType": "Takeaway", "prefix": "TA", "nextNumber": "2001", "padding": "4", "suffix": "", "active": True},
    {"id": "seq-3", "name": "Room Service Sequence", "orderType": "Room Service", "prefix": "RS", "nextNumber": "3001", "padding": "4", "suffix": "", "active": True},
    {"id": "seq-4", "name": "Online Delivery Sequence", "orderType": "Delivery", "prefix": "ONL", "nextNumber": "4001", "padding": "4", "suffix": "", "active": True},
]


class OutletConfigService:
    @staticmethod
    def get_or_create_config(outlet: Outlet) -> POSOutletConfig:
        config, created = POSOutletConfig.objects.get_or_create(
            outlet=outlet,
            defaults={
                'details': {
                    'outletName': outlet.name,
                    'alias': outlet.code,
                    'email': outlet.email or '',
                    'gstin': outlet.gstin or '',
                    'fssai': outlet.fssai_license or '',
                    'cuisine': outlet.cuisine or 'Multi-Cuisine & Bar',
                    'phone': outlet.phone or '',
                    'website': '',
                    'seatingCapacity': '80',
                    'address': (outlet.meta_settings or {}).get('address', ''),
                    'area': (outlet.meta_settings or {}).get('area', ''),
                    'city': (outlet.meta_settings or {}).get('city', ''),
                    'state': (outlet.meta_settings or {}).get('state', ''),
                    'zipCode': (outlet.meta_settings or {}).get('zipCode', ''),
                    'country': 'India',
                    'timezone': 'Asia/Kolkata',
                    'additionalInfo': (outlet.meta_settings or {}).get('additionalInfo', ''),
                },
                'contact': {
                    'ownerName': (outlet.meta_settings or {}).get('ownerName', 'Property General Manager'),
                    'ownerMobile': outlet.phone or '',
                    'ownerEmail': outlet.email or '',
                    'managerName': 'Restaurant Manager',
                    'managerMobile': outlet.phone or '',
                    'managerEmail': outlet.email or '',
                    'accountsName': 'Finance / Cashier Head',
                    'accountsMobile': '',
                    'accountsEmail': '',
                    'staff': [],
                },
                'timings': {
                    'sameAllDays': 'Yes',
                    'displayOnBill': 'Yes',
                    'displayOnline': 'Yes',
                    'days': DEFAULT_CONFIG_TIMINGS,
                },
                'payment': {
                    'currency': outlet.currency or 'INR',
                    'symbol': '₹',
                    'decimalPlaces': '2',
                    'symbolPosition': 'Before',
                    'allowSplitPayment': 'Yes',
                    'roundOffBills': 'Yes',
                    'types': DEFAULT_PAYMENT_TYPES,
                },
                'invoice_sequences': DEFAULT_INVOICE_SEQUENCES,
                'billing_display': {
                    'showItemImages': 'Yes',
                    'showCategoryImages': 'Yes',
                    'showItemCode': 'Yes',
                    'showKotNumber': 'Yes',
                    'showTaxBreakup': 'Yes',
                    'showRunningTableAmount': 'Yes',
                    'showOutOfStock': 'Yes',
                    'confirmBeforeSettle': 'Yes',
                    'menuLayout': 'Grid',
                    'itemColumns': '4',
                    'defaultOrderType': 'Dine In',
                    'density': 'Comfortable',
                    'themeAccent': 'Teal',
                },
                'print_logo': {
                    'logoDataUrl': '',
                    'alignment': 'Center',
                    'widthMm': '58',
                    'printOnBill': 'Yes',
                    'printOnKot': 'No',
                    'printOutletName': 'Yes',
                    'headerText': 'Welcome to ' + outlet.name,
                    'footerText': 'Thank you! Visit again.',
                },
                'calculations': {
                    'taxInclusive': 'No',
                    'applyServiceCharge': 'Yes' if outlet.service_charge_percentage > 0 else 'No',
                    'serviceChargePct': str(outlet.service_charge_percentage or '5.00'),
                    'serviceChargeOn': 'All orders',
                    'gstOnServiceCharge': 'Yes',
                    'applyPackingCharge': 'No',
                    'packingCharge': '0.00',
                    'gstOnPacking': 'No',
                    'applyDeliveryCharge': 'Yes',
                    'deliveryCharge': '40.00',
                    'discountBeforeTax': 'Yes',
                    'autoRoundOff': 'Yes',
                    'roundOffMethod': 'Nearest',
                },
                'connected_services': {
                    'pmsRoomService': 'Yes',
                    'inventoryConsumption': 'Yes',
                    'onlineOrdering': 'Yes',
                    'aggregatorSync': 'Yes',
                    'whatsappBill': 'Yes',
                    'smsBill': 'No',
                    'paymentGateway': 'Yes',
                },
                'print_settings': {
                    'billCopies': '1',
                    'kotCopies': '1',
                    'paperSize': '80mm',
                    'autoPrintOnSettle': 'Yes',
                    'autoPrintKot': 'Yes',
                    'printTokenNumber': 'Yes',
                    'printCustomerCopy': 'Yes',
                    'printGstin': 'Yes',
                    'printFssai': 'Yes',
                    'printTableNumber': 'Yes',
                    'printCashierName': 'Yes',
                    'cutAfterPrint': 'Yes',
                },
                'customer_settings': {
                    'mandatoryMobile': 'No',
                    'mandatoryName': 'No',
                    'allowGstOnBill': 'Yes',
                    'enableLoyalty': 'Yes',
                    'allowWalkInWithoutCustomer': 'Yes',
                    'captureAddress': 'No',
                    'captureBirthday': 'No',
                    'searchByMobile': 'Yes',
                    'autoCreateOnBill': 'Yes',
                    'showLastOrders': 'Yes',
                },
            }
        )
        return config

    @staticmethod
    def update_config(outlet: Outlet, data: Dict[str, Any]) -> POSOutletConfig:
        config = OutletConfigService.get_or_create_config(outlet)

        # Update config JSON sections
        if 'details' in data and isinstance(data['details'], dict):
            config.details.update(data['details'])
            # Sync key fields back to Outlet master
            details = data['details']
            if 'outletName' in details and details['outletName']:
                outlet.name = details['outletName']
            if 'email' in details:
                outlet.email = details['email']
            if 'phone' in details:
                outlet.phone = details['phone']
            if 'cuisine' in details:
                outlet.cuisine = details['cuisine']
            if 'gstin' in details:
                outlet.gstin = details['gstin']
            if 'fssai' in details:
                outlet.fssai_license = details['fssai']

        if 'contact' in data and isinstance(data['contact'], dict):
            config.contact.update(data['contact'])
            if not outlet.phone and data['contact'].get('ownerMobile'):
                outlet.phone = data['contact']['ownerMobile']

        if 'timings' in data and isinstance(data['timings'], dict):
            config.timings.update(data['timings'])

        if 'payment' in data and isinstance(data['payment'], dict):
            config.payment.update(data['payment'])
            if data['payment'].get('currency'):
                outlet.currency = data['payment']['currency']

        if 'invoice_sequences' in data or 'invoiceSequences' in data:
            seqs = data.get('invoice_sequences') or data.get('invoiceSequences')
            if isinstance(seqs, list):
                config.invoice_sequences = seqs

        if 'billing_display' in data or 'billingDisplay' in data:
            bd = data.get('billing_display') or data.get('billingDisplay')
            if isinstance(bd, dict):
                config.billing_display.update(bd)

        if 'print_logo' in data or 'printLogo' in data:
            pl = data.get('print_logo') or data.get('printLogo')
            if isinstance(pl, dict):
                config.print_logo.update(pl)

        if 'calculations' in data and isinstance(data['calculations'], dict):
            config.calculations.update(data['calculations'])
            sc = data['calculations'].get('serviceChargePct')
            if sc is not None:
                try:
                    outlet.service_charge_percentage = Decimal(str(sc))
                except Exception:
                    pass

        if 'connected_services' in data or 'connectedServices' in data:
            cs = data.get('connected_services') or data.get('connectedServices')
            if isinstance(cs, dict):
                config.connected_services.update(cs)

        if 'print_settings' in data or 'print' in data:
            ps = data.get('print_settings') or data.get('print')
            if isinstance(ps, dict):
                config.print_settings.update(ps)

        if 'customer_settings' in data or 'customer' in data:
            cust = data.get('customer_settings') or data.get('customer')
            if isinstance(cust, dict):
                config.customer_settings.update(cust)

        config.save()

        # Keep Outlet meta_settings synced with the updated full state
        meta = outlet.meta_settings or {}
        meta.update({
            'details': config.details,
            'contact': config.contact,
            'timings': config.timings,
            'payment': config.payment,
            'calculations': config.calculations,
            'connected_services': config.connected_services,
        })
        outlet.meta_settings = meta
        outlet.save()

        # Audit log entry
        AuditTrailService.log_action(
            outlet=outlet,
            actor_name="Management Admin",
            action="SETTINGS_CHANGE",
            entity_type="POSOutletConfig",
            entity_id=str(config.id),
            description=f"Updated outlet configuration for {outlet.name}",
        )

        return config


class ShiftManagementService:
    @staticmethod
    def get_active_shift(register: POSRegister) -> Optional[POSCashierShift]:
        return POSCashierShift.objects.filter(
            register=register,
            status='OPEN'
        ).order_by('-start_time').first()

    @staticmethod
    @transaction.atomic
    def open_shift(
        register: POSRegister,
        cashier_name: str,
        cashier_user=None,
        opening_float: Decimal = Decimal('0.00'),
        notes: str = ""
    ) -> POSCashierShift:
        # If there's an existing open shift for this register, close it automatically
        existing = POSCashierShift.objects.filter(register=register, status='OPEN').first()
        if existing:
            ShiftManagementService.close_shift(
                shift=existing,
                actual_cash_counted=existing.expected_cash,
                notes="Automatically closed prior open shift upon new session open."
            )

        shift = POSCashierShift.objects.create(
            register=register,
            outlet=register.outlet,
            cashier_name=cashier_name,
            cashier_user=cashier_user,
            start_time=timezone.now(),
            opening_float=opening_float,
            expected_cash=opening_float,
            actual_cash_counted=Decimal('0.00'),
            status='OPEN',
            notes=notes,
        )

        # Record opening float drawer movement
        POSCashDrawerMovement.objects.create(
            shift=shift,
            outlet=register.outlet,
            movement_type='FLOAT',
            amount=opening_float,
            reason='Initial opening cash float assigned to register drawer',
            authorized_by_name=cashier_name,
        )

        POSManagementLog.objects.create(
            outlet=register.outlet,
            log_type='CASH_TOPUP',
            event_title=f"Shift #{shift.id} opened with opening float ₹{opening_float}",
            actor_name=cashier_name,
            reference_id=str(shift.id),
            details={'opening_float': str(opening_float), 'register': register.name},
        )

        AuditTrailService.log_action(
            outlet=register.outlet,
            actor_name=cashier_name,
            actor_user=cashier_user,
            action="LOGIN",
            entity_type="POSCashierShift",
            entity_id=str(shift.id),
            description=f"Shift opened on register {register.name} with float ₹{opening_float}",
        )

        return shift

    @staticmethod
    @transaction.atomic
    def record_cash_movement(
        shift: POSCashierShift,
        movement_type: str,
        amount: Decimal,
        reason: str,
        authorized_by_name: str = ""
    ) -> POSCashDrawerMovement:
        movement = POSCashDrawerMovement.objects.create(
            shift=shift,
            outlet=shift.outlet,
            movement_type=movement_type,
            amount=amount,
            reason=reason,
            authorized_by_name=authorized_by_name or shift.cashier_name,
        )

        # Update expected cash
        if movement_type in ('FLOAT', 'TOP_UP'):
            shift.expected_cash += amount
        elif movement_type in ('WITHDRAWAL', 'PETTY_EXPENSE'):
            shift.expected_cash -= amount
        shift.save(update_fields=['expected_cash', 'updated_at'])

        log_type = 'WITHDRAWAL' if movement_type == 'WITHDRAWAL' else 'CASH_TOPUP'
        POSManagementLog.objects.create(
            outlet=shift.outlet,
            log_type=log_type,
            event_title=f"{movement_type} of ₹{amount}: {reason}",
            actor_name=authorized_by_name or shift.cashier_name,
            reference_id=str(movement.id),
            details={'amount': str(amount), 'movement_type': movement_type, 'shift_id': str(shift.id)},
        )

        return movement

    @staticmethod
    @transaction.atomic
    def close_shift(
        shift: POSCashierShift,
        actual_cash_counted: Decimal,
        denominations: Optional[Dict[str, int]] = None,
        notes: str = ""
    ) -> POSCashierShift:
        # Sum cash payments collected during shift
        cash_sales = POSPayment.objects.filter(
            order__outlet=shift.outlet,
            mode='CASH',
            created_at__gte=shift.start_time,
            created_at__lte=timezone.now(),
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Add top-ups and subtract withdrawals & petty expenses
        movements = shift.movements.all()
        top_ups = sum((m.amount for m in movements if m.movement_type in ('FLOAT', 'TOP_UP')), Decimal('0.00'))
        payouts = sum((m.amount for m in movements if m.movement_type in ('WITHDRAWAL', 'PETTY_EXPENSE')), Decimal('0.00'))

        expected = top_ups + cash_sales - payouts
        shift.expected_cash = expected
        shift.actual_cash_counted = actual_cash_counted
        shift.discrepancy_amount = actual_cash_counted - expected
        shift.end_time = timezone.now()
        shift.status = 'CLOSED'
        if notes:
            shift.notes = f"{shift.notes}\n{notes}".strip()
        if denominations:
            shift.denominations = denominations
        shift.save()

        # Save denomination audit row
        if denominations:
            denom_record = POSCashDenomination(
                outlet=shift.outlet,
                register=shift.register,
                shift=shift,
                date=shift.start_time.date(),
                session_type='SHIFT_CLOSE',
                count_2000=denominations.get('count_2000', 0),
                count_500=denominations.get('count_500', 0),
                count_200=denominations.get('count_200', 0),
                count_100=denominations.get('count_100', 0),
                count_50=denominations.get('count_50', 0),
                count_20=denominations.get('count_20', 0),
                count_10=denominations.get('count_10', 0),
                count_5=denominations.get('count_5', 0),
                count_2=denominations.get('count_2', 0),
                count_1=denominations.get('count_1', 0),
                coins=Decimal(str(denominations.get('coins', 0))),
                counted_by_name=shift.cashier_name,
                notes=f"Reconciled at shift close #{shift.id}",
            )
            denom_record.save()

        AuditTrailService.log_action(
            outlet=shift.outlet,
            actor_name=shift.cashier_name,
            actor_user=shift.cashier_user,
            action="SHIFT_CLOSE",
            entity_type="POSCashierShift",
            entity_id=str(shift.id),
            description=f"Shift #{shift.id} closed. Expected: ₹{expected}, Counted: ₹{actual_cash_counted}, Variance: ₹{shift.discrepancy_amount}",
        )

        return shift


class StaffAuthService:
    @staticmethod
    def verify_pin(outlet_id: str, user_code: str, pin: str) -> Optional[Dict[str, Any]]:
        staff = POSStaffUser.objects.filter(
            outlet_id=outlet_id,
            user_code=user_code,
            is_active=True
        ).select_related('biller_group').first()

        if not staff:
            return None

        if not staff.check_pin(pin):
            return None

        staff.last_login_at = timezone.now()
        staff.save(update_fields=['last_login_at', 'updated_at'])

        group = staff.biller_group
        permissions = {
            'can_give_discount': group.can_give_discount if group else False,
            'max_discount_percentage': float(group.max_discount_percentage) if group else 0.0,
            'can_void_kot': group.can_void_kot if group else False,
            'can_reprint_bill': group.can_reprint_bill if group else True,
            'can_modify_menu': group.can_modify_menu if group else False,
            'can_settle_due': group.can_settle_due if group else False,
            'can_view_reports': group.can_view_reports if group else False,
            'can_open_drawer': group.can_open_drawer if group else False,
            'can_change_table_status': group.can_change_table_status if group else True,
        }

        return {
            'id': str(staff.id),
            'name': staff.name,
            'username': staff.username,
            'user_code': staff.user_code,
            'phone': staff.phone,
            'biller_group': group.name if group else None,
            'permissions': permissions,
            'outlet_id': str(outlet_id),
        }

    @staticmethod
    def verify_supervisor(outlet_id: str, supervisor_pin: str, action: str = "OVERRIDE") -> bool:
        # Search staff with supervisor privileges
        supervisors = POSStaffUser.objects.filter(
            outlet_id=outlet_id,
            is_active=True,
            biller_group__can_void_kot=True,
        )
        for sup in supervisors:
            if sup.check_pin(supervisor_pin):
                AuditTrailService.log_action(
                    outlet=sup.outlet,
                    actor_name=sup.name,
                    action=action,
                    entity_type="SupervisorOverride",
                    entity_id=str(sup.id),
                    description=f"Supervisor override authorized by {sup.name} for {action}",
                )
                return True
        return False


class VirtualWalletService:
    @staticmethod
    @transaction.atomic
    def credit(wallet: POSVirtualWallet, amount: Decimal, reference_note: str = "", performed_by_name: str = "") -> POSVirtualWalletTransaction:
        if amount <= 0:
            raise ValidationError("Top-up amount must be strictly greater than 0.")

        wallet.balance += amount
        wallet.save(update_fields=['balance', 'updated_at'])

        txn = POSVirtualWalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='TOP_UP',
            amount=amount,
            balance_after=wallet.balance,
            reference_note=reference_note or "Wallet Top-up",
            performed_by_name=performed_by_name,
        )
        return txn

    @staticmethod
    @transaction.atomic
    def debit(wallet: POSVirtualWallet, amount: Decimal, order_id: str = "", reference_note: str = "", performed_by_name: str = "") -> POSVirtualWalletTransaction:
        if amount <= 0:
            raise ValidationError("Debit amount must be strictly greater than 0.")

        available = wallet.balance + wallet.credit_limit
        if available < amount:
            raise ValidationError(f"Insufficient wallet balance. Available credit: ₹{available}, required: ₹{amount}")

        wallet.balance -= amount
        wallet.save(update_fields=['balance', 'updated_at'])

        txn = POSVirtualWalletTransaction.objects.create(
            wallet=wallet,
            transaction_type='DEBIT',
            amount=amount,
            balance_after=wallet.balance,
            order_id=order_id,
            reference_note=reference_note or "Order Settlement",
            performed_by_name=performed_by_name,
        )
        return txn


class AuditTrailService:
    @staticmethod
    def log_action(
        outlet: Outlet,
        actor_name: str,
        action: str,
        description: str,
        actor_user=None,
        entity_type: str = "",
        entity_id: str = "",
        ip_address: Optional[str] = None,
        device_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> POSAuditTrail:
        return POSAuditTrail.objects.create(
            outlet=outlet,
            actor_name=actor_name,
            actor_user=actor_user,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            description=description,
            ip_address=ip_address,
            device_name=device_name,
            metadata=metadata or {},
        )


class DataManagementService:
    @staticmethod
    def get_stats(outlet: Outlet) -> Dict[str, Any]:
        return {
            'total_orders': POSOrder.objects.filter(outlet=outlet).count(),
            'total_bills_settled': POSOrder.objects.filter(outlet=outlet, status='SETTLED').count(),
            'total_expenses': POSExpense.objects.filter(outlet=outlet).count(),
            'total_staff': POSStaffUser.objects.filter(outlet=outlet).count(),
            'total_biller_groups': POSBillerGroup.objects.filter(outlet=outlet).count(),
            'total_sub_order_types': POSSubOrderType.objects.filter(outlet=outlet).count(),
            'total_area_charges': POSAreaDeliveryCharge.objects.filter(outlet=outlet).count(),
            'total_audit_logs': POSAuditTrail.objects.filter(outlet=outlet).count(),
            'active_wallets': POSVirtualWallet.objects.filter(outlet=outlet, is_active=True).count(),
            'bank_accounts': POSBankAccount.objects.filter(outlet=outlet).count(),
        }

    @staticmethod
    @transaction.atomic
    def reset_demo_data(outlet: Outlet, confirmed_by: str = "Admin") -> Dict[str, int]:
        """
        Safely clears dummy transaction data (Orders, KOTs, Payments, Drawer Shifts)
        while preserving menu categories, dishes, modifiers, tables, and outlet configuration.
        """
        res_orders = POSOrder.objects.filter(outlet=outlet).delete()
        orders_deleted = res_orders[0] if isinstance(res_orders, (tuple, list)) else (res_orders or 0)

        res_expenses = POSExpense.objects.filter(outlet=outlet).delete()
        expenses_deleted = res_expenses[0] if isinstance(res_expenses, (tuple, list)) else (res_expenses or 0)

        res_shifts = POSCashierShift.objects.filter(outlet=outlet).delete()
        shifts_deleted = res_shifts[0] if isinstance(res_shifts, (tuple, list)) else (res_shifts or 0)

        AuditTrailService.log_action(
            outlet=outlet,
            actor_name=confirmed_by,
            action="SETTINGS_CHANGE",
            entity_type="DataReset",
            description=f"Demo transactions reset for outlet {outlet.name}",
        )

        return {
            'orders_cleared': orders_deleted,
            'expenses_cleared': expenses_deleted,
            'shifts_cleared': shifts_deleted,
        }
