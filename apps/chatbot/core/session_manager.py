import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

SESSION_TIMEOUT = 86400  # 24 hours

def get_user_session(sender_id: str) -> dict:
    """Retrieve raw session for a sender."""
    sess = cache.get(f"user_session:{sender_id}")
    if not isinstance(sess, dict):
        sess = {"state": "IDLE", "data": {}, "authenticated": False, "mode": None}
    return sess

def update_user_session(sender_id: str, new_state: str = None, **kwargs) -> dict:
    """Updates user session in Redis cache, preserving existing keys unless overwritten."""
    sess = get_user_session(sender_id)
    if new_state is not None:
        sess["state"] = new_state
    for k, v in kwargs.items():
        sess[k] = v
    cache.set(f"user_session:{sender_id}", sess, timeout=SESSION_TIMEOUT)
    return sess

def clear_user_session(sender_id: str):
    """Clears active session from cache."""
    try:
        cache.delete(f"user_session:{sender_id}")
    except Exception as e:
        logger.error(f"Error clearing session for {sender_id}: {e}")

def set_session_mode(sender_id: str, mode: str) -> dict:
    """Sets session role mode explicitly ('STAFF' or 'GUEST')."""
    return update_user_session(sender_id, mode=mode.upper())
