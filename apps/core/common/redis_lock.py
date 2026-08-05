import time
import logging
import uuid
from contextlib import contextmanager
from django.core.cache import cache

logger = logging.getLogger(__name__)

@contextmanager
def redis_distributed_lock(lock_key, timeout=15, retry_delay=0.1, max_retries=10):
    """
    A distributed lock context manager using Django's cache framework (Redis).
    Ensures safe concurrent operations for critical resources (e.g. room assignments).
    If Redis fails, it gracefully falls back (yielding acquired=False), letting DB transactions handle it.
    """
    acquired = False
    lock_value = str(uuid.uuid4())

    try:
        cache.set("pms:ping", "pong", timeout=1)
        if cache.get("pms:ping") == "pong":
            retries = 0
            while retries < max_retries:
                if cache.add(lock_key, lock_value, timeout):
                    acquired = True
                    break
                time.sleep(retry_delay)
                retries += 1
        else:
            logger.warning("Cache is unresponsive. Falling back to DB-level safety.")
    except Exception as e:
        logger.warning(f"Cache check/lock acquisition issue: {e}. Falling back to DB-level safety.")

    try:
        yield acquired
    finally:
        if acquired:
            try:
                if cache.get(lock_key) == lock_value:
                    cache.delete(lock_key)
            except Exception as e:
                logger.warning(f"Failed to release Redis lock for key {lock_key}: {e}")
