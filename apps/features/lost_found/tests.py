from django.utils import timezone
from rest_framework.test import APITestCase
from apps.core.tenants.models import Tenant, Property
from apps.core.accounts.models import AppUser
from apps.features.lost_found.models import LostFoundItem
from apps.features.crm.models import GuestProfile, GuestContact
from apps.core.reference.models import ReservationSource
from apps.features.reservations.models import Reservation
import tempfile
from django.core.files.uploadedfile import SimpleUploadedFile

class LostFoundAPITests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Lost Tenant', subdomain='lostfound', country='India', currency='INR', timezone='UTC'
        )
        self.property = Property.objects.create(
            tenant=self.tenant, name='Hotel Lost', address_line_1='Street', city='Goa',
            state='Goa', country='India', postal_code='403001', contact_email='lost@test.com',
            contact_phone='+91', currency='INR', timezone='UTC'
        )
        self.user = AppUser.objects.create_user(
            email='admin@lost.com', password='Password123', tenant=self.tenant, name='Admin', username='lostadmin'
        )
        self.client.credentials(HTTP_X_TENANT_SUBDOMAIN='lostfound')
        self.client.force_authenticate(user=self.user)

        # Create basic references for reservation
        self.source = ReservationSource.objects.create(code="DIRECT", name="Direct")

    def test_lost_found_workflows(self):
        # 1. Create Found Item and verify sequential reference_number (starts at LF-301)
        response = self.client.post('/api/lost-found/items/', {
            'property': str(self.property.id),
            'item_type': 'FOUND',
            'item_name': 'iPhone 15',
            'description': 'Found near the swimming pool area.',
            'location_found': 'Pool Side',
            'reported_by': str(self.user.id),
            'status': 'REPORTED'
        }, format='json')
        self.assertEqual(response.status_code, 201)
        item_id = response.data['id']
        self.assertEqual(response.data['reference_number'], 'LF-301')

        # 2. Claim Item
        claim_res = self.client.post(f'/api/lost-found/items/{item_id}/claim/', {
            'claimed_by': 'John Doe'
        }, format='json')
        self.assertEqual(claim_res.status_code, 200)
        self.assertEqual(claim_res.data['status'], 'CLAIMED')
        self.assertEqual(claim_res.data['claimed_by'], 'John Doe')

        # 3. Create another found item to dispose and verify reference_number increment (LF-302)
        response2 = self.client.post('/api/lost-found/items/', {
            'property': str(self.property.id),
            'item_type': 'FOUND',
            'item_name': 'Water Bottle',
            'description': 'Plastic bottle left in room 101.',
            'location_found': 'Room 101',
            'reported_by': str(self.user.id),
            'status': 'REPORTED'
        }, format='json')
        self.assertEqual(response2.status_code, 201)
        item_id2 = response2.data['id']
        self.assertEqual(response2.data['reference_number'], 'LF-302')

        # 4. Dispose Item
        dispose_res = self.client.post(f'/api/lost-found/items/{item_id2}/dispose/', {
            'disposed_reason': 'Recycled after 30 days.'
        }, format='json')
        self.assertEqual(dispose_res.status_code, 200)
        self.assertEqual(dispose_res.data['status'], 'DISPOSED')
        self.assertEqual(dispose_res.data['disposed_reason'], 'Recycled after 30 days.')

    def test_image_upload_and_representation(self):
        # Create a mock image file
        mock_image = SimpleUploadedFile(
            name="test_item.jpg",
            content=b"test_image_data",
            content_type="image/jpeg"
        )
        
        response = self.client.post('/api/lost-found/items/', {
            'property': str(self.property.id),
            'item_type': 'FOUND',
            'item_name': 'Camera',
            'description': 'Sony DSLR camera.',
            'location_found': 'Room 205',
            'reported_by': str(self.user.id),
            'status': 'REPORTED',
            'image': mock_image
        }, format='multipart')
        
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data['image'])
        self.assertTrue('test_item' in response.data['image'])

    def test_stats_and_matching_flow(self):
        # Create a Guest Profile and a Guest Contact
        guest = GuestProfile.objects.create(
            tenant=self.tenant,
            first_name='Sophie',
            last_name='Laurent'
        )
        contact = GuestContact.objects.create(
            tenant=self.tenant,
            guest=guest,
            email='sophie@example.com',
            phone='+12345678',
            is_primary=True
        )

        # Create a Reservation for this guest that overlaps the found date
        today = timezone.now().date()
        Reservation.objects.create(
            tenant=self.tenant,
            property=self.property,
            primary_guest=guest,
            reservation_source=self.source,
            booking_date=today,
            arrival_date=today - timezone.timedelta(days=1),
            departure_date=today + timezone.timedelta(days=2),
            status='CONFIRMED',
            confirmation_number='LF-CONF-999',
            reservation_type='FIT',
            market_segment='LEISURE'
        )

        # Create a found item where the description contains initials matching 'Sophie Laurent' ('S.L.')
        response = self.client.post('/api/lost-found/items/', {
            'property': str(self.property.id),
            'item_type': 'FOUND',
            'item_name': 'Gold bracelet',
            'description': "18k gold chain with a small heart pendant. Engraved 'S.L.' on the clasp.",
            'location_found': 'Spa locker',
            'reported_by': str(self.user.id),
            'status': 'REPORTED'
        }, format='json')
        self.assertEqual(response.status_code, 201)
        item_id = response.data['id']

        # Verify stats endpoint returns correct values
        stats_res = self.client.get('/api/lost-found/items/stats/')
        self.assertEqual(stats_res.status_code, 200)
        self.assertEqual(stats_res.data['open_items'], 1)
        self.assertEqual(stats_res.data['match_suggestions'], 1)

        # Verify suggested matches endpoint returns Sophie Laurent
        match_res = self.client.get(f'/api/lost-found/items/{item_id}/suggested-matches/')
        self.assertEqual(match_res.status_code, 200)
        self.assertEqual(len(match_res.data), 1)
        self.assertEqual(match_res.data[0]['guest']['first_name'], 'Sophie')
        self.assertEqual(match_res.data[0]['guest']['last_name'], 'Laurent')
        self.assertEqual(match_res.data[0]['confidence'], 'HIGH')

        # Verify notifying the guest updates status to AWAITING_CLAIM
        notify_res = self.client.post(f'/api/lost-found/items/{item_id}/notify/', {
            'guest_id': str(guest.id)
        }, format='json')
        self.assertEqual(notify_res.status_code, 200)
        self.assertEqual(notify_res.data['status'], 'AWAITING_CLAIM')
        self.assertEqual(notify_res.data['guest_name'], 'Sophie Laurent')
        self.assertEqual(notify_res.data['guest_contact'], 'sophie@example.com')

        # Check stats again
        stats_res2 = self.client.get('/api/lost-found/items/stats/')
        self.assertEqual(stats_res2.data['open_items'], 0)
        self.assertEqual(stats_res2.data['awaiting_claim'], 1)

    def test_search_endpoint(self):
        # Create item to search
        self.client.post('/api/lost-found/items/', {
            'property': str(self.property.id),
            'item_type': 'FOUND',
            'item_name': 'Blue Umbrella',
            'description': 'Found in the lobby.',
            'location_found': 'Lobby',
            'finder_name': 'Sherlock Holmes',
            'status': 'REPORTED'
        }, format='json')

        # Search by description
        search_res1 = self.client.get('/api/lost-found/items/?search=lobby')
        self.assertEqual(search_res1.status_code, 200)
        results1 = search_res1.data['results'] if isinstance(search_res1.data, dict) else search_res1.data
        self.assertEqual(len(results1), 1)

        # Search by finder name
        search_res2 = self.client.get('/api/lost-found/items/?search=Sherlock')
        self.assertEqual(search_res2.status_code, 200)
        results2 = search_res2.data['results'] if isinstance(search_res2.data, dict) else search_res2.data
        self.assertEqual(len(results2), 1)

        # Search by item name
        search_res3 = self.client.get('/api/lost-found/items/?search=Umbrella')
        self.assertEqual(search_res3.status_code, 200)
        results3 = search_res3.data['results'] if isinstance(search_res3.data, dict) else search_res3.data
        self.assertEqual(len(results3), 1)

