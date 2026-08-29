from django.db import models
import uuid

class Hotel(models.Model):
    uuid = models.CharField(max_length=64, unique=True, default=uuid.uuid4)
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    property_type = models.CharField(max_length=50, default='Hotel') # Hotel, Resort, Villa, Apartment
    chain_name = models.CharField(max_length=150, default='Retrod Hotels')
    star_rating = models.IntegerField(default=4)
    tagline = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    google_rating = models.DecimalField(max_digits=3, decimal_places=1, default=4.1)
    total_reviews = models.IntegerField(default=4395)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    map_embed_url = models.TextField(blank=True, null=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(max_length=100)
    whatsapp = models.CharField(max_length=50, blank=True, null=True)
    check_in_time = models.CharField(max_length=20, default='12:00 PM')
    check_out_time = models.CharField(max_length=20, default='11:00 AM')
    logo_url = models.TextField(blank=True, null=True)
    hero_banner_url = models.TextField(blank=True, null=True)
    page_title = models.CharField(max_length=255, blank=True, null=True)
    theme_color = models.CharField(max_length=50, default='#ffc107')
    what_makes_special = models.TextField(blank=True, null=True)
    backstory = models.TextField(blank=True, null=True)
    booking_engine_settings = models.JSONField(default=dict, blank=True)
    enable_google_reviews = models.BooleanField(default=True)
    google_reviews_data = models.JSONField(default=list, blank=True)
    short_description = models.TextField(blank=True, null=True)
    facebook_url = models.URLField(max_length=255, default='https://facebook.com/retrod', blank=True, null=True)
    instagram_url = models.URLField(max_length=255, default='https://instagram.com/retrod', blank=True, null=True)
    twitter_url = models.URLField(max_length=255, default='https://twitter.com/retrod', blank=True, null=True)
    linkedin_url = models.URLField(max_length=255, default='https://linkedin.com/company/retrod', blank=True, null=True)
    youtube_url = models.URLField(max_length=255, default='https://youtube.com/@retrod', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class HotelImage(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='images', on_delete=models.CASCADE)
    image_url = models.TextField()
    category = models.CharField(max_length=50, default='all')
    caption = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} - {self.category} ({self.id})"

class Amenity(models.Model):
    name = models.CharField(max_length=100)
    icon_name = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=50, default='general')

    def __str__(self):
        return self.name

class HotelAmenity(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='hotel_amenities', on_delete=models.CASCADE)
    amenity = models.ForeignKey(Amenity, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('hotel', 'amenity')

class RoomType(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='room_types', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    bed_type = models.CharField(max_length=255, default='King')
    base_included_adults = models.IntegerField(default=2)
    base_included_children = models.IntegerField(default=1)
    max_adults = models.IntegerField(default=3)
    max_children = models.IntegerField(default=2)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    current_discount_percent = models.IntegerField(default=0)
    description = models.TextField(blank=True, null=True)
    thumbnail_url = models.TextField(blank=True, null=True)
    room_images = models.JSONField(default=list, blank=True)  # [{url, caption}]
    amenities = models.JSONField(default=list, blank=True)
    total_rooms = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} - {self.name}"

    @property
    def starting_price(self):
        return float(self.base_price) * (1 - self.current_discount_percent / 100.0)

class RatePlan(models.Model):
    room_type = models.ForeignKey(RoomType, related_name='rate_plans', on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    single_occupancy_price = models.DecimalField(max_digits=10, decimal_places=2)
    single_occupancy_tax = models.DecimalField(max_digits=10, decimal_places=2)
    double_occupancy_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    double_occupancy_tax = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    extra_adult_price = models.DecimalField(max_digits=10, decimal_places=2, default=700.0)
    extra_child_price = models.DecimalField(max_digits=10, decimal_places=2, default=500.0)
    is_popular = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.room_type.name} - {self.title}"

class RoomInventory(models.Model):
    room_type = models.ForeignKey(RoomType, related_name='inventory', on_delete=models.CASCADE)
    date = models.DateField()
    available_rooms = models.IntegerField(default=5)
    custom_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_blocked = models.BooleanField(default=False) # Stop sell
    min_los = models.IntegerField(default=1) # Minimum Length of Stay restriction
    max_los = models.IntegerField(default=30) # Maximum Length of Stay restriction
    closed_to_arrival = models.BooleanField(default=False) # CTA restriction
    closed_to_departure = models.BooleanField(default=False) # CTD restriction

    class Meta:
        unique_together = ('room_type', 'date')

class Policy(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='policies', on_delete=models.CASCADE)
    policy_type = models.CharField(max_length=100) # 'privacy', 'refund_cancellation', 'terms'
    title = models.CharField(max_length=255)
    content = models.TextField()
    sort_order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.hotel.name} - {self.title}"

class NearbyPlace(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='nearby', on_delete=models.CASCADE)
    place_name = models.CharField(max_length=150)
    distance = models.CharField(max_length=50)
    category = models.CharField(max_length=50, default='transit')

    def __str__(self):
        return f"{self.place_name} ({self.distance})"

class Booking(models.Model):
    booking_reference = models.CharField(max_length=50, unique=True)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE)
    check_in = models.DateField()
    check_out = models.DateField()
    total_nights = models.IntegerField(default=1)
    num_rooms = models.IntegerField(default=1)
    num_adults = models.IntegerField(default=2)
    num_children = models.IntegerField(default=0)
    room_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_and_fees = models.DecimalField(max_digits=10, decimal_places=2)
    selected_addons = models.JSONField(default=list, blank=True)
    addons_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=50, default='PENDING')
    booking_status = models.CharField(max_length=50, default='CONFIRMED')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.booking_reference

class Guest(models.Model):
    booking = models.OneToOneField(Booking, related_name='guest', on_delete=models.CASCADE)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=100)
    phone = models.CharField(max_length=50)
    id_proof_type = models.CharField(max_length=50)
    id_proof_number = models.CharField(max_length=100)
    special_requests = models.TextField(blank=True, null=True)
    purpose_of_travel = models.CharField(max_length=50, blank=True, null=True)
    company_name = models.CharField(max_length=150, blank=True, null=True)
    company_contact = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.full_name

class EventRequest(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='event_requests')
    nature_of_event = models.CharField(max_length=100)
    num_guests = models.IntegerField(default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    halls_count = models.IntegerField(default=1)
    catering_plan = models.CharField(max_length=100, default='Standard Buffet', blank=True, null=True)
    total_catering_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    total_addons_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    require_rooms = models.BooleanField(default=False)
    num_rooms = models.IntegerField(default=0)
    additional_details = models.TextField(blank=True, null=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=50)
    email = models.EmailField(max_length=100)
    status = models.CharField(max_length=50, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nature_of_event} Request - {self.name}"

class RestaurantRequest(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='restaurant_requests')
    booking_date = models.DateField()
    booking_time = models.CharField(max_length=20)
    num_guests = models.IntegerField(default=2)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=50)
    email = models.EmailField(max_length=100)
    special_requests = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Restaurant Reservation - {self.name}"

class PromoCode(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='promo_codes', on_delete=models.CASCADE, null=True, blank=True)
    code = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=20, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=10.0)
    min_nights = models.IntegerField(default=1)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} - {self.code} ({self.discount_value})"

class AddonPackage(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='addons', on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=50, default='Dining')
    charge_type = models.CharField(max_length=50, default='Per Stay')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_pct = models.DecimalField(max_digits=5, decimal_places=2, default=18.0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} - {self.name} (₹{self.price})"

class PaymentGateway(models.Model):
    hotel = models.ForeignKey(Hotel, related_name='payment_gateways', on_delete=models.CASCADE)
    provider = models.CharField(max_length=100)
    key_id = models.CharField(max_length=255, blank=True, null=True)
    key_secret = models.CharField(max_length=255, blank=True, null=True)
    sandbox = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    pay_at_hotel = models.BooleanField(default=False)
    deposit_pct = models.DecimalField(max_digits=5, decimal_places=2, default=100.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.hotel.name} - {self.provider}"

