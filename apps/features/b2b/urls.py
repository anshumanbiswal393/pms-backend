from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.features.b2b.views import B2BPartnerViewSet

router = DefaultRouter()
router.register(r'b2b-agents', B2BPartnerViewSet, basename='b2bpartner')

urlpatterns = [
    path('', include(router.urls)),
]
