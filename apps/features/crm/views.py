from rest_framework import viewsets, status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from django.db.models import Q

from apps.features.crm.models import (
    GuestProfile, GuestContact, GuestDocument, GuestPreference,
    GuestTag, GuestProfileTag, GuestActivity
)
from apps.features.crm.serializers import (
    GuestProfileSerializer, GuestContactSerializer, GuestDocumentSerializer,
    GuestPreferenceSerializer, GuestTagSerializer, GuestProfileTagSerializer,
    GuestActivitySerializer, MergeProfilesRequestSerializer,
    AddLoyaltyPointsSerializer, AssignTagRequestSerializer
)
from apps.features.crm.permissions import (
    HasGuestPermission, IsMergeManager, IsVerifyDocumentManager,
    IsLoyaltyManager, IsTagManager
)
from apps.features.crm.services import (
    GuestMergeService, LoyaltyService, DocumentVerificationService,
    GuestSearchEngine, TaggingService
)

class GuestProfileViewSet(viewsets.ModelViewSet):
    serializer_class = GuestProfileSerializer
    permission_classes = [HasGuestPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestProfile.objects.none()
        
        queryset = GuestProfile.objects.filter(tenant=tenant)
        search_query = self.request.query_params.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query)
            )
        return queryset

    @extend_schema(
        parameters=[
            OpenApiParameter('query', OpenApiTypes.STR, required=False, description='Search by name, email, or phone'),
            OpenApiParameter('tag', OpenApiTypes.STR, required=False, description='Filter by tag code'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)
        
        query = request.query_params.get('query')
        tag = request.query_params.get('tag')
        
        results = GuestSearchEngine.search_guests(tenant=tenant, query_str=query, tag_code=tag)
        page = self.paginate_queryset(results)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=MergeProfilesRequestSerializer)
    @action(detail=True, methods=['post'], url_path='merge', permission_classes=[IsMergeManager])
    def merge(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        master_profile = self.get_object()
        serializer = MergeProfilesRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        duplicate_id = serializer.validated_data['duplicate_guest_id']
        try:
            duplicate_profile = GuestProfile.objects.get(id=duplicate_id, tenant=tenant)
        except GuestProfile.DoesNotExist:
            return Response({'error': f'Duplicate profile with ID {duplicate_id} not found.'}, status=status.HTTP_404_NOT_FOUND)

        merged = GuestMergeService.merge_profiles(tenant, master_profile, duplicate_profile, user=request.user)
        output_serializer = self.get_serializer(merged)
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=AddLoyaltyPointsSerializer)
    @action(detail=True, methods=['post'], url_path='loyalty', permission_classes=[IsLoyaltyManager])
    def loyalty(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        serializer = AddLoyaltyPointsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        points = serializer.validated_data['points']
        reason = serializer.validated_data['reason']

        updated_profile = LoyaltyService.add_points(tenant, profile, points, reason, user=request.user)
        output_serializer = self.get_serializer(updated_profile)
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(request=AssignTagRequestSerializer)
    @action(detail=True, methods=['post'], url_path='tag', permission_classes=[IsTagManager])
    def tag(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        serializer = AssignTagRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tag_code = serializer.validated_data['tag_code']
        pt = TaggingService.assign_tag(tenant, profile, tag_code, user=request.user)
        
        profile_serializer = self.get_serializer(profile)
        return Response(profile_serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='activities')
    def activities(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        profile = self.get_object()
        # Check active profile redirection
        active_profile = GuestMergeService.resolve_profile(profile)

        qs = GuestActivity.objects.filter(tenant=tenant, guest=active_profile).order_by('-timestamp')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = GuestActivitySerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = GuestActivitySerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='parse-document')
    def parse_document(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        file_obj = request.FILES.get('document_file')
        if not file_obj:
            return Response({'error': 'No file uploaded under key document_file.'}, status=status.HTTP_400_BAD_REQUEST)

        filename = file_obj.name.lower()
        extracted_text = ""

        try:
            if filename.endswith('.pdf'):
                from pypdf import PdfReader
                reader = PdfReader(file_obj)
                for page in reader.pages:
                    extracted_text += page.extract_text() or ""
            else:
                # Call OCR.space free API
                import requests
                url = "https://api.ocr.space/parse/image"
                payload = {'apikey': 'helloworld', 'language': 'eng'}
                files = {'file': file_obj}
                resp = requests.post(url, data=payload, files=files, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    parsed_results = data.get('ParsedResults', [])
                    if parsed_results:
                        extracted_text = parsed_results[0].get('ParsedText', '')
                
                if not extracted_text:
                    extracted_text = f"Uploaded image: {filename}"
        except Exception as e:
            return Response({'error': f"Failed to parse document: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        import re
        details = {
            'first_name': '',
            'last_name': '',
            'nationality': 'Indian',
            'document_type': 'NATIONAL_ID',
            'document_number': '',
            'expiry_date': None
        }

        # 1. Document Type Detection
        text_upper = extracted_text.upper()
        if 'PASSPORT' in text_upper or 'REPUBLIC OF INDIA' in text_upper:
            details['document_type'] = 'PASSPORT'
        elif 'DRIV' in text_upper or 'LICENSE' in text_upper or 'LICENCE' in text_upper:
            details['document_type'] = 'DRIVING_LICENCE'
        else:
            details['document_type'] = 'NATIONAL_ID'

        # 2. Document Number Extraction
        # Aadhaar: 12 digits (grouped with spaces, dashes, or no spaces)
        aadhaar_match = re.search(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b|\b\d{12}\b', extracted_text)
        # PAN Card: 5 letters, 4 digits, 1 letter
        pan_match = re.search(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b', text_upper)
        # Passport: Letter + 7 digits
        passport_match = re.search(r'\b[A-Z][0-9]{7}\b', text_upper)
        # Driving License: SS-YYYY-NNNNNNN or similar (alphanumeric sequences 10-16 chars)
        dl_match = re.search(r'\b[A-Z]{2}[-|\s]?[0-9]{2}[-|\s]?[0-9]{11}\b|\b[A-Z]{2}[0-9]{13,15}\b', text_upper)

        if passport_match:
            details['document_number'] = passport_match.group(0)
            details['document_type'] = 'PASSPORT'
        elif aadhaar_match:
            details['document_number'] = aadhaar_match.group(0).replace(" ", "").replace("-", "")
            details['document_type'] = 'NATIONAL_ID'
        elif pan_match:
            details['document_number'] = pan_match.group(0)
            details['document_type'] = 'NATIONAL_ID'
        elif dl_match:
            details['document_number'] = dl_match.group(0)
            details['document_type'] = 'DRIVING_LICENCE'

        # 3. Name Extraction
        # Strategy A: Look for "Name:" or "NAME:" or "नाम" label
        name_match = re.search(r'(?:Name|NAME|नाम|Nom|NOM)\s*[:|-]?\s*([A-Za-z\s]+)', extracted_text)
        
        # Strategy B: If Aadhaar card, look for the line preceding "DOB" or "Year of Birth" or "जन्म तिथि"
        dob_line_idx = -1
        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]
        for idx, line in enumerate(lines):
            if any(x in line.upper() for x in ['DOB', 'DATE OF BIRTH', 'YEAR OF BIRTH', 'जन्म तिथि', 'FATHER', 'S/O', 'D/O', 'W/O', 'C/O']):
                dob_line_idx = idx
                break

        if name_match:
            name_parts = name_match.group(1).strip().split('\n')[0].strip().split()
            if len(name_parts) > 0:
                details['first_name'] = name_parts[0]
                if len(name_parts) > 1:
                    details['last_name'] = " ".join(name_parts[1:])
        elif dob_line_idx > 0:
            # Pick the line directly preceding the DOB line
            candidate = lines[dob_line_idx - 1]
            candidate_clean = re.sub(r'[^A-Za-z\s]', '', candidate).strip()
            words = [w for w in candidate_clean.split() if w.lower() not in ['name', 'holder', 'government', 'india']]
            if len(words) >= 2:
                details['first_name'] = words[0]
                details['last_name'] = " ".join(words[1:])
        
        # Strategy C: Look after "To" or "To,"
        if not details['first_name']:
            to_match = re.search(r'(?:To|TO|To,)\s*\n\s*([A-Za-z\s]+)', extracted_text)
            if to_match:
                name_parts = to_match.group(1).strip().split('\n')[0].strip().split()
                if len(name_parts) > 0:
                    details['first_name'] = name_parts[0]
                    if len(name_parts) > 1:
                        details['last_name'] = " ".join(name_parts[1:])

        # Strategy D: Fallback to the first line containing 2-3 capitalized words that are not headers
        if not details['first_name']:
            for line in lines[:5]:
                if any(x in line.upper() for x in ['GOVERNMENT', 'INDIA', 'AUTHORITY', 'UNIQUE', 'INCOME', 'TAX', 'REPUBLIC']):
                    continue
                words = [w for w in line.split() if w.istitle() or w.isupper()]
                if 2 <= len(words) <= 4:
                    details['first_name'] = words[0]
                    details['last_name'] = " ".join(words[1:])
                    break

        if not details['first_name']:
            details['first_name'] = "Extracted"
            details['last_name'] = "Guest"

        # 4. Email Extraction
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', extracted_text)
        details['email'] = email_match.group(0) if email_match else ''

        # 5. Phone Extraction
        phone_match = re.search(r'(?:Mobile|Phone|Mob|Ph|Mobile No|Mobile:)\s*[:|-]?\s*([+0-9\s-]{10,15})', extracted_text, re.IGNORECASE)
        if phone_match:
            details['phone'] = re.sub(r'[^\d+]', '', phone_match.group(1).strip())
        else:
            # Fallback to any 10-digit number starting with 6-9
            raw_phone = re.search(r'\b(?:[+]91|91)?[6-9]\d{9}\b', extracted_text)
            if raw_phone:
                details['phone'] = raw_phone.group(0)
            else:
                details['phone'] = ''

        # 6. Address Extraction
        # Try matching starting with "Address:" up to a 6 digit pin
        addr_match = re.search(r'(?:Address|ADDRESS|Add|ADD)\s*[:|-]\s*(.*?)(?=\b\d{6}\b)', extracted_text, re.DOTALL | re.IGNORECASE)
        if addr_match:
            addr_text = addr_match.group(1).strip()
            # Append pin if found
            pin_match = re.search(r'\b\d{6}\b', extracted_text)
            if pin_match:
                addr_text += " - " + pin_match.group(0)
            # Remove any "Details on:" or "Details on" or metadata labels
            addr_text = re.sub(r'Details\s+on\s*:\s*\d{2}/\d{2}/\d{4}', '', addr_text, flags=re.IGNORECASE)
            # Clean up leading/trailing symbols, e.g. from table layout
            addr_text = re.sub(r'^[:\-\s,|]+|[:\-\s,|]+$', '', addr_text)
            details['address'] = re.sub(r'\s+', ' ', addr_text).strip()
        else:
            # Fallback search: find pin code and look backwards for lines that look like address
            pin_match = re.search(r'\b\d{6}\b', extracted_text)
            if pin_match:
                pin_idx = extracted_text.find(pin_match.group(0))
                # Look at the previous 250 characters
                pre_text = extracted_text[max(0, pin_idx-250):pin_idx].strip()
                # Split by lines and take lines that have structure
                addr_lines = [l.strip() for l in pre_text.split('\n') if l.strip()]
                # Keep last 4 lines
                addr_lines = addr_lines[-4:] if len(addr_lines) > 4 else addr_lines
                if addr_lines:
                    details['address'] = ", ".join(addr_lines) + " - " + pin_match.group(0)
            else:
                details['address'] = ''

        return Response(details, status=status.HTTP_200_OK)


class GuestContactViewSet(viewsets.ModelViewSet):
    serializer_class = GuestContactSerializer
    permission_classes = [HasGuestPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestContact.objects.none()
        return GuestContact.objects.filter(tenant=tenant)


class GuestDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = GuestDocumentSerializer
    permission_classes = [HasGuestPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestDocument.objects.none()
        return GuestDocument.objects.filter(tenant=tenant)

    @action(detail=False, methods=['post'], url_path='upload', parser_classes=[MultiPartParser, FormParser])
    def upload(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)
            
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided.'}, status=status.HTTP_400_BAD_REQUEST)
            
        import os
        from django.conf import settings
        from django.core.files.storage import default_storage
        
        # Ensure media directory exists
        media_dir = os.path.join(settings.MEDIA_ROOT, 'guest_documents')
        if not os.path.exists(media_dir):
            os.makedirs(media_dir, exist_ok=True)
            
        # Save file
        file_name = default_storage.save(f"guest_documents/{file_obj.name}", file_obj)
        file_url = default_storage.url(file_name)
        
        return Response({'url': file_url}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='verify', permission_classes=[IsVerifyDocumentManager])
    def verify(self, request, pk=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        doc = self.get_object()
        verified_doc = DocumentVerificationService.verify_document(tenant, doc, user=request.user)
        serializer = self.get_serializer(verified_doc)
        return Response(serializer.data, status=status.HTTP_200_OK)


class GuestPreferenceViewSet(viewsets.ModelViewSet):
    serializer_class = GuestPreferenceSerializer
    permission_classes = [HasGuestPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestPreference.objects.none()
        return GuestPreference.objects.filter(tenant=tenant)


class GuestTagViewSet(viewsets.ModelViewSet):
    serializer_class = GuestTagSerializer
    permission_classes = [IsTagManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestTag.objects.filter(tenant__isnull=True)
        return GuestTag.objects.filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class GuestProfileTagViewSet(viewsets.ModelViewSet):
    serializer_class = GuestProfileTagSerializer
    permission_classes = [IsTagManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestProfileTag.objects.none()
        return GuestProfileTag.objects.filter(guest__tenant=tenant)


class GuestActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GuestActivitySerializer
    permission_classes = [HasGuestPermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return GuestActivity.objects.none()
        return GuestActivity.objects.filter(tenant=tenant).order_by('-timestamp')
