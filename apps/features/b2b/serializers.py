from rest_framework import serializers
from apps.features.b2b.models import B2BPartner
import json
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

@extend_schema_field(OpenApiTypes.BINARY)
class FlexibleFileField(serializers.FileField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            # Treat empty, "null", or "none" strings as None/empty value
            if data.strip().lower() in ['', 'null', 'none']:
                return None
            return data
        return super().to_internal_value(data)

class B2BPartnerSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='agent_id', read_only=True)
    contact = serializers.CharField(source='contact_person', required=False, allow_blank=True)
    commission = serializers.IntegerField(source='commission_rate', default=0, required=False)
    creditLimit = serializers.DecimalField(source='credit_limit', max_digits=12, decimal_places=2, default=0.00, required=False)
    
    # Use FlexibleFileField to support both file uploads and string filenames
    incorporation = FlexibleFileField(source='incorporation_document', required=False, allow_null=True)
    ownerId = FlexibleFileField(source='owner_id_document', required=False, allow_null=True)
    cheque = FlexibleFileField(source='cheque_document', required=False, allow_null=True)

    class Meta:
        model = B2BPartner
        fields = [
            'id', 'name', 'contact', 'email', 'phone', 'location',
            'status', 'commission', 'creditLimit', 'incorporation', 'ownerId', 'cheque',
            'created_at', 'updated_at'
        ]
        read_only_fields = ('created_at', 'updated_at')

    def validate_name(self, value):
        if not value:
            return value
        import re
        if re.search(r'[@!#$%^*+=<>{}[\]~`]', value):
            raise serializers.ValidationError("Agency name contains invalid characters (@, !, #, $, %, etc.).")
        return value.strip()

    def validate_contact(self, value):
        if not value:
            return value
        import re
        if not re.match(r"^[a-zA-Z\s.'-]+$", value.strip()):
            raise serializers.ValidationError("Contact person name must contain only letters and spaces (no numbers or special characters like Saurav12@).")
        return value.strip()

    def validate_location(self, value):
        if not value:
            return value
        import re
        if not re.match(r"^[a-zA-Z\s,.-]+$", value.strip()):
            raise serializers.ValidationError("Location must contain only letters, spaces, commas, and dots (no numbers or special characters like Delhi123@).")
        return value.strip()

    def validate_phone(self, value):
        if not value:
            return value
        import re
        digits = re.sub(r'\D', '', str(value))
        if len(digits) == 12 and digits.startswith('91'):
            digits = digits[2:]
        if len(digits) != 10:
            raise serializers.ValidationError("Phone number must be exactly 10 digits.")
    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        request = self.context.get('request')

        def get_doc_url(field_file):
            if not field_file:
                return None
            
            raw_url = ""
            if hasattr(field_file, 'url'):
                try:
                    raw_url = field_file.url
                except Exception:
                    pass
            if not raw_url:
                name = str(field_file.name if hasattr(field_file, 'name') else field_file)
                raw_url = name

            if not raw_url or raw_url.strip().lower() in ['none', 'null', '']:
                return None

            # External cloud storage URL (S3, Cloudinary, etc.)
            if raw_url.startswith('http://') or raw_url.startswith('https://') or raw_url.startswith('//'):
                if 'retrod' not in raw_url and 'localhost' not in raw_url and '127.0.0.1' not in raw_url:
                    return raw_url
                from urllib.parse import urlparse
                parsed = urlparse(raw_url)
                raw_url = parsed.path

            clean_path = raw_url.lstrip('/')
            if clean_path.startswith('api/media/'):
                clean_path = clean_path[len('api/media/'):]
            elif clean_path.startswith('media/'):
                clean_path = clean_path[len('media/'):]
            elif clean_path.startswith('api/'):
                clean_path = clean_path[len('api/'):]

            api_path = f"/api/media/{clean_path}"
            if request:
                return request.build_absolute_uri(api_path)
            return api_path

        # Nest the document fields in a 'documents' object as expected by the frontend
        ret['documents'] = {
            'incorporation': get_doc_url(instance.incorporation_document),
            'ownerId': get_doc_url(instance.owner_id_document),
            'cheque': get_doc_url(instance.cheque_document)
        }
        ret.pop('incorporation', None)
        ret.pop('ownerId', None)
        ret.pop('cheque', None)
        return ret

    def to_internal_value(self, data):
        # Extract files from 'documents' if sent as nested JSON or stringified dict in form-data
        if 'documents' in data:
            docs = data['documents']
            if isinstance(docs, str):
                try:
                    docs = json.loads(docs)
                except Exception:
                    docs = {}
            if isinstance(docs, dict):
                mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
                if 'incorporation' in docs and 'incorporation' not in mutable_data:
                    mutable_data['incorporation'] = docs['incorporation']
                if 'ownerId' in docs and 'ownerId' not in mutable_data:
                    mutable_data['ownerId'] = docs['ownerId']
                if 'cheque' in docs and 'cheque' not in mutable_data:
                    mutable_data['cheque'] = docs['cheque']
                data = mutable_data

        # Also parse bracket notations such as documents[incorporation] commonly used in form-data
        bracket_mappings = {
            'documents[incorporation]': 'incorporation',
            'documents[ownerId]': 'ownerId',
            'documents[cheque]': 'cheque'
        }
        has_brackets = any(k in data for k in bracket_mappings)
        if has_brackets:
            mutable_data = data.copy() if hasattr(data, 'copy') else dict(data)
            for bracket_key, flat_key in bracket_mappings.items():
                if bracket_key in data and flat_key not in mutable_data:
                    mutable_data[flat_key] = data[bracket_key]
            data = mutable_data

        return super().to_internal_value(data)


