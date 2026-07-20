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

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        def get_doc_url(field_file, default_url):
            if not field_file:
                return None
            name = field_file.name
            # If the database value is an absolute URL, return it directly
            if name.startswith('http://') or name.startswith('https://') or name.startswith('//'):
                return name
            return default_url

        # Nest the document fields in a 'documents' object as expected by the frontend
        ret['documents'] = {
            'incorporation': get_doc_url(instance.incorporation_document, ret.pop('incorporation', None)),
            'ownerId': get_doc_url(instance.owner_id_document, ret.pop('ownerId', None)),
            'cheque': get_doc_url(instance.cheque_document, ret.pop('cheque', None))
        }
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


