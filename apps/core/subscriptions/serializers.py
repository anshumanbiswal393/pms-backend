from rest_framework import serializers
from apps.core.subscriptions.models import (
    Product, SubscriptionPlan, SubscriptionPlanProduct, SubscriptionEntitlement, TenantSubscription,
    TenantSubscriptionFeature, ProductFeature, TenantProduct, TenantProductLicense, TenantProductEntitlement, TenantProductUsage
)

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class SubscriptionEntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionEntitlement
        fields = '__all__'


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    entitlements = SubscriptionEntitlementSerializer(many=True, read_only=True)
    products = ProductSerializer(many=True, read_only=True)
    product_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False,
        help_text="List of Product UUIDs to link to this plan"
    )
    feature_codes = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False,
        help_text="List of Feature codes included in this plan"
    )

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'billing_cycle', 'price', 'currency', 'is_active', 'products', 'product_ids', 'entitlements', 'feature_codes']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['feature_codes'] = list(instance.entitlements.filter(limit_type='BOOLEAN', limit_value=True).values_list('feature_code', flat=True))
        return ret

    def create(self, validated_data):
        product_ids = validated_data.pop('product_ids', [])
        feature_codes = validated_data.pop('feature_codes', [])
        plan = SubscriptionPlan.objects.create(**validated_data)
        for prod_id in product_ids:
            try:
                prod = Product.objects.get(id=prod_id)
                SubscriptionPlanProduct.objects.create(plan=plan, product=prod)
            except Product.DoesNotExist:
                pass
        
        for code in feature_codes:
            SubscriptionEntitlement.objects.create(
                plan=plan,
                feature_code=code,
                limit_type='BOOLEAN',
                limit_value=True
            )
        return plan

    def update(self, instance, validated_data):
        product_ids = validated_data.pop('product_ids', None)
        feature_codes = validated_data.pop('feature_codes', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if product_ids is not None:
            SubscriptionPlanProduct.objects.filter(plan=instance).delete()
            for prod_id in product_ids:
                try:
                    prod = Product.objects.get(id=prod_id)
                    SubscriptionPlanProduct.objects.create(plan=instance, product=prod)
                except Product.DoesNotExist:
                    pass
                    
        if feature_codes is not None:
            SubscriptionEntitlement.objects.filter(plan=instance, limit_type='BOOLEAN').delete()
            for code in feature_codes:
                SubscriptionEntitlement.objects.create(
                    plan=instance,
                    feature_code=code,
                    limit_type='BOOLEAN',
                    limit_value=True
                )
        return instance


class TenantSubscriptionFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source='product_feature.name', read_only=True)
    product_name = serializers.CharField(source='product_feature.product.name', read_only=True)

    class Meta:
        model = TenantSubscriptionFeature
        fields = '__all__'


class TenantSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    features = TenantSubscriptionFeatureSerializer(many=True, read_only=True)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    class Meta:
        model = TenantSubscription
        fields = [
            'id', 'tenant', 'plan', 'plan_name', 'is_custom', 'custom_name',
            'billing_cycle', 'price', 'currency', 'start_date', 'end_date', 'status', 'features'
        ]
        read_only_fields = ['tenant']


class SubscriptionActionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField(required=True)


class ProductFeatureSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source='product.code', read_only=True)

    class Meta:
        model = ProductFeature
        fields = '__all__'


class TenantProductSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source='product.code', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = TenantProduct
        fields = '__all__'


class TenantProductLicenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantProductLicense
        fields = '__all__'


class TenantProductEntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantProductEntitlement
        fields = '__all__'


class TenantProductUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantProductUsage
        fields = '__all__'


class SuperadminTenantSubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(source='plan.name', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    features = TenantSubscriptionFeatureSerializer(many=True, read_only=True)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    class Meta:
        model = TenantSubscription
        fields = [
            'id', 'tenant', 'tenant_name', 'plan', 'plan_name', 'is_custom', 'custom_name',
            'billing_cycle', 'price', 'currency', 'start_date', 'end_date', 'status', 'features'
        ]


