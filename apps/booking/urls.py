from django.urls import path
from . import views

urlpatterns = [
    # Epic 1 — Search, Availability & Inventory Engine Endpoints
    path('properties/search/', views.search_properties, name='search_properties'),
    path('availability/occupancy-calc/', views.occupancy_calc, name='occupancy_calc'),
    path('availability/search/', views.search_availability, name='search_availability'),
    path('promo-codes/validate/', views.validate_promo_code, name='validate_promo_code'),
    path('availability/flexible-calendar/', views.flexible_calendar, name='flexible_calendar'),

    # Existing Hotel & Booking Endpoints
    path('hotels/resolve/', views.resolve_hotel, name='resolve_hotel'),
    path('hotels/<str:slug>/inventory/', views.hotel_inventory, name='hotel_inventory'),
    path('hotels/<str:slug>/update_settings/', views.update_hotel_settings, name='update_hotel_settings'),
    path('hotels/<str:slug>/', views.hotel_detail, name='hotel_detail'),
    path('bookings/send-invoice-notification/', views.send_invoice_notification_view, name='send_invoice_notification'),
    path('bookings/<str:ref>/', views.get_booking_detail, name='get_booking_detail'),
    path('bookings/', views.create_booking, name='create_booking'),

    path('payments/create-order/', views.create_razorpay_order_view, name='create_razorpay_order'),
    path('payments/verify/', views.verify_razorpay_payment_view, name='verify_razorpay_payment'),

    path('event-requests/', views.create_event_request, name='create_event_request'),
    path('restaurant-requests/', views.create_restaurant_request, name='create_restaurant_request'),
]

