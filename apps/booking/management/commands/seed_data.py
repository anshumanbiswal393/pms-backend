from django.core.management.base import BaseCommand
from datetime import date, timedelta
from apps.booking.models import Hotel, HotelImage, Amenity, HotelAmenity, RoomType, RatePlan, RoomInventory, Policy, NearbyPlace

class Command(BaseCommand):
    help = 'Seeds multi-tenant hotels (including Hotel XYZ) into the booking engine database'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding multi-tenant hotel data...")

        # 1. HOTEL XYZ (Primary Example Tenant)
        hotel_xyz, created = Hotel.objects.get_or_create(
            slug='hotelxyz',
            defaults={
                'name': 'Hotel XYZ',
                'tagline': 'Experience Luxury & Comfort Redefined',
                'description': 'Welcome to Hotel XYZ – a premier luxury hotel offering state-of-the-art accommodation, modern amenities, fine dining, and world-class hospitality services. Perfect for business executives, family vacations, and international travelers.',
                'google_rating': 4.5,
                'total_reviews': 2850,
                'address': 'Plot No. 102, Retrod Tech Avenue, Business District, City Centre, 751001',
                'city': 'Bhubaneswar',
                'state': 'Odisha',
                'pincode': '751001',
                'latitude': 20.2961,
                'longitude': 85.8245,
                'map_embed_url': 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3742.617635678737!2d85.8338251!3d20.2644!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3a19a7e3d8f1e58b%3A0x7d0ff70f2f3f982a!2sRetrod%20Technologies!5e0!3m2!1sen!2sin!4v1700000000000!5m2!1sen!2sin',
                'phone': '+91 9876 543 210',
                'email': 'stay@hotelxyz.com',
                'whatsapp': '+919876543210',
                'check_in_time': '12:00 PM',
                'check_out_time': '11:00 AM',
                'logo_url': 'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=200&h=80&fit=crop',
                'hero_banner_url': 'https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=1200&h=600&fit=crop',
                'facebook_url': 'https://facebook.com/retrod',
                'instagram_url': 'https://instagram.com/retrod',
                'twitter_url': 'https://twitter.com/retrod',
                'linkedin_url': 'https://linkedin.com/company/retrod',
                'youtube_url': 'https://youtube.com/@retrod'
            }
        )

        # Update attributes if already existed
        hotel_xyz.map_embed_url = 'https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3742.617635678737!2d85.8338251!3d20.2644!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x3a19a7e3d8f1e58b%3A0x7d0ff70f2f3f982a!2sRetrod%20Technologies!5e0!3m2!1sen!2sin!4v1700000000000!5m2!1sen!2sin'
        hotel_xyz.facebook_url = 'https://facebook.com/retrod'
        hotel_xyz.instagram_url = 'https://instagram.com/retrod'
        hotel_xyz.twitter_url = 'https://twitter.com/retrod'
        hotel_xyz.linkedin_url = 'https://linkedin.com/company/retrod'
        hotel_xyz.youtube_url = 'https://youtube.com/@retrod'
        hotel_xyz.save()

        # Hotel XYZ Images
        xyz_images = [
            ('https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?w=1200&auto=format&fit=crop', 'exterior', 'Hotel XYZ Main View & Entrance'),
            ('https://images.unsplash.com/photo-1566073771259-6a8506099945?w=1200&auto=format&fit=crop', 'lobby', 'Grand Executive Lobby Lounge'),
            ('https://images.unsplash.com/photo-1582719508461-905c673771fd?w=1200&auto=format&fit=crop', 'lobby', 'Reception & Concierge Desk'),
            ('https://images.unsplash.com/photo-1571896349842-33c89424de2d?w=1200&auto=format&fit=crop', 'pool', 'Rooftop Swimming Pool & Spa'),
            ('https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=1200&auto=format&fit=crop', 'room', 'Deluxe King Bedroom'),
            ('https://images.unsplash.com/photo-1591088398332-8a7791972843?w=1200&auto=format&fit=crop', 'room', 'Executive Suite Lounge'),
            ('https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1200&auto=format&fit=crop', 'dining', 'Multicuisine Fine Dining')
        ]
        for idx, (url, cat, cap) in enumerate(xyz_images, start=1):
            HotelImage.objects.get_or_create(hotel=hotel_xyz, image_url=url, defaults={'category': cat, 'caption': cap, 'sort_order': idx})

        # Master Recommended Amenities
        amenities_data = [
            ('Free High Speed Wi-Fi', 'wifi'),
            ('Air Conditioning', 'wind'),
            ('Swimming Pool & Spa', 'droplet'),
            ('Multi-cuisine Restaurant', 'utensils'),
            ('24/7 Room Service', 'clock'),
            ('Fitness Center / Gym', 'activity'),
            ('Hot & Cold Water', 'thermometer'),
            ('Smart Television', 'tv'),
            ('Airport Shuttle', 'truck'),
            ('EV Charging Station', 'zap'),
            ('Bar & Lounge', 'coffee'),
            ('Banquet & Conference Hall', 'briefcase'),
            ('Electric Kettle & Tea Maker', 'coffee'),
            ('Mini Bar', 'box'),
            ('Safe Locker', 'lock'),
            ('Daily Housekeeping', 'sun'),
            ('Power Backup', 'zap'),
            ('Free On-site Parking', 'navigation'),
            ('UPI & Card Accepted', 'credit-card'),
            ('Wheelchair Access', 'user-check')
        ]
        for name, icon in amenities_data:
            am, _ = Amenity.objects.get_or_create(name=name, defaults={'icon_name': icon})
            HotelAmenity.objects.get_or_create(hotel=hotel_xyz, amenity=am)

        # Standard 4 Meal Plans (EP, CP, MAP, AP)
        standard_meal_plans = [
            ('EP (Room Only)', 'The most basic and budget-friendly room stay with essential amenities', False),
            ('CP (Room + Breakfast)', 'Includes complimentary buffet breakfast daily', False),
            ('MAP (Room + Breakfast + 1 Meal)', 'Includes breakfast and choice of lunch or dinner daily', False),
            ('AP (American Plan)', 'Includes 3 times full meals daily', False),
        ]

        # Hotel XYZ Room Categories (Matching Exact User Pricing Spec)
        xyz_rooms = [
            {
                'name': 'Standard Room', 'slug': 'standard-room', 'bed_type': 'King Bed', 'max_adults': 2, 'max_children': 1, 'base_price': 2000.00,
                'plans': {'EP': 2000.00, 'CP': 2400.00, 'MAP': 3150.00, 'AP': 3930.00},
                'description': 'The most basic and budget-friendly room with essential amenities and standard bedding.',
                'thumbnail_url': 'https://images.unsplash.com/photo-1618773928121-c32242e63f39?w=500&auto=format&fit=crop'
            },
            {
                'name': 'Superior Room', 'slug': 'superior-room', 'bed_type': 'Queen / King Bed', 'max_adults': 2, 'max_children': 2, 'base_price': 2900.00,
                'plans': {'EP': 2900.00, 'CP': 3420.00, 'MAP': 4350.00, 'AP': 5220.00},
                'description': 'A mid-tier option offering slightly more square footage and upgraded furnishings than a standard room.',
                'thumbnail_url': 'https://images.unsplash.com/photo-1590490360182-c33d57733427?w=500&auto=format&fit=crop'
            },
            {
                'name': 'Deluxe Room', 'slug': 'deluxe-room', 'bed_type': 'King Bed', 'max_adults': 3, 'max_children': 1, 'base_price': 3500.00,
                'plans': {'EP': 3500.00, 'CP': 4020.00, 'MAP': 4950.00, 'AP': 5700.00},
                'description': 'A larger room featuring premium decor, better views, and high-end amenities like a minibar or bathtub.',
                'thumbnail_url': 'https://images.unsplash.com/photo-1584132967334-10e028bd69f7?w=500&auto=format&fit=crop'
            },
            {
                'name': 'Junior Suite', 'slug': 'junior-suite', 'bed_type': 'King Bed + Seating Area', 'max_adults': 3, 'max_children': 2, 'base_price': 4500.00,
                'plans': {'EP': 4500.00, 'CP': 5220.00, 'MAP': 6250.00, 'AP': 7200.00},
                'description': 'Spacious junior suite featuring dedicated seating lounge, luxury vanity bath, and full room service.',
                'thumbnail_url': 'https://images.unsplash.com/photo-1566665797739-1674de7a421a?w=500&auto=format&fit=crop'
            },
            {
                'name': 'Executive Suite', 'slug': 'executive-suite', 'bed_type': 'Master King Suite', 'max_adults': 4, 'max_children': 2, 'base_price': 8000.00,
                'plans': {'EP': 8000.00, 'CP': 9020.00, 'MAP': 10350.00, 'AP': 11700.00},
                'description': "Ultimate luxury executive suite with separate master living room, panoramic skyline views, and private butler service.",
                'thumbnail_url': 'https://images.unsplash.com/photo-1591088398332-8a7791972843?w=500&auto=format&fit=crop'
            },
            {
                'name': 'Banquet Hall / Event Hall', 'slug': 'banquet-hall', 'bed_type': 'Custom Setup', 'max_adults': 500, 'max_children': 0, 'base_price': 25000.00,
                'plans': {'EP': 25000.00},
                'description': 'A grand hall ideal for weddings, conferences, and large social events. Accommodates up to 500 guests with state-of-the-art audio-visual equipment, central air conditioning, and customizable seating.',
                'thumbnail_url': 'https://images.unsplash.com/photo-1519167758481-83f550bb49b3?w=500&auto=format&fit=crop'
            }
        ]

        # Clean up obsolete room types for Hotel XYZ to ensure exact room types catalog
        valid_slugs = [r['slug'] for r in xyz_rooms]
        RoomType.objects.filter(hotel=hotel_xyz).exclude(slug__in=valid_slugs).delete()

        for r_data in xyz_rooms:
            base_price_val = float(r_data.get('base_price', 2000.00))
            rt, _ = RoomType.objects.get_or_create(
                hotel=hotel_xyz, slug=r_data['slug'],
                defaults={
                    'name': r_data['name'],
                    'bed_type': r_data['bed_type'],
                    'max_adults': r_data['max_adults'],
                    'max_children': r_data['max_children'],
                    'description': r_data['description'],
                    'base_price': base_price_val,
                    'current_discount_percent': 0,
                    'thumbnail_url': r_data['thumbnail_url']
                }
            )
            rt.name = r_data['name']
            rt.max_adults = r_data['max_adults']
            rt.max_children = r_data['max_children']
            rt.description = r_data['description']
            rt.base_price = base_price_val
            rt.save()

            # Delete old plans to prevent duplicate plan titles
            RatePlan.objects.filter(room_type=rt).delete()

            if r_data['slug'] == 'banquet-hall':
                RatePlan.objects.create(
                    room_type=rt, title='Banquet Venue Rental Only', description='Rental of the banquet hall space for the day. Excludes catering and meal plans.',
                    single_occupancy_price=25000.00, single_occupancy_tax=4500.00,
                    double_occupancy_price=25000.00, double_occupancy_tax=4500.00,
                    is_popular=True
                )
            else:
                plans_dict = r_data['plans']
                for p_title, p_desc, pop in standard_meal_plans:
                    p_key = 'EP' if 'EP' in p_title else ('CP' if 'CP' in p_title else ('MAP' if 'MAP' in p_title else 'AP'))
                    plan_price = plans_dict.get(p_key, base_price_val)
                    plan_tax = round(plan_price * 0.05, 2)
                    RatePlan.objects.create(
                        room_type=rt, title=p_title, description=p_desc,
                        single_occupancy_price=plan_price, single_occupancy_tax=plan_tax,
                        double_occupancy_price=plan_price, double_occupancy_tax=plan_tax,
                        is_popular=pop
                    )


        # Policies for Hotel XYZ
        xyz_policies = [
            ('privacy', 'Privacy Policy', 'Hotel XYZ is committed to safeguarding your privacy. Guest data is securely processed solely for booking confirmation and government regulatory compliance.', 1),
            ('refund_cancellation', 'Refund And Cancellation Policy', 'Free cancellation up to 24 hours before 12:00 PM check-in date. Cancellations within 24 hours attract a 1-night fee.', 2),
            ('terms', 'Terms And Conditions', 'Check-in: 12:00 PM. Check-out: 11:00 AM. Original government ID (Aadhaar, Passport, DL) required at check-in.', 3)
        ]
        for p_type, title, content, order in xyz_policies:
            Policy.objects.get_or_create(hotel=hotel_xyz, policy_type=p_type, defaults={'title': title, 'content': content, 'sort_order': order})

        # Nearby for Hotel XYZ
        xyz_nearby = [
            ('Central Railway Station', '1.2 km', 'transit'),
            ('Retrod Tech Campus', '0.5 km', 'landmark'),
            ('International Airport', '5.0 km', 'airport')
        ]
        for p_name, dist, cat in xyz_nearby:
            NearbyPlace.objects.get_or_create(hotel=hotel_xyz, place_name=p_name, defaults={'distance': dist, 'category': cat})

        self.stdout.write("Database seeded successfully with Hotel XYZ!")
