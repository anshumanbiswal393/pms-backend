from rest_framework import serializers
from apps.features.linen.models import LinenItem, LinenAssignment, LaundryRecord, GuestLaundryOrder, GuestLaundryOrderItem, LaundryMachine
from apps.features.inventory.models import InventoryUnit


class LinenItemSerializer(serializers.ModelSerializer):
    stock_status = serializers.CharField(source='get_stock_status', read_only=True)

    class Meta:
        model = LinenItem
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and tenant and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        if tenant:
            validated_data['tenant'] = tenant
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)


class LinenAssignmentSerializer(serializers.ModelSerializer):
    linen_item_name = serializers.CharField(source='linen_item.name', read_only=True)
    inventory_unit_name = serializers.CharField(source='inventory_unit.name', read_only=True)

    class Meta:
        model = LinenAssignment
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        linen_item = data.get('linen_item')
        if linen_item and tenant and linen_item.tenant != tenant:
            raise serializers.ValidationError("Linen item must belong to the resolved tenant context.")
            
        unit = data.get('inventory_unit')
        if unit and tenant and unit.tenant != tenant:
            raise serializers.ValidationError("Inventory unit must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        if tenant:
            validated_data['tenant'] = tenant
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)


class LaundryRecordSerializer(serializers.ModelSerializer):
    linen_item_name = serializers.CharField(source='linen_item.name', read_only=True)

    class Meta:
        model = LaundryRecord
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        
        prop = data.get('property')
        if prop and tenant and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
            
        linen_item = data.get('linen_item')
        if linen_item and tenant and linen_item.tenant != tenant:
            raise serializers.ValidationError("Linen item must belong to the resolved tenant context.")
            
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        if tenant:
            validated_data['tenant'] = tenant
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)


class GuestLaundryOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestLaundryOrderItem
        fields = '__all__'
        read_only_fields = ('id', 'order', 'total_price', 'created_at', 'updated_at', 'deleted_at')


class GuestLaundryOrderSerializer(serializers.ModelSerializer):
    items = GuestLaundryOrderItemSerializer(many=True, required=False)

    class Meta:
        model = GuestLaundryOrder
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'order_number', 'total_amount', 'is_posted_to_folio', 'posted_at', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and tenant and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        if tenant:
            validated_data['tenant'] = tenant
        if user and user.is_authenticated:
            validated_data['created_by'] = user

        order = super().create(validated_data)
        for item_data in items_data:
            GuestLaundryOrderItem.objects.create(order=order, **item_data)
        order.calculate_total()
        return order


class LaundryMachineSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaundryMachine
        fields = '__all__'
        read_only_fields = ('id', 'tenant', 'created_at', 'updated_at', 'created_by', 'updated_by', 'deleted_at')

    def validate(self, data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        prop = data.get('property')
        if prop and tenant and prop.tenant != tenant:
            raise serializers.ValidationError("Property must belong to the resolved tenant context.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        if tenant:
            validated_data['tenant'] = tenant
        if user and user.is_authenticated:
            validated_data['created_by'] = user
        return super().create(validated_data)
