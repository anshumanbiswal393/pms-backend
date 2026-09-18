from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.core.reference.views import (
    CountryViewSet, NationalityViewSet, LanguageViewSet,
    CurrencyViewSet, DocumentTypeViewSet, ReservationSourceViewSet, TimezoneViewSet,
    StateViewSet, PaymentModeViewSet, VenueViewSet, EventTypeViewSet
)

router = DefaultRouter()
router.register(r'countries', CountryViewSet, basename='country')
router.register(r'states', StateViewSet, basename='state')
router.register(r'nationalities', NationalityViewSet, basename='nationality')
router.register(r'languages', LanguageViewSet, basename='language')
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'payment-modes', PaymentModeViewSet, basename='paymentmode')
router.register(r'document-types', DocumentTypeViewSet, basename='documenttype')
router.register(r'reservation-sources', ReservationSourceViewSet, basename='reservationsource')
router.register(r'timezones', TimezoneViewSet, basename='timezone')
router.register(r'venues', VenueViewSet, basename='venue')
router.register(r'event-types', EventTypeViewSet, basename='eventtype')

urlpatterns = [
    path('', include(router.urls)),
]

