import json
import logging
import hashlib
from typing import Optional, Tuple, Any
from django.core.cache import cache

logger = logging.getLogger(__name__)

class IdempotencyManager:
    """
    Enterprise Idempotency Manager.
    Ensures safe, duplicate-free operations for payments, reservations, and critical booking updates.
    
    Lifecycle:
    1. Check if key exists.
       - If status == 'PROCESSING': Returns conflict (in-progress lock).
       - If status == 'COMPLETED': Returns cached response data immediately.
    2. Start processing: Sets key to 'PROCESSING' with a short TTL (e.g. 60s).
    3. Complete processing: Saves the resulting response payload and status code with a 24h TTL.
    4. On unhandled failure: Clears the key so client can retry with corrected inputs.
    """
    
    KEY_PREFIX = "pms:idempotency"
    PROCESSING_TTL = 60       # 1 minute lock for in-flight requests
    COMPLETED_TTL = 86400     # 24 hours retention for completed responses

    @classmethod
    def _format_cache_key(cls, tenant_id: str, idempotency_key: str) -> str:
        clean_key = str(idempotency_key).strip()
        return f"{cls.KEY_PREFIX}:{tenant_id or 'global'}:{clean_key}"

    @classmethod
    def check_idempotency(cls, tenant_id: str, idempotency_key: str) -> Tuple[bool, Optional[int], Optional[Any]]:
        """
        Returns:
            (is_handled: bool, status_code: int, response_data: Any)
        If is_handled is True:
            - status_code 409 means still processing.
            - status_code 200/201 means completed previously; return response_data immediately.
        If is_handled is False:
            - Proceed with normal request execution.
        """
        if not idempotency_key:
            return False, None, None

        cache_key = cls._format_cache_key(tenant_id, idempotency_key)
        try:
            cached_entry = cache.get(cache_key)
            if not cached_entry:
                return False, None, None

            if isinstance(cached_entry, str):
                try:
                    cached_entry = json.loads(cached_entry)
                except Exception:
                    pass

            state = cached_entry.get("state")
            if state == "PROCESSING":
                return True, 409, {
                    "error": "A request with this Idempotency-Key is currently in progress. Please wait for completion.",
                    "idempotency_key": idempotency_key,
                    "status": "PROCESSING"
                }

            if state == "COMPLETED":
                logger.info(f"Idempotency hit for key={idempotency_key}. Returning cached response without re-executing.")
                return True, cached_entry.get("status_code", 200), cached_entry.get("data")

        except Exception as e:
            logger.warning(f"Error checking idempotency cache: {e}. Falling back to normal execution.")

        return False, None, None

    @classmethod
    def start_processing(cls, tenant_id: str, idempotency_key: str) -> bool:
        """
        Atomically acquires lock / marks key as PROCESSING.
        Returns True if acquired, False if already processing.
        """
        if not idempotency_key:
            return True

        cache_key = cls._format_cache_key(tenant_id, idempotency_key)
        payload = json.dumps({"state": "PROCESSING"})
        try:
            # cache.add only sets if the key does not already exist
            acquired = cache.add(cache_key, payload, timeout=cls.PROCESSING_TTL)
            if not acquired:
                # Key already exists
                existing = cache.get(cache_key)
                return False
            return True
        except Exception as e:
            logger.warning(f"Error starting idempotency for key {idempotency_key}: {e}")
            return True

    @classmethod
    def complete(cls, tenant_id: str, idempotency_key: str, response_data: Any, status_code: int = 201):
        """
        Marks idempotency key as COMPLETED and stores response payload.
        """
        if not idempotency_key:
            return

        cache_key = cls._format_cache_key(tenant_id, idempotency_key)
        payload = json.dumps({
            "state": "COMPLETED",
            "status_code": status_code,
            "data": response_data
        })
        try:
            cache.set(cache_key, payload, timeout=cls.COMPLETED_TTL)
        except Exception as e:
            logger.warning(f"Error saving completed idempotency for key {idempotency_key}: {e}")

    @classmethod
    def clear(cls, tenant_id: str, idempotency_key: str):
        """
        Clears idempotency lock on error so client can retry.
        """
        if not idempotency_key:
            return

        cache_key = cls._format_cache_key(tenant_id, idempotency_key)
        try:
            cache.delete(cache_key)
        except Exception as e:
            logger.warning(f"Error clearing idempotency key {idempotency_key}: {e}")

    @classmethod
    def extract_key(cls, request) -> Optional[str]:
        """
        Extracts idempotency key from headers or request payload.
        Supported headers: 'Idempotency-Key', 'X-Idempotency-Key'
        Supported body fields: 'idempotency_key', 'idempotencyKey'
        """
        key = (
            request.headers.get("Idempotency-Key") or
            request.headers.get("X-Idempotency-Key") or
            request.META.get("HTTP_IDEMPOTENCY_KEY") or
            request.META.get("HTTP_X_IDEMPOTENCY_KEY")
        )
        if key:
            return str(key).strip()

        if hasattr(request, "data") and isinstance(request.data, dict):
            body_key = request.data.get("idempotency_key") or request.data.get("idempotencyKey")
            if body_key:
                return str(body_key).strip()

        return None
