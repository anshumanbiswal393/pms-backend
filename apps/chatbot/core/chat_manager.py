import logging
import re
from apps.chatbot.core.session_manager import get_user_session, update_user_session
from apps.chatbot.core.staff_manager import process_staff_message, handle_staff_login_flow, handle_housekeeping_flow, handle_checkin_flow
from apps.chatbot.core.guest_manager import process_guest_message, handle_booking_flow


logger = logging.getLogger(__name__)

# Prompt injection sanitizer patterns
_PROMPT_INJECTION_RE = re.compile(
    r'(?i)(<system>|</system>|<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>|ignore previous instructions|forget previous instructions|override system prompt)',
    re.IGNORECASE
)

def sanitize_prompt(text: str) -> str:
    """Sanitizes user input string against prompt injection vectors."""
    if not text:
        return ""
    return _PROMPT_INJECTION_RE.sub('[redacted_prompt_injection]', text).strip()

def process_incoming_message(sender_id: str, message: str, profile_name: str, channel: str = "whatsapp") -> str:
    """
    Facade Entry Point for Backward Compatibility.
    Delegates to Staff Manager or Guest Manager based on active session mode.
    """
    message = sanitize_prompt(message)
    session = get_user_session(sender_id)
    is_authenticated = session.get("authenticated") is True
    active_mode = session.get("mode")

    lowered = message.lower().strip() if message else ""

    if lowered in ["/login", "login", "staff login"]:
        active_mode = "STAFF"
    elif lowered in ["guest", "guest mode", "guest_mode", "/guest"]:
        active_mode = "GUEST"
    elif is_authenticated or session.get("state", "").startswith("LOGIN_") or session.get("state", "").startswith("HK_") or session.get("state", "").startswith("CHECKIN_"):
        active_mode = "STAFF"

    if active_mode == "STAFF":
        return process_staff_message(sender_id, message, profile_name)
    else:
        return process_guest_message(sender_id, message, profile_name)

