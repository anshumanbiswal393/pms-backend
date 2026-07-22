from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.core.tenants.models import Tenant, Property
from apps.core.accounts.models import AppUser
from apps.features.inventory.models import InventoryUnitCategory, InventoryUnitType, InventoryUnit
from apps.features.assets.models import Asset
from apps.features.maintenance.models import MaintenanceTicket, MaintenanceSchedule

class MaintenanceAPITests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Maint Tenant', subdomain='maint', country='India', currency='INR', timezone='UTC'
        )
        self.property = Property.objects.create(
            tenant=self.tenant, name='Hotel Maint', address_line_1='Street', city='Goa',
            state='Goa', country='India', postal_code='403001', contact_email='maint@test.com',
            contact_phone='+91', currency='INR', timezone='UTC'
        )
        self.user = AppUser.objects.create_user(
            email='staff@maint.com', password='Password123', tenant=self.tenant, name='Staff', username='staff'
        )
        self.client.credentials(HTTP_X_TENANT_SUBDOMAIN='maint')
        self.client.force_authenticate(user=self.user)

        # Inventory & Asset Setup
        self.cat = InventoryUnitCategory.objects.create(tenant=self.tenant, code='room', name='Room')
        self.unit_type = InventoryUnitType.objects.create(
            tenant=self.tenant, property=self.property, category=self.cat, code='STD', name='Standard Room'
        )
        self.unit = InventoryUnit.objects.create(
            tenant=self.tenant, property=self.property, inventory_unit_type=self.unit_type, name='301'
        )
        self.asset = Asset.objects.create(
            tenant=self.tenant, property=self.property, asset_code='AC-301', asset_name='AC Unit', asset_type='AC'
        )

    def test_maintenance_ticket_lifecycle(self):
        # 1. Create Ticket
        response = self.client.post('/api/maintenance/tickets/', {
            'property': str(self.property.id),
            'inventory_unit': str(self.unit.id),
            'asset': str(self.asset.id),
            'title': 'AC Leaking',
            'description': 'Water leaking from indoor unit',
            'priority': 'HIGH',
            'status': 'REPORTED',
            'category': 'HVAC'
        }, format='json')
        self.assertEqual(response.status_code, 201)
        ticket_id = response.data['id']
        self.assertEqual(response.data['status'], 'REPORTED')
        self.assertEqual(response.data['category'], 'HVAC')
        self.assertEqual(response.data['room_location'], f"Room {self.unit.name}")

        # 2. Assign Ticket
        assign_res = self.client.post('/api/maintenance/assign/', {
            'ticket_id': ticket_id,
            'user_id': str(self.user.id)
        }, format='json')
        self.assertEqual(assign_res.status_code, 200)
        self.assertEqual(assign_res.data['status'], 'IN_PROGRESS')
        
        # Verify InventoryUnit maintenance status updated to active
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.maintenance_status, 'active')

        # Test Stats endpoint before completing
        stats_res = self.client.get('/api/maintenance/tickets/stats/')
        self.assertEqual(stats_res.status_code, 200)
        self.assertEqual(stats_res.data['open_work_orders'], 1)
        # Note: Rooms OOO count is based on operational_status in ['maintenance', 'offline']. Let's verify structure.
        self.assertIn('rooms_ooo', stats_res.data)
        self.assertIn('pm_due_this_week', stats_res.data)

        # 3. Complete Ticket
        complete_res = self.client.post('/api/maintenance/complete/', {
            'ticket_id': ticket_id
        }, format='json')
        self.assertEqual(complete_res.status_code, 200)
        self.assertEqual(complete_res.data['status'], 'RESOLVED')

        # Verify InventoryUnit maintenance status reset to none
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.maintenance_status, 'none')

        # Test Stats endpoint after completing
        stats_res2 = self.client.get('/api/maintenance/tickets/stats/')
        self.assertEqual(stats_res2.status_code, 200)
        self.assertEqual(stats_res2.data['open_work_orders'], 0)
        self.assertGreaterEqual(stats_res2.data['avg_resolution_hours'], 0.0)
