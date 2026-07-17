from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.features.reservations.views import (
    CorporateAccountViewSet, GroupBlockViewSet, ReservationViewSet, WaitlistViewSet
)

router = DefaultRouter()
router.register(r'corporate-accounts', CorporateAccountViewSet, basename='corporateaccount')
router.register(r'group-blocks', GroupBlockViewSet, basename='groupblock')
router.register(r'bookings', ReservationViewSet, basename='reservation')
router.register(r'waitlist', WaitlistViewSet, basename='waitlist')

urlpatterns = [
    path('', include(router.urls)),
]
