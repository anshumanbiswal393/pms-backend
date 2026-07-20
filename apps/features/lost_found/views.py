from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.features.lost_found.models import LostFoundItem
from apps.features.lost_found.serializers import LostFoundItemSerializer
from apps.features.lost_found.filters import LostFoundItemFilter
from django.utils import timezone

class LostFoundItemViewSet(viewsets.ModelViewSet):
    serializer_class = LostFoundItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = LostFoundItemFilter
    search_fields = ['reference_number', 'description', 'finder_name', 'item_name']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return LostFoundItem.objects.none()
            
        return LostFoundItem.objects.filter(tenant=tenant)

    @action(detail=True, methods=['post'], url_path='claim')
    def claim_item(self, request, pk=None):
        item = self.get_object()
        claimed_by = request.data.get('claimed_by')
        
        if not claimed_by:
            return Response({'error': 'claimed_by field is required to claim an item.'}, status=status.HTTP_400_BAD_REQUEST)
            
        item.status = 'CLAIMED'
        item.claimed_by = claimed_by
        item.claimed_date = timezone.now()
        item.save()
        return Response(LostFoundItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='dispose')
    def dispose_item(self, request, pk=None):
        item = self.get_object()
        reason = request.data.get('disposed_reason')
        
        if not reason:
            return Response({'error': 'disposed_reason field is required to dispose an item.'}, status=status.HTTP_400_BAD_REQUEST)
            
        item.status = 'DISPOSED'
        item.disposed_reason = reason
        item.save()
        return Response(LostFoundItemSerializer(item).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant not resolved.'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 1. Open items
        open_items = LostFoundItem.objects.filter(tenant=tenant, status='REPORTED').count()
        
        # 2. Awaiting claim
        awaiting_claim = LostFoundItem.objects.filter(tenant=tenant, status='AWAITING_CLAIM').count()
        
        # 3. Released - MTD (claimed items in current month)
        now = timezone.now()
        released_mtd = LostFoundItem.objects.filter(
            tenant=tenant,
            status='CLAIMED',
            claimed_date__year=now.year,
            claimed_date__month=now.month
        ).count()
        
        # 4. Match suggestions: count of items that are FOUND, status in ['REPORTED', 'MATCHED'] and have at least 1 suggestion
        match_suggestions = 0
        found_items = LostFoundItem.objects.filter(tenant=tenant, item_type='FOUND', status__in=['REPORTED', 'MATCHED'])
        for item in found_items:
            suggestions = self._calculate_suggested_matches(item)
            if len(suggestions) > 0:
                match_suggestions += 1

        return Response({
            'open_items': open_items,
            'awaiting_claim': awaiting_claim,
            'released_mtd': released_mtd,
            'match_suggestions': match_suggestions
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='suggested-matches')
    def suggested_matches(self, request, pk=None):
        item = self.get_object()
        suggestions = self._calculate_suggested_matches(item)
        return Response(suggestions, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='notify')
    def notify_guest(self, request, pk=None):
        item = self.get_object()
        guest_id = request.data.get('guest_id')
        if not guest_id:
            return Response({'error': 'guest_id field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        from apps.features.crm.models import GuestProfile
        from django.conf import settings
        try:
            guest = GuestProfile.objects.get(id=guest_id, tenant=item.tenant)
        except GuestProfile.DoesNotExist:
            return Response({'error': 'Guest not found.'}, status=status.HTTP_442_UNPROCESSABLE_ENTITY if False else status.HTTP_404_NOT_FOUND)

        from django.core.mail import send_mail
        primary_contact = guest.contacts.filter(is_primary=True).first()
        guest_email = primary_contact.email if primary_contact else None
        
        if guest_email:
            subject = f"Found Item Notification: {item.item_name}"
            body = (
                f"Dear {guest.first_name} {guest.last_name},\n\n"
                f"We are writing to inform you that we found an item matching your description:\n"
                f"Item: {item.item_name}\n"
                f"Location Found: {item.location_found}\n"
                f"Description: {item.description}\n\n"
                f"Please reply to this email or contact front desk to arrange return.\n\n"
                f"Best regards,\n"
                f"{item.property.name} Team"
            )
            try:
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [guest_email],
                    fail_silently=False
                )
            except Exception:
                pass
        
        item.guest_name = f"{guest.first_name} {guest.last_name}"
        if primary_contact:
            item.guest_contact = primary_contact.email or primary_contact.phone
        item.status = 'AWAITING_CLAIM'
        item.save()

        return Response({
            'message': 'Guest notified successfully.',
            'status': item.status,
            'guest_name': item.guest_name,
            'guest_contact': item.guest_contact
        }, status=status.HTTP_200_OK)

    def _calculate_suggested_matches(self, item):
        from apps.features.reservations.models import Reservation
        from django.conf import settings
        import re

        suggestions = []
        found_date = item.created_at.date() if item.created_at else timezone.now().date()
        
        # Match reservations active in stay period or checked out within 7 days before found date
        reservations = Reservation.objects.filter(
            property=item.property,
            arrival_date__lte=found_date,
            departure_date__gte=found_date - timezone.timedelta(days=7)
        ).select_related('primary_guest')

        # Heuristic: Try to match initials or guest name mentioned in description or location details
        initials_in_desc = []
        desc_upper = item.description.upper()
        
        # Find initials (e.g. S.L. or S.L)
        matches = re.findall(r"\b([A-Z])\.([A-Z])\b", item.description)
        for m in matches:
            initials_in_desc.append("".join(m))
        
        quoted_matches = re.findall(r"['\"]([A-Z]\.[A-Z]\.?)['\"]", item.description)
        for q in quoted_matches:
            clean_q = q.replace(".", "").upper()
            initials_in_desc.append(clean_q)

        added_guest_ids = set()
        for res in reservations:
            guest = res.primary_guest
            if not guest or guest.id in added_guest_ids:
                continue

            guest_first = guest.first_name.upper()
            guest_last = guest.last_name.upper()
            guest_initials = f"{guest_first[0] if guest_first else ''}{guest_last[0] if guest_last else ''}"

            reason = ""
            confidence = "LOW"

            initials_match = False
            for init in initials_in_desc:
                if init == guest_initials:
                    initials_match = True
                    break
            
            name_mentioned = (guest_first in desc_upper and len(guest_first) > 2) or (guest_last in desc_upper and len(guest_last) > 2)

            room_match = False
            unit_name = ""
            if item.location_found:
                digits = re.findall(r"\d+", item.location_found)
                allocations = res.room_allocations.filter(deleted_at__isnull=True)
                for alloc in allocations:
                    candidate_name = alloc.inventory_unit.name if alloc.inventory_unit else ""
                    if any(d in candidate_name for d in digits) or (item.location_found.upper() in candidate_name.upper()):
                        room_match = True
                        unit_name = candidate_name
                        break

            if room_match:
                if initials_match or name_mentioned:
                    reason = f"Stayed in matching room ({unit_name}) and initials/name match description."
                    confidence = "HIGH"
                else:
                    reason = f"Stayed in matching room ({unit_name}) around the found date."
                    confidence = "HIGH"
            elif initials_match or name_mentioned:
                reason = f"Stayed at property recently and initials/name match description ('{guest_initials}')."
                confidence = "HIGH"
            else:
                reason = f"Stayed at property during the time the item was found."
                confidence = "MEDIUM"

            contact_email = ""
            contact_phone = ""
            primary_contact = guest.contacts.filter(is_primary=True).first()
            if primary_contact:
                contact_email = primary_contact.email
                contact_phone = primary_contact.phone

            suggestions.append({
                'guest': {
                    'id': str(guest.id),
                    'first_name': guest.first_name,
                    'last_name': guest.last_name,
                    'email': contact_email,
                    'phone': contact_phone
                },
                'reason': reason,
                'confidence': confidence
            })
            added_guest_ids.add(guest.id)

        priority_map = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        suggestions.sort(key=lambda x: priority_map.get(x['confidence'], 3))

        return suggestions
