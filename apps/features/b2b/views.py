from rest_framework import viewsets, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from apps.features.b2b.models import B2BPartner
from apps.features.b2b.serializers import B2BPartnerSerializer

class B2BPartnerViewSet(viewsets.ModelViewSet):
    serializer_class = B2BPartnerSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    lookup_field = 'agent_id'

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return B2BPartner.objects.none()
        return B2BPartner.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)
