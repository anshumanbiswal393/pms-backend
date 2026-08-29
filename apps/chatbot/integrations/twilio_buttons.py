import logging
import os
import json
from twilio.rest import Client

logger = logging.getLogger(__name__)

# Singleton Twilio client — reuses TCP connections across all button dispatches
_twilio_client = None

def _get_twilio_client():
    """Returns a cached Twilio Client instance (singleton). Creates one on first call."""
    global _twilio_client
    if _twilio_client is None:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip().strip('"').strip("'")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip().strip('"').strip("'")
        if account_sid and auth_token:
            _twilio_client = Client(account_sid, auth_token)
        else:
            logger.warning("Twilio credentials missing (TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN not set).")
            return None
    return _twilio_client

def send_native_whatsapp_buttons(to_number: str, profile_name: str = "Staff Member"):
    """
    Sends native WhatsApp GUI Buttons using Twilio Content Template SID.
    """
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")
    content_sid = os.getenv("TWILIO_CONTENT_SID", "").strip().strip('"').strip("'")

    if not from_number:
        logger.warning("TWILIO_WHATSAPP_FROM is empty, cannot send buttons.")
        return False

    if not content_sid:
        logger.warning("TWILIO_CONTENT_SID is empty, sending text menu instead of buttons.")
        return False

    client = _get_twilio_client()
    if not client:
        return False

    try:
        msg_params = {
            "from_": from_number,
            "to": to_number,
            "content_sid": content_sid,
            "content_variables": json.dumps({"1": profile_name}),
        }
        logger.info("Sending native WhatsApp buttons to %s", to_number)
        message = client.messages.create(**msg_params)
        logger.info("Native WhatsApp GUI buttons sent to %s. SID: %s", to_number, message.sid)
        return True
    except Exception as e:
        logger.error("Error sending native WhatsApp buttons via Twilio Content API: %s: %s", type(e).__name__, e)
        return False

def send_sub_category_buttons(to_number: str, category_key: str, profile_name: str = "Staff Member") -> bool:
    """
    Sends sub-category native WhatsApp GUI Buttons using the specific Content Template SID.
    category_key can be: 'frontdesk', 'analytics', 'operations', 'security'
    """
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")

    env_map = {
        "frontdesk": "TWILIO_CONTENT_SID_FRONTDESK",
        "analytics": "TWILIO_CONTENT_SID_ANALYTICS",
        "operations": "TWILIO_CONTENT_SID_OPERATIONS",
        "security": "TWILIO_CONTENT_SID_SECURITY",
    }

    env_var_name = env_map.get(category_key.lower(), "")
    content_sid = os.getenv(env_var_name, "").strip().strip('"').strip("'")

    if not from_number or not content_sid:
        logger.warning("Sub-category button config missing for '%s' (SID var: %s='%s')", category_key, env_var_name, content_sid)
        return False

    client = _get_twilio_client()
    if not client:
        return False

    try:
        msg_params = {
            "from_": from_number,
            "to": to_number,
            "content_sid": content_sid,
        }
        # Include content variables if template uses them, otherwise safely send
        try:
            msg_params["content_variables"] = json.dumps({"1": profile_name})
            message = client.messages.create(**msg_params)
        except Exception:
            # Fallback without content_variables if template has no parameters
            del msg_params["content_variables"]
            message = client.messages.create(**msg_params)

        logger.info("Sub-category WhatsApp GUI buttons ('%s') sent to %s. SID: %s", category_key, to_number, message.sid)
        return True
    except Exception as e:
        logger.error("Error sending sub-category buttons for '%s': %s: %s", category_key, type(e).__name__, e)
        return False

def get_whatsapp_main_menu(profile_name: str) -> str:
    """
    Fallback menu formatting for WhatsApp messaging.
    """
    return (
        f"\ud83d\udc4b Hi *{profile_name}*! Welcome to *Retrod PMS Assistant*.\n\n"
        "Reply with a category number or tap an action:\n\n"
        "1\ufe0f\u20e3 \ud83d\udd11 *Front Desk & Bookings*\n"
        "2\ufe0f\u20e3 \ud83d\udcca *Analytics & Reports*\n"
        "3\ufe0f\u20e3 \ud83d\udd27 *Operations & Housekeeping*\n"
        "4\ufe0f\u20e3 \ud83d\udee1\ufe0f *System Health & Security*\n\n"
        "\ud83d\udca1 _Or ask me any question about PMS workflows, policies, or page links!_"
    )
