from django.test import TestCase
from rest_framework.test import APIClient
from datetime import datetime, timedelta
from apps.booking.models import Hotel, RoomType, RatePlan, RoomInventory, PromoCode

class Epic1SearchAndAvailabilityTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.today = datetime.now().date()
        self.tomorrow = self.today + timedelta(days=1)
        self.day_after = self.today + timedelta(days=2)

        # 1. Create Test Hotel
        self.hotel = Hotel.objects.create(
            slug='test-resort',
            name='Test Luxury Resort',
            property_type='Resort',
            chain_name='Retrod Luxury Collection',
            star_rating=5,
            city='Bhubaneswar',
            state='Odisha',
            address='123 Beach Road',
            phone='+91 99999 88888',
            email='test@resort.com'
        )

        # 2. Create Test Room Type
        self.room_type = RoomType.objects.create(
            hotel=self.hotel,
            name='Deluxe Ocean View Room',
            slug='deluxe-ocean',
            bed_type='King',
            max_adults=2,
            max_children=1,
            base_price=3000.00,
            total_rooms=10,
            is_active=True
        )

        # 3. Create Rate Plan
        self.rate_plan = RatePlan.objects.create(
            room_type=self.room_type,
            title='CP - Breakfast Included Rate',
            single_occupancy_price=3000.00,
            single_occupancy_tax=360.00,
            double_occupancy_price=3500.00,
            double_occupancy_tax=420.00,
            is_popular=True
        )

        # 4. Create Room Inventories
        self.inv1 = RoomInventory.objects.create(
            room_type=self.room_type,
            date=self.today,
            available_rooms=5,
            custom_price=3000.00,
            min_los=1,
            max_los=14,
            closed_to_arrival=False,
            closed_to_departure=False
        )
        self.inv2 = RoomInventory.objects.create(
            room_type=self.room_type,
            date=self.tomorrow,
            available_rooms=5,
            custom_price=3200.00,
            min_los=1,
            max_los=14,
            closed_to_arrival=False,
            closed_to_departure=False
        )

        # 5. Create Sample Promo Codes
        self.promo_percent = PromoCode.objects.create(
            code='SUMMER2026',
            description='Summer 20% Off',
            discount_type='PERCENT',
            discount_value=20.00,
            max_discount_amount=2000.00,
            min_booking_amount=1000.00,
            is_active=True
        )
        self.promo_corp = PromoCode.objects.create(
            code='CORP_RETROD',
            description='Corporate 25% Off',
            discount_type='PERCENT',
            discount_value=25.00,
            min_booking_amount=0.00,
            is_active=True,
            is_corporate=True,
            corporate_company_name='Retrod Technologies'
        )

    # --- 1. Property Search Tests ---
    def test_01_property_search_by_city(self):
        url = '/api/v1/properties/search/?q=Bhubaneswar'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertGreaterEqual(response.data['total_properties_found'], 1)

    def test_02_property_search_by_type_filter(self):
        url = '/api/v1/properties/search/?property_type=Resort'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        props = response.data['properties']
        self.assertTrue(any(p['slug'] == 'test-resort' for p in props))

    # --- 2. Occupancy Calculation Tests ---
    def test_03_occupancy_calc_valid(self):
        url = '/api/v1/availability/occupancy-calc/'
        payload = {
            'check_in': str(self.today),
            'check_out': str(self.tomorrow),
            'num_adults': 2,
            'num_children': 2,
            'child_ages': [1, 7],
            'num_infants': 0,
            'extra_beds': 1
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['stay_duration']['total_nights'], 1)
        self.assertEqual(response.data['occupancy_breakdown']['categorized']['infants_under_2'], 1)
        self.assertEqual(response.data['occupancy_breakdown']['categorized']['children_2_to_11'], 1)
        self.assertEqual(response.data['extra_beds']['requested_beds'], 1)

    # --- 3. Real-Time Availability & Restriction Tests ---
    def test_04_availability_search_success(self):
        url = '/api/v1/availability/search/'
        payload = {
            'hotel_slug': 'test-resort',
            'check_in': str(self.today),
            'check_out': str(self.tomorrow),
            'num_rooms': 1,
            'adults': 2
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertGreaterEqual(len(response.data['available_room_types']), 1)

    def test_05_min_los_restriction(self):
        # Set Min LOS = 3 nights for inv1
        self.inv1.min_los = 3
        self.inv1.save()

        url = '/api/v1/availability/search/'
        payload = {
            'hotel_slug': 'test-resort',
            'check_in': str(self.today),
            'check_out': str(self.tomorrow), # 1 night stay
            'num_rooms': 1,
            'adults': 2
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        deluxe_avail = [rt for rt in response.data['available_room_types'] if rt['slug'] == 'deluxe-ocean']
        self.assertEqual(len(deluxe_avail), 0)
        deluxe_sold = [rt for rt in response.data['sold_out_room_types'] if rt['slug'] == 'deluxe-ocean']
        self.assertEqual(len(deluxe_sold), 1)
        self.assertIn('Minimum stay requirement', deluxe_sold[0]['reason'])

    def test_06_closed_to_arrival_restriction(self):
        # Set Closed to Arrival for inv1
        self.inv1.closed_to_arrival = True
        self.inv1.save()

        url = '/api/v1/availability/search/'
        payload = {
            'hotel_slug': 'test-resort',
            'check_in': str(self.today),
            'check_out': str(self.tomorrow),
            'num_rooms': 1,
            'adults': 2
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        deluxe_avail = [rt for rt in response.data['available_room_types'] if rt['slug'] == 'deluxe-ocean']
        self.assertEqual(len(deluxe_avail), 0)
        deluxe_sold = [rt for rt in response.data['sold_out_room_types'] if rt['slug'] == 'deluxe-ocean']
        self.assertEqual(len(deluxe_sold), 1)
        self.assertEqual(deluxe_sold[0]['reason'], 'Closed to Arrival on selected check-in date.')

    def test_07_stop_sell_blocked_restriction(self):
        from apps.booking.views import get_or_create_hotel_tenant
        hotel = get_or_create_hotel_tenant('test-resort')

        # Block inventory (Stop sell) for all room types in hotel to test alternative date suggestions
        for rt in hotel.room_types.all():
            RoomInventory.objects.update_or_create(
                room_type=rt,
                date=self.today,
                defaults={'available_rooms': 0, 'is_blocked': True}
            )

        url = '/api/v1/availability/search/'
        payload = {
            'hotel_slug': 'test-resort',
            'check_in': str(self.today),
            'check_out': str(self.tomorrow),
            'num_rooms': 1,
            'adults': 2
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['available_room_types']), 0)
        self.assertTrue(len(response.data['alternative_date_suggestions']) > 0)



    # --- 4. Promo Code Validation Tests ---
    def test_08_promo_code_validation_percentage(self):
        url = '/api/v1/promo-codes/validate/'
        payload = {
            'code': 'SUMMER2026',
            'hotel_slug': 'test-resort',
            'booking_amount': 5000.00
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['valid'])
        self.assertEqual(response.data['discount_amount'], 1000.00) # 20% of 5000
        self.assertEqual(response.data['final_amount'], 4000.00)

    def test_09_corporate_promo_code(self):
        url = '/api/v1/promo-codes/validate/'
        payload = {
            'code': 'CORP_RETROD',
            'hotel_slug': 'test-resort',
            'booking_amount': 4000.00
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_corporate'])
        self.assertEqual(response.data['corporate_company_name'], 'Retrod Technologies')
        self.assertEqual(response.data['discount_amount'], 1000.00) # 25% of 4000

    def test_10_invalid_promo_code(self):
        url = '/api/v1/promo-codes/validate/'
        payload = {
            'code': 'INVALID99',
            'booking_amount': 2000.00
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data['success'])

    # --- 5. Flexible Price Calendar Matrix Tests ---
    def test_11_flexible_calendar_matrix(self):
        url = f'/api/v1/availability/flexible-calendar/?hotel_slug=test-resort&range_days=7'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        self.assertEqual(len(response.data['calendar_matrix']), 7)
        self.assertIn('lowest_price_per_night', response.data['calendar_matrix'][0])
