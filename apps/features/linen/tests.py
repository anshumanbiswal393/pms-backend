from django.utils import timezone
from rest_framework.test import APITestCase
from apps.core.tenants.models import Tenant, Property
from apps.core.accounts.models import AppUser
from apps.features.inventory.models import InventoryUnitCategory, InventoryUnitType, InventoryUnit
from apps.features.linen.models import LinenItem, LinenAssignment, LaundryRecord, GuestLaundryOrder, LaundryMachine

class LinenAPITests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Linen Tenant', subdomain='linen', country='India', currency='INR', timezone='UTC'
        )
        self.property = Property.objects.create(
            tenant=self.tenant, name='Hotel Linen', address_line_1='Street', city='Goa',
            state='Goa', country='India', postal_code='403001', contact_email='linen@test.com',
            contact_phone='+91', currency='INR', timezone='UTC'
        )
        self.user = AppUser.objects.create_user(
            email='admin@linen.com', password='Password123', tenant=self.tenant, name='Admin', username='linenadmin'
        )
        self.client.credentials(HTTP_X_TENANT_SUBDOMAIN='linen')
        self.client.force_authenticate(user=self.user)

        # Inventory setup
        self.cat = InventoryUnitCategory.objects.create(tenant=self.tenant, code='room', name='Room')
        self.unit_type = InventoryUnitType.objects.create(
            tenant=self.tenant, property=self.property, category=self.cat, code='STD', name='Standard Room'
        )
        self.unit_1 = InventoryUnit.objects.create(
            tenant=self.tenant, property=self.property, inventory_unit_type=self.unit_type, name='101'
        )

    def test_linen_crud_and_adjustment(self):
        # 1. Create Linen Item
        response = self.client.post('/api/linen/items/', {
            'property': str(self.property.id),
            'name': 'King Bed Sheet',
            'code': 'KBS-1',
            'total_qty': 100,
            'par_stock': 20,
            'status': 'ACTIVE'
        }, format='json')
        self.assertEqual(response.status_code, 201)
        item_id = response.data['id']

        # 2. Adjust Stock
        adjust_res = self.client.post(f'/api/linen/items/{item_id}/adjust-stock/', {
            'quantity': 50
        }, format='json')
        self.assertEqual(adjust_res.status_code, 200)
        self.assertEqual(adjust_res.data['total_qty'], 150)

        # 3. Detailed Stock Breakdown Update
        stock_update_res = self.client.post(f'/api/linen/items/{item_id}/update-stock/', {
            'total_qty': 500,
            'in_use_qty': 300,
            'in_wash_qty': 150,
            'damaged_qty': 10,
            'location': 'Housekeeping'
        }, format='json')
        self.assertEqual(stock_update_res.status_code, 200)
        self.assertEqual(stock_update_res.data['in_use_qty'], 300)
        self.assertEqual(stock_update_res.data['stock_status'], 'NORMAL')

        # 4. Assign Linen to room
        assign_res = self.client.post('/api/linen/assignments/', {
            'linen_item': item_id,
            'inventory_unit': str(self.unit_1.id),
            'quantity': 4
        }, format='json')
        self.assertEqual(assign_res.status_code, 201)

        # 5. Create Laundry Record
        laundry_res = self.client.post('/api/linen/laundry/', {
            'property': str(self.property.id),
            'linen_item': item_id,
            'quantity_sent': 10,
            'sent_date': '2026-06-25',
            'expected_return_date': '2026-06-27',
            'status': 'SENT'
        }, format='json')
        self.assertEqual(laundry_res.status_code, 201)
        laundry_id = laundry_res.data['id']

        # 6. Receive Laundry
        receive_res = self.client.post(f'/api/linen/laundry/{laundry_id}/receive-laundry/', {
            'quantity': 10
        }, format='json')
        self.assertEqual(receive_res.status_code, 200)
        self.assertEqual(receive_res.data['status'], 'RETURNED')

    def test_guest_laundry_order_flow(self):
        # Create Guest Laundry Order with items
        order_res = self.client.post('/api/linen/orders/', {
            'property': str(self.property.id),
            'room_number': '402',
            'guest_name': 'Alice Smith',
            'service_speed': 'STANDARD',
            'status': 'PICKUP_REQUESTED',
            'items': [
                {'category': 'Garment', 'item_name': 'Shirts', 'quantity': 2, 'service': 'Wash & Fold', 'unit_price': 15.00},
                {'category': 'Garment', 'item_name': 'Jeans', 'quantity': 1, 'service': 'Dry Clean', 'unit_price': 25.00}
            ]
        }, format='json')
        self.assertEqual(order_res.status_code, 201)
        order_id = order_res.data['id']
        self.assertTrue(order_res.data['order_number'].startswith('LND-'))
        self.assertEqual(float(order_res.data['total_amount']), 55.00)

        # Check Dashboard Stats
        stats_res = self.client.get('/api/linen/orders/dashboard-stats/')
        self.assertEqual(stats_res.status_code, 200)
        self.assertEqual(stats_res.data['pending_pickups'], 1)
        self.assertEqual(stats_res.data['today_revenue'], 55.00)

        # Update Workflow Status
        status_res = self.client.post(f'/api/linen/orders/{order_id}/update-status/', {
            'status': 'WASHING'
        }, format='json')
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.data['status'], 'WASHING')

        # Get Receipt
        receipt_res = self.client.get(f'/api/linen/orders/{order_id}/receipt/')
        self.assertEqual(receipt_res.status_code, 200)
        self.assertEqual(receipt_res.data['order_number'], order_res.data['order_number'])

        # Post to Folio
        folio_res = self.client.post(f'/api/linen/orders/{order_id}/post-to-folio/')
        self.assertEqual(folio_res.status_code, 200)
        self.assertTrue(folio_res.data['is_posted_to_folio'])

    def test_laundry_machine_flow(self):
        # Create Machine
        machine_res = self.client.post('/api/linen/machines/', {
            'property': str(self.property.id),
            'name': 'Washer A1',
            'machine_type': 'WASHER',
            'capacity_kg': '50kg',
            'status': 'IDLE'
        }, format='json')
        self.assertEqual(machine_res.status_code, 201)
        machine_id = machine_res.data['id']

        # Update Machine Status
        update_res = self.client.post(f'/api/linen/machines/{machine_id}/update-status/', {
            'status': 'OPERATING'
        }, format='json')
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.data['status'], 'OPERATING')
