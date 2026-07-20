from rest_framework import serializers
from apps.features.lost_found.models import LostFoundItem
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

@extend_schema_field(OpenApiTypes.BINARY)
class FlexibleFileField(serializers.FileField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            if data.strip().lower() in ['', 'null', 'none']:
                return None
            return data
        return super().to_internal_value(data)

class LostFoundItemSerializer(serializers.ModelSerializer):
    reported_by_name = serializers.CharField(source='reported_by.name', read_only=True)
    image = FlexibleFileField(required=False, allow_null=True)

    class Meta:
        model = LostFoundItem
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'reference_number', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Handle image field to return its name/url properly
        image_field = instance.image
        if image_field:
            name = image_field.name
            if name.startswith('http://') or name.startswith('https://') or name.startswith('//'):
                ret['image'] = name
            else:
                # If there's a request context, use build_absolute_uri
                request = self.context.get('request')
                if request:
                    ret['image'] = request.build_absolute_uri(image_field.url)
                else:
                    ret['image'] = image_field.url
        else:
            ret['image'] = None
        return ret

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        validated_data['tenant'] = tenant
        validated_data['created_by'] = user
        return super().create(validated_data)
