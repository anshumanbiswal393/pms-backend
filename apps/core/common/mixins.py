import json
import hashlib
from django.core.cache import cache
from rest_framework.response import Response

class RedisCacheMixin:
    """
    Mixin for DRF ViewSets that caches list and retrieve responses in Redis.
    Invalidates the cache on create, update, and destroy operations.
    Cache keys are partitioned by tenant_id.
    """
    cache_timeout = 60 * 60  # Default 1 hour

    def _get_cache_prefix(self):
        tenant = getattr(self.request, 'tenant', None)
        tenant_id = str(tenant.id) if tenant else 'global'
        # Base cache prefix e.g., 'inventoryunit_tenantUUID'
        return f"{self.basename}_{tenant_id}"

    def _get_list_cache_key(self):
        # Hash the query params to support filtering/pagination
        query_string = self.request.META.get('QUERY_STRING', '')
        qs_hash = hashlib.md5(query_string.encode('utf-8')).hexdigest()
        return f"{self._get_cache_prefix()}_list_{qs_hash}"

    def _get_detail_cache_key(self, pk):
        return f"{self._get_cache_prefix()}_detail_{pk}"

    def _invalidate_cache(self):
        # We store all keys associated with this prefix in a set in Redis
        # so we can easily invalidate them all on write.
        prefix = self._get_cache_prefix()
        keys_set_name = f"{prefix}_keys"
        
        # Get all cached keys for this viewset/tenant
        keys = cache.get(keys_set_name, set())
        if keys:
            cache.delete_many(list(keys))
        cache.delete(keys_set_name)

    def _track_cache_key(self, key):
        prefix = self._get_cache_prefix()
        keys_set_name = f"{prefix}_keys"
        keys = cache.get(keys_set_name, set())
        keys.add(key)
        cache.set(keys_set_name, keys, self.cache_timeout)

    def list(self, request, *args, **kwargs):
        cache_key = self._get_list_cache_key()
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, self.cache_timeout)
            self._track_cache_key(cache_key)
        return response

    def retrieve(self, request, *args, **kwargs):
        cache_key = self._get_detail_cache_key(kwargs.get('pk'))
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, self.cache_timeout)
            self._track_cache_key(cache_key)
        return response

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        self._invalidate_cache()
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        self._invalidate_cache()
        return response

    def partial_update(self, request, *args, **kwargs):
        response = super().partial_update(request, *args, **kwargs)
        self._invalidate_cache()
        return response

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)
        self._invalidate_cache()
        return response
