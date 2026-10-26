import uuid
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.POS.models import (
    Outlet,
    POSRegister,
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
    POSBillerGroup,
    POSStaffUser,
    POSManagementLog,
    POSSupportTicket,
    POSMarketplaceIntegration,
    POSAuditTrail,
)
from apps.POS.tests.helpers import make_tenant_property_outlet


class POSManagementModuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant, cls.prop, cls.outlet = make_tenant_property_outlet()
        cls.register = POSRegister.objects.create(
            outlet=cls.outlet,
            name="Main Billing Terminal 1",
            register_code=f"REG-{cls.tenant.subdomain[:6]}",
            is_active=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.defaults['HTTP_X_TENANT_SUBDOMAIN'] = self.tenant.subdomain

    def test_outlet_config_get_and_update(self):
        # 1. GET outlet config
        res = self.client.get(f"/api/pos/management/outlet-config/?outlet_id={self.outlet.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIn("details", data)
        self.assertIn("calculations", data)
        self.assertIn("timings", data)
        self.assertIn("payment", data)

        # 2. PUT / Update outlet config
        update_payload = {
            "details": {
                "outletName": "Highway Inn Rooftop & Bar",
                "email": "rooftop@highwayinn.in",
                "phone": "+91 9988776655",
                "cuisine": "Continental & Italian",
                "gstin": "27AABCU9603R1ZX",
            },
            "calculations": {
                "serviceChargePct": "7.50",
                "applyServiceCharge": "Yes",
            },
            "connectedServices": {
                "onlineOrdering": "Yes",
                "whatsappBill": "Yes",
            }
        }
        update_res = self.client.put(
            f"/api/pos/management/outlet-config/?outlet_id={self.outlet.id}",
            update_payload,
            format="json"
        )
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        updated_data = update_res.json()
        self.assertEqual(updated_data["details"]["outletName"], "Highway Inn Rooftop & Bar")
        self.assertEqual(updated_data["calculations"]["serviceChargePct"], "7.50")

        # Verify synced back to Outlet master
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.name, "Highway Inn Rooftop & Bar")
        self.assertEqual(self.outlet.email, "rooftop@highwayinn.in")
        self.assertEqual(self.outlet.service_charge_percentage, Decimal("7.50"))

        # Verify audit trail created
        self.assertTrue(
            POSAuditTrail.objects.filter(outlet=self.outlet, action="SETTINGS_CHANGE").exists()
        )

    def test_sub_order_types_crud(self):
        # Create
        res = self.client.post(
            f"/api/pos/management/sub-order-types/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "name": "Bar Counter",
                "type": "Area",
                "order_type": "Dine In",
                "status": "Active",
            },
            format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        item_id = res.json()["id"]

        # List
        list_res = self.client.get(f"/api/pos/management/sub-order-types/?outlet_id={self.outlet.id}")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        results = list_res.json()
        items = results.get("results", []) if isinstance(results, dict) else results
        names = [item["name"] for item in items]
        self.assertIn("Bar Counter", names)

        # Update
        patch_res = self.client.patch(
            f"/api/pos/management/sub-order-types/{item_id}/",
            {"name": "Bar Counter & Lounge"},
            format="json"
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.json()["name"], "Bar Counter & Lounge")

    def test_area_delivery_and_distance_slabs(self):
        # Area delivery charge
        area_res = self.client.post(
            f"/api/pos/management/area-delivery-charges/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "area_name": "Koregaon Park",
                "min_order_amount": "250.00",
                "delivery_charge": "40.00",
                "free_delivery_above": "500.00",
                "estimated_delivery_time_mins": 30,
            },
            format="json"
        )
        self.assertEqual(area_res.status_code, status.HTTP_201_CREATED)

        # Distance slab
        slab_res = self.client.post(
            f"/api/pos/management/delivery-distance-slabs/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "min_distance_km": "0.00",
                "max_distance_km": "4.50",
                "delivery_fee": "35.00",
                "min_order_amount": "200.00",
            },
            format="json"
        )
        self.assertEqual(slab_res.status_code, status.HTTP_201_CREATED)

    def test_bank_accounts_and_primary_switch(self):
        # Create bank account 1
        res1 = self.client.post(
            f"/api/pos/management/accounting/bank-details/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "account_name": "Highway Inn Operations",
                "account_number": "91234567890123",
                "bank_name": "HDFC Bank",
                "ifsc_code": "HDFC0001234",
                "is_primary": True,
            },
            format="json"
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        acc1_id = res1.json()["id"]

        # Create bank account 2
        res2 = self.client.post(
            f"/api/pos/management/accounting/bank-details/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "account_name": "Highway Inn Reserve",
                "account_number": "91876543210987",
                "bank_name": "ICICI Bank",
                "ifsc_code": "ICIC0005678",
                "is_primary": False,
            },
            format="json"
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        acc2_id = res2.json()["id"]

        # Make account 2 primary
        set_prim_res = self.client.post(
            f"/api/pos/management/accounting/bank-details/{acc2_id}/set-primary/"
        )
        self.assertEqual(set_prim_res.status_code, status.HTTP_200_OK)

        # Check account 1 is no longer primary and account 2 is primary
        acc1 = POSBankAccount.objects.get(id=acc1_id)
        acc2 = POSBankAccount.objects.get(id=acc2_id)
        self.assertFalse(acc1.is_primary)
        self.assertTrue(acc2.is_primary)

    def test_expenses_management_and_approval(self):
        exp_res = self.client.post(
            f"/api/pos/management/accounting/expenses/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "category": "RAW_MATERIALS",
                "payee_name": "Local Dairy Supplier",
                "amount": "1250.00",
                "payment_mode": "CASH",
                "status": "PENDING",
                "notes": "Emergency milk & butter purchase",
            },
            format="json"
        )
        self.assertEqual(exp_res.status_code, status.HTTP_201_CREATED)
        exp_id = exp_res.json()["id"]

        # Approve expense
        appr_res = self.client.post(
            f"/api/pos/management/accounting/expenses/{exp_id}/approve/",
            {"approved_by_name": "General Manager"},
            format="json"
        )
        self.assertEqual(appr_res.status_code, status.HTTP_200_OK)
        exp = POSExpense.objects.get(id=exp_id)
        self.assertEqual(exp.status, "APPROVED")
        self.assertEqual(exp.approved_by_name, "General Manager")

    def test_cash_denominations_auto_calculation(self):
        denom_res = self.client.post(
            f"/api/pos/management/accounting/denominations/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "count_500": 10,  # 5000
                "count_200": 5,   # 1000
                "count_100": 15,  # 1500
                "count_50": 4,    # 200
                "coins": "50.00", # 50
                "counted_by_name": "Cashier Rahul",
            },
            format="json"
        )
        self.assertEqual(denom_res.status_code, status.HTTP_201_CREATED)
        # Expected total: 5000 + 1000 + 1500 + 200 + 50 = 7750
        self.assertEqual(Decimal(denom_res.json()["total_amount"]), Decimal("7750.00"))

    def test_virtual_wallet_credit_debit(self):
        # Create wallet
        w_res = self.client.post(
            f"/api/pos/management/accounting/wallets/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "customer_name": "Vikram Seth",
                "customer_phone": "+919876543210",
                "balance": "1000.00",
                "credit_limit": "2000.00",
            },
            format="json"
        )
        self.assertEqual(w_res.status_code, status.HTTP_201_CREATED)
        w_id = w_res.json()["id"]

        # Top-up wallet by 500
        topup_res = self.client.post(
            f"/api/pos/management/accounting/wallets/{w_id}/top-up/",
            {"amount": "500.00", "note": "VIP Member advance topup", "performed_by": "Cashier"},
            format="json"
        )
        self.assertEqual(topup_res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(topup_res.json()["new_balance"]), Decimal("1500.00"))

        # Debit wallet by 300
        debit_res = self.client.post(
            f"/api/pos/management/accounting/wallets/{w_id}/debit/",
            {"amount": "300.00", "order_id": "ORD-101", "note": "Dinner bill payment", "performed_by": "Cashier"},
            format="json"
        )
        self.assertEqual(debit_res.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(debit_res.json()["new_balance"]), Decimal("1200.00"))

        # Check transactions list
        wallet = POSVirtualWallet.objects.get(id=w_id)
        self.assertEqual(wallet.transactions.count(), 2)

    def test_shift_and_cash_drawer_management(self):
        # 1. Open shift
        open_res = self.client.post(
            "/api/pos/management/shifts/open-shift/",
            {
                "register_id": str(self.register.id),
                "cashier_name": "Rohan Deshmukh",
                "opening_float": "2000.00",
                "notes": "Morning lunch shift",
            },
            format="json"
        )
        self.assertEqual(open_res.status_code, status.HTTP_201_CREATED)
        shift_id = open_res.json()["id"]

        # 2. Query active shift
        active_res = self.client.get(
            f"/api/pos/management/shifts/active/?register_id={self.register.id}"
        )
        self.assertEqual(active_res.status_code, status.HTTP_200_OK)
        self.assertTrue(active_res.json()["active"])
        self.assertEqual(active_res.json()["shift"]["id"], shift_id)

        # 3. Mid-shift cash movement (top-up float +500)
        movement_res = self.client.post(
            f"/api/pos/management/shifts/{shift_id}/cash-movement/",
            {
                "movement_type": "TOP_UP",
                "amount": "500.00",
                "reason": "Customer gave large 2000 note; extra change added",
            },
            format="json"
        )
        self.assertEqual(movement_res.status_code, status.HTTP_201_CREATED)

        # 4. Close shift
        close_res = self.client.post(
            f"/api/pos/management/shifts/{shift_id}/close-shift/",
            {
                "actual_cash_counted": "2500.00",
                "denominations": {
                    "count_500": 5,
                },
                "notes": "Shift closed smoothly with zero discrepancy",
            },
            format="json"
        )
        self.assertEqual(close_res.status_code, status.HTTP_200_OK)
        closed_data = close_res.json()
        self.assertEqual(closed_data["status"], "CLOSED")
        self.assertEqual(Decimal(closed_data["discrepancy_amount"]), Decimal("0.00"))

    def test_biller_group_and_staff_pin_authentication(self):
        # 1. Create Biller Group
        grp_res = self.client.post(
            f"/api/pos/management/users/biller-groups/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "name": "Floor Captains",
                "can_void_kot": True,
                "can_give_discount": True,
                "max_discount_percentage": "15.00",
            },
            format="json"
        )
        self.assertEqual(grp_res.status_code, status.HTTP_201_CREATED)
        group_id = grp_res.json()["id"]

        # 2. Create Staff User with 4-digit PIN '1536'
        staff_res = self.client.post(
            f"/api/pos/management/users/biller-users/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "name": "PAPI",
                "username": "papi_captain",
                "user_code": "1536",
                "pin": "1536",
                "phone": "9892001125",
                "biller_group": group_id,
            },
            format="json"
        )
        self.assertEqual(staff_res.status_code, status.HTTP_201_CREATED)
        staff_id = staff_res.json()["id"]

        # 3. Test PIN Login with wrong PIN
        wrong_res = self.client.post(
            "/api/pos/management/users/pin-login/",
            {
                "outlet_id": str(self.outlet.id),
                "user_code": "1536",
                "pin": "9999",
            },
            format="json"
        )
        self.assertEqual(wrong_res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 4. Test PIN Login with correct PIN '1536'
        auth_res = self.client.post(
            "/api/pos/management/users/pin-login/",
            {
                "outlet_id": str(self.outlet.id),
                "user_code": "1536",
                "pin": "1536",
            },
            format="json"
        )
        self.assertEqual(auth_res.status_code, status.HTTP_200_OK)
        staff_data = auth_res.json()["staff"]
        self.assertEqual(staff_data["name"], "PAPI")
        self.assertEqual(staff_data["biller_group"], "Floor Captains")
        self.assertTrue(staff_data["permissions"]["can_void_kot"])
        self.assertEqual(staff_data["permissions"]["max_discount_percentage"], 15.0)

        # 5. Test Supervisor Verify
        sup_res = self.client.post(
            "/api/pos/management/users/supervisor-verify/",
            {
                "outlet_id": str(self.outlet.id),
                "supervisor_pin": "1536",
                "action": "VOID_KOT",
            },
            format="json"
        )
        self.assertEqual(sup_res.status_code, status.HTTP_200_OK)

    def test_marketplace_and_support_tickets(self):
        # Create marketplace integration
        mp_res = self.client.post(
            f"/api/pos/management/marketplace/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "platform": "ZOMATO",
                "name": "Zomato Online Delivery",
                "store_id": "ZOM-98214",
                "is_connected": False,
            },
            format="json"
        )
        self.assertEqual(mp_res.status_code, status.HTTP_201_CREATED)
        mp_id = mp_res.json()["id"]

        # Toggle connection
        toggle_res = self.client.post(f"/api/pos/management/marketplace/{mp_id}/toggle-connection/")
        self.assertEqual(toggle_res.status_code, status.HTTP_200_OK)
        self.assertTrue(toggle_res.json()["is_connected"])
        self.assertEqual(toggle_res.json()["status"], "CONNECTED")

        # Test connection ping
        ping_res = self.client.post(f"/api/pos/management/marketplace/{mp_id}/test-connection/")
        self.assertEqual(ping_res.status_code, status.HTTP_200_OK)
        self.assertTrue(ping_res.json()["success"])

        # Create support ticket
        tick_res = self.client.post(
            f"/api/pos/management/support-tickets/?outlet_id={self.outlet.id}",
            {
                "outlet": str(self.outlet.id),
                "category": "BILLING_HARDWARE",
                "subject": "Printer Paper Jam",
                "description": "Thermal printer not feeding 80mm rolls properly",
                "priority": "HIGH",
            },
            format="json"
        )
        self.assertEqual(tick_res.status_code, status.HTTP_201_CREATED)
        tick_id = tick_res.json()["id"]

        # Resolve support ticket
        resolve_res = self.client.post(
            f"/api/pos/management/support-tickets/{tick_id}/resolve/",
            {"response_notes": "Cleaned roller gears, printing verified"},
            format="json"
        )
        self.assertEqual(resolve_res.status_code, status.HTTP_200_OK)
        ticket = POSSupportTicket.objects.get(id=tick_id)
        self.assertEqual(ticket.status, "RESOLVED")

    def test_data_management_stats_and_reset(self):
        stats_res = self.client.get(f"/api/pos/management/data/stats/?outlet_id={self.outlet.id}")
        self.assertEqual(stats_res.status_code, status.HTTP_200_OK)
        self.assertIn("stats", stats_res.json())

        reset_res = self.client.post(
            f"/api/pos/management/data/reset-demo/?outlet_id={self.outlet.id}",
            {"confirmed_by": "Super Admin"},
            format="json"
        )
        self.assertEqual(reset_res.status_code, status.HTTP_200_OK)
        self.assertTrue(reset_res.json()["success"])
