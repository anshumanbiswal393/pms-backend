from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils.dateparse import parse_date
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from datetime import datetime, date, timedelta

from apps.features.rates.models import (
    MealPlan, CancellationPolicy, ChildPolicy, RatePlan,
    RatePlanInventoryType, RatePlanVersion, DerivedRateConfig,
    RateRuleOccupancy, RateRuleDayOfWeek, RateCalendar,
    TenantMealPlanPrice, HospitalityPackage, ServiceCategory, Service, Coupon
)
from apps.features.rates.serializers import (
    MealPlanSerializer, CancellationPolicySerializer, ChildPolicySerializer,
    RatePlanSerializer, RatePlanInventoryTypeSerializer, RatePlanVersionSerializer,
    DerivedRateConfigSerializer, RateRuleOccupancySerializer, RateRuleDayOfWeekSerializer,
    RateCalendarSerializer, TenantMealPlanPriceSerializer,
    HospitalityPackageSerializer, RebuildCalendarSerializer, ServiceCategorySerializer, ServiceSerializer, CouponSerializer
)
from apps.features.rates.permissions import (
    HasRatePermission, IsRateCalendarManager, IsPolicyManager, IsPackageManager
)
from apps.features.rates.services import RateCalendarService, RatePlanService

class TenantMealPlanPriceViewSet(viewsets.ModelViewSet):
    serializer_class = TenantMealPlanPriceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantMealPlanPrice.objects.none()
        return TenantMealPlanPrice.objects.filter(tenant=tenant)


class MealPlanViewSet(viewsets.ModelViewSet):
    serializer_class = MealPlanSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsPolicyManager()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return MealPlan.objects.filter(tenant__isnull=True)
        return MealPlan.objects.filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class CancellationPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = CancellationPolicySerializer
    permission_classes = [IsPolicyManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return CancellationPolicy.objects.none()
        return CancellationPolicy.objects.filter(tenant=tenant)


class ChildPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = ChildPolicySerializer
    permission_classes = [IsPolicyManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return ChildPolicy.objects.none()
        return ChildPolicy.objects.filter(tenant=tenant)


class RatePlanViewSet(viewsets.ModelViewSet):
    serializer_class = RatePlanSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [HasRatePermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return RatePlan.objects.none()
        qs = RatePlan.objects.filter(tenant=tenant)
        property_id = self.request.query_params.get('property_id')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    def perform_create(self, serializer):
        rate_plan = serializer.save(tenant=self.request.tenant)
        # Automatically generate version snapshot when created
        RatePlanService.create_version_snapshot(rate_plan)


class RatePlanInventoryTypeViewSet(viewsets.ModelViewSet):
    serializer_class = RatePlanInventoryTypeSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [HasRatePermission()]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return RatePlanInventoryType.objects.none()
        return RatePlanInventoryType.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)


class RatePlanVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RatePlanVersionSerializer
    permission_classes = [HasRatePermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return RatePlanVersion.objects.none()
        rate_plan_id = self.request.query_params.get('rate_plan_id')
        qs = RatePlanVersion.objects.filter(rate_plan__tenant=tenant)
        if rate_plan_id:
            qs = qs.filter(rate_plan_id=rate_plan_id)
        return qs


class DerivedRateConfigViewSet(viewsets.ModelViewSet):
    serializer_class = DerivedRateConfigSerializer
    permission_classes = [HasRatePermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return DerivedRateConfig.objects.none()
        return DerivedRateConfig.objects.filter(tenant=tenant)


class RateRuleOccupancyViewSet(viewsets.ModelViewSet):
    serializer_class = RateRuleOccupancySerializer
    permission_classes = [HasRatePermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return RateRuleOccupancy.objects.none()
        return RateRuleOccupancy.objects.filter(tenant=tenant)


class RateRuleDayOfWeekViewSet(viewsets.ModelViewSet):
    serializer_class = RateRuleDayOfWeekSerializer
    permission_classes = [HasRatePermission]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return RateRuleDayOfWeek.objects.none()
        return RateRuleDayOfWeek.objects.filter(tenant=tenant)


class RateCalendarViewSet(viewsets.ModelViewSet):
    serializer_class = RateCalendarSerializer
    permission_classes = [IsRateCalendarManager]

    def get_queryset(self):
        property_id = self.request.query_params.get('property_id')
        qs = RateCalendar.objects.select_related('rate_plan', 'inventory_unit_type')
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    @extend_schema(request=RebuildCalendarSerializer)
    @action(detail=False, methods=['post'], url_path='rebuild')
    def rebuild(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = RebuildCalendarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        property_id = serializer.validated_data['property_id']
        start_date = serializer.validated_data['start_date']
        end_date = serializer.validated_data['end_date']

        count = RateCalendarService.rebuild_calendar(
            tenant=tenant,
            property_id=property_id,
            start_date=start_date,
            end_date=end_date
        )

        return Response({
            'status': 'success',
            'rebuilt_records': count
        }, status=status.HTTP_200_OK)

    @extend_schema(
        parameters=[
            OpenApiParameter('start_date', OpenApiTypes.DATE, required=False, description='Start date Filter'),
            OpenApiParameter('end_date', OpenApiTypes.DATE, required=False, description='End date Filter'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='property/(?P<property_id>[^/.]+)')
    def property_calendar(self, request, property_id=None):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        # Cache key generation based on Flipkart-like Redis caching
        from django.core.cache import cache
        cache_key = f"ratecalendar_tenant_{tenant.id}_prop_{property_id}_{start_date_str}_{end_date_str}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        qs = RateCalendar.objects.filter(property_id=property_id).select_related(
            'rate_plan', 'inventory_unit_type'
        )
        
        if start_date_str:
            start_date = parse_date(start_date_str)
            if start_date:
                qs = qs.filter(date__gte=start_date)

        if end_date_str:
            end_date = parse_date(end_date_str)
            if end_date:
                qs = qs.filter(date__lte=end_date)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            data = self.get_paginated_response(serializer.data).data
        else:
            serializer = self.get_serializer(qs, many=True)
            data = serializer.data

        # Save to Redis before returning
        cache.set(cache_key, data, 60 * 15)  # Cache for 15 minutes
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-update-rates')
    def bulk_update_rates(self, request):
        """
        Bulk update base_rate for a room type across a date range.
        Updates RatePlanInventoryType.base_rate (source of truth), then
        triggers a calendar rebuild for the given date range.

        Body:
          property_id: UUID (required)
          inventory_unit_type_id: UUID | "all" (required)
          start_date: YYYY-MM-DD (required)
          end_date: YYYY-MM-DD (required)
          new_rate: decimal (required)
        """
        from django.db import transaction
        from decimal import Decimal

        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({'error': 'Tenant context missing.'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        property_id = data.get('property_id')
        unit_type_id = data.get('inventory_unit_type_id')  # UUID or "all"
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        new_rate = data.get('new_rate')

        if not all([property_id, start_date_str, end_date_str, new_rate]):
            return Response(
                {'error': 'property_id, start_date, end_date, and new_rate are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        if not start_date or not end_date or start_date > end_date:
            return Response({'error': 'Invalid date range.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_rate_decimal = Decimal(str(new_rate))
        except Exception:
            return Response({'error': 'Invalid rate value.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Find all active rate plans for the property
            rate_plans = RatePlan.objects.filter(
                property_id=property_id,
                is_active=True,
                tenant=tenant,
                # inventory_unit_type__is_sellable=True,
            )
            # Find target room types (sellable only if 'all')
            from apps.features.inventory.models import InventoryUnitType
            ut_qs = InventoryUnitType.objects.filter(property_id=property_id, tenant=tenant)
            if unit_type_id and unit_type_id != 'all':
                ut_qs = ut_qs.filter(id=unit_type_id)
            else:
                ut_qs = ut_qs.filter(is_sellable=True)

            # Direct RateCalendar update/create for each date, plan, and room type
            updated_count = 0
            curr_date = start_date
            while curr_date <= end_date:
                for rp in rate_plans:
                    for ut in ut_qs:
                        RateCalendar.objects.update_or_create(
                            property_id=property_id,
                            date=curr_date,
                            rate_plan=rp,
                            inventory_unit_type=ut,
                            defaults={'amount': new_rate_decimal}
                        )
                        updated_count += 1
                curr_date += timedelta(days=1)

            # Invalidate Redis Cache (Flipkart-style optimization cleanup)
            from django.core.cache import cache
            cache.delete_pattern(f"ratecalendar_tenant_{tenant.id}_prop_{property_id}_*") if hasattr(cache, 'delete_pattern') else cache.clear()

        return Response({
            'status': 'success',
            'rate_plans_updated': updated_count,
            'calendar_records_rebuilt': updated_count,
            'date_range': {'start': start_date_str, 'end': end_date_str},
        }, status=status.HTTP_200_OK)


class HospitalityPackageViewSet(viewsets.ModelViewSet):
    serializer_class = HospitalityPackageSerializer
    permission_classes = [IsPackageManager]
    filterset_fields = ['status']
    search_fields = ['name', 'inclusions']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return HospitalityPackage.objects.none()
        return HospitalityPackage.objects.filter(tenant=tenant)

class ServiceCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsPackageManager]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return ServiceCategory.objects.none()
        return ServiceCategory.objects.filter(tenant=tenant)

class ServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ServiceSerializer
    permission_classes = [IsPackageManager]
    filterset_fields = ['category', 'status']
    search_fields = ['name']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Service.objects.none()
        return Service.objects.filter(tenant=tenant)

class CouponViewSet(viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Coupon.objects.none()
        return Coupon.objects.filter(tenant=tenant)
