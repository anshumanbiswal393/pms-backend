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
        qs = B2BPartner.objects.filter(tenant=tenant)
        search = self.request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(agent_id__icontains=search) |
                Q(contact_person__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(location__icontains=search)
            )
        status_val = self.request.query_params.get('status')
        if status_val and status_val != 'All':
            qs = qs.filter(status__iexact=status_val)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        serializer.save(tenant=tenant)
