import json
import hashlib
from django.core.cache import cache
from rest_framework.response import Response

def invalidate_viewset_cache(basename: str, tenant_id: str = None):
    """
    Utility to invalidate all cached list and detail responses for a given basename and tenant.
    """
    prefix = f"{basename}_{tenant_id or 'global'}"
    keys_set_name = f"{prefix}_keys"
    try:
        keys = cache.get(keys_set_name, set())
        if keys:
            cache.delete_many(list(keys))
        cache.delete(keys_set_name)
    except Exception:
        pass

class RedisCacheMixin:
    """
    Mixin for DRF ViewSets that caches list and retrieve responses in Redis.
    Invalidates the cache on create, update, and destroy operations.
    Cache keys are partitioned by tenant_id, property_id, and query parameters.
    """
    cache_timeout = 60 * 60  # Default 1 hour

    def _get_cache_prefix(self):
        tenant = getattr(self.request, 'tenant', None)
        tenant_id = str(tenant.id) if tenant else 'global'
        basename = getattr(self, 'basename', self.__class__.__name__.lower())
        return f"{basename}_{tenant_id}"

    def _get_list_cache_key(self):
        # Hash the query params along with property_id and user context
        query_string = self.request.META.get('QUERY_STRING', '')
        property_id = self.request.headers.get('X-Property-ID') or (
            self.request.query_params.get('property_id') if hasattr(self.request, 'query_params') else ''
        ) or ''
        user = getattr(self.request, 'user', None)
        user_id = str(user.id) if user and getattr(user, 'is_authenticated', False) else 'anon'
        composite = f"{query_string}|prop={property_id}|user={user_id}"
        qs_hash = hashlib.md5(composite.encode('utf-8')).hexdigest()
        return f"{self._get_cache_prefix()}_list_{qs_hash}"

    def _get_detail_cache_key(self, pk):
        return f"{self._get_cache_prefix()}_detail_{pk}"

    def _invalidate_cache(self):
        # We store all keys associated with this prefix in a set in Redis
        # so we can easily invalidate them all on write.
        prefix = self._get_cache_prefix()
        keys_set_name = f"{prefix}_keys"
        try:
            keys = cache.get(keys_set_name, set())
            if keys:
                cache.delete_many(list(keys))
            cache.delete(keys_set_name)
        except Exception:
            pass

    def _track_cache_key(self, key):
        prefix = self._get_cache_prefix()
        keys_set_name = f"{prefix}_keys"
        try:
            keys = cache.get(keys_set_name)
            if not isinstance(keys, set):
                keys = set(keys) if isinstance(keys, (list, tuple)) else set()
            keys.add(key)
            cache.set(keys_set_name, keys, self.cache_timeout)
        except Exception:
            pass

    def list(self, request, *args, **kwargs):
        cache_key = self._get_list_cache_key()
        try:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)
        except Exception:
            pass

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
                self._track_cache_key(cache_key)
            except Exception:
                pass
        return response

    def retrieve(self, request, *args, **kwargs):
        cache_key = self._get_detail_cache_key(kwargs.get('pk'))
        try:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)
        except Exception:
            pass

        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
                self._track_cache_key(cache_key)
            except Exception:
                pass
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

