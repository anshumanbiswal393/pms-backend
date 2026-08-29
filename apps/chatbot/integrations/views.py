import logging
import os
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from twilio.twiml.messaging_response import MessagingResponse
from django_ratelimit.decorators import ratelimit
from apps.chatbot.integrations.decorators import validate_twilio_signature
from apps.chatbot.integrations.tasks import send_whatsapp_async
from apps.chatbot.core.session_manager import get_user_session, update_user_session
from apps.chatbot.core.staff_manager import process_staff_message
from apps.chatbot.core.guest_manager import process_guest_message


logger = logging.getLogger(__name__)

def chatbot_info_view(request):
    """Informational endpoint for the AI Chatbot WhatsApp Integration."""
    return JsonResponse({
        "status": "healthy",
        "service": "Retrod AI Chatbot WhatsApp Integration",
        "product": "Product 3 (AI Chatbot)",
        "endpoints": {
            "unified_webhook": "/api/v1/integrations/whatsapp/webhook/",
            "staff_webhook": "/api/v1/integrations/whatsapp/staff/",
            "guest_webhook": "/api/v1/integrations/whatsapp/guest/",
        },
        "description": "Handles WhatsApp guest inquiries, staff operations, bookings, and RAG knowledge retrieval.",
        "request_method_note": "Twilio sends webhook events via HTTP POST."
    })

def _is_duplicate_message(message_sid: str) -> bool:
    """Checks and records MessageSid in Redis to prevent replay attacks and duplicate webhook executions."""
    if not message_sid:
        return False
    # cache.add returns True if key was set (i.e. first time seen), False if already exists
    was_set = cache.add(f"msg_sid:{message_sid}", "1", timeout=3600)
    return not was_set

@csrf_exempt
@ratelimit(key='post:From', rate='30/m', method='POST', block=True)
@validate_twilio_signature
def staff_whatsapp_webhook(request):
    """Dedicated Webhook Endpoint for Staff Twilio WhatsApp Number."""
    if request.method == "GET":
        return JsonResponse({
            "status": "active",
            "endpoint": "Staff WhatsApp Webhook",
            "usage": "Configure this URL as the webhook target for the Staff Twilio phone number (HTTP POST)."
        })
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)


    sender = request.POST.get("From", "")
    message_body = request.POST.get("Body", "").strip()
    profile_name = request.POST.get("ProfileName", "Staff Member")
    message_sid = request.POST.get("MessageSid", "").strip()

    logger.info("Incoming STAFF WhatsApp message from %s (%s): '%s' [SID=%s]", sender, profile_name, message_body, message_sid)

    if _is_duplicate_message(message_sid):
        logger.warning("Idempotency Guard: Suppressed duplicate MessageSid=%s from %s", message_sid, sender)
        resp = MessagingResponse()
        return HttpResponse(str(resp), content_type="application/xml", status=200)

    use_async = os.getenv("ASYNC_WEBHOOKS", "True").lower() in ("true", "1", "yes")
    if use_async:
        try:
            send_whatsapp_async.delay(sender, message_body, profile_name)
            resp = MessagingResponse()
            return HttpResponse(str(resp), content_type="application/xml", status=200)
        except Exception as e:
            logger.error("Celery dispatch error for staff webhook %s (SID=%s): %s. Executing synchronous fallback.", sender, message_sid, e, exc_info=True)

    try:
        reply_text = process_staff_message(sender, message_body, profile_name)
    except Exception as e:
        logger.error(f"Error in Staff Engine for {sender}: {e}", exc_info=True)
        reply_text = "⚠️ *Staff Assistant Service Delay*. Please reply `/login` to refresh your session."

    resp = MessagingResponse()
    resp.message(reply_text)
    return HttpResponse(str(resp), content_type="application/xml", status=200)

@csrf_exempt
@ratelimit(key='post:From', rate='30/m', method='POST', block=True)
@validate_twilio_signature
def guest_whatsapp_webhook(request):
    """Dedicated Webhook Endpoint for Guest Twilio WhatsApp Number."""
    if request.method == "GET":
        return JsonResponse({
            "status": "active",
            "endpoint": "Guest WhatsApp Webhook",
            "usage": "Configure this URL as the webhook target for the Guest Twilio phone number (HTTP POST)."
        })
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)

    sender = request.POST.get("From", "")
    message_body = request.POST.get("Body", "").strip()
    profile_name = request.POST.get("ProfileName", "Hotel Guest")
    message_sid = request.POST.get("MessageSid", "").strip()

    logger.info("Incoming GUEST WhatsApp message from %s (%s): '%s' [SID=%s]", sender, profile_name, message_body, message_sid)

    if _is_duplicate_message(message_sid):
        logger.warning("Idempotency Guard: Suppressed duplicate MessageSid=%s from %s", message_sid, sender)
        resp = MessagingResponse()
        return HttpResponse(str(resp), content_type="application/xml", status=200)

    use_async = os.getenv("ASYNC_WEBHOOKS", "True").lower() in ("true", "1", "yes")
    if use_async:
        try:
            send_whatsapp_async.delay(sender, message_body, profile_name)
            resp = MessagingResponse()
            return HttpResponse(str(resp), content_type="application/xml", status=200)
        except Exception as e:
            logger.error("Celery dispatch error for guest webhook %s (SID=%s): %s. Executing synchronous fallback.", sender, message_sid, e, exc_info=True)

    try:
        reply_text = process_guest_message(sender, message_body, profile_name)
    except Exception as e:
        logger.error(f"Error in Guest Engine for {sender}: {e}", exc_info=True)
        reply_text = "👋 *Retrod Guest Assistant*: Welcome! How can we assist you with your booking today?"

    resp = MessagingResponse()
    resp.message(reply_text)
    return HttpResponse(str(resp), content_type="application/xml", status=200)

@csrf_exempt
@ratelimit(key='post:From', rate='30/m', method='POST', block=True)
@validate_twilio_signature
def whatsapp_webhook(request):
    """
    Unified Testing Router Webhook Endpoint (For single Twilio Sandbox testing).
    Delegates to Staff Manager or Guest Manager based on active session mode / explicit toggle commands.
    """
    if request.method == "GET":
        return JsonResponse({
            "status": "active",
            "endpoint": "Unified WhatsApp Sandbox Webhook",
            "usage": "Configure this URL as the webhook target for the Twilio Sandbox WhatsApp number (HTTP POST)."
        })
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)


    sender = request.POST.get("From", "")
    message_body = request.POST.get("Body", "").strip()
    lowered = message_body.lower()
    profile_name = request.POST.get("ProfileName", "User")
    message_sid = request.POST.get("MessageSid", "").strip()

    logger.info("Unified Sandbox Webhook message from %s (%s): '%s' [SID=%s]", sender, profile_name, message_body, message_sid)

    if _is_duplicate_message(message_sid):
        logger.warning("Idempotency Guard: Suppressed duplicate MessageSid=%s from %s", message_sid, sender)
        resp = MessagingResponse()
        return HttpResponse(str(resp), content_type="application/xml", status=200)

    use_async = os.getenv("ASYNC_WEBHOOKS", "True").lower() in ("true", "1", "yes")
    if use_async:
        try:
            send_whatsapp_async.delay(sender, message_body, profile_name)
            resp = MessagingResponse()
            return HttpResponse(str(resp), content_type="application/xml", status=200)
        except Exception as e:
            logger.error("Celery dispatch error for router webhook %s (SID=%s): %s. Executing synchronous fallback.", sender, message_sid, e, exc_info=True)

    session = get_user_session(sender)
    is_authenticated = session.get("authenticated") is True
    active_mode = session.get("mode")

    # Mode Toggle Commands
    if lowered in ["/login", "login", "staff login", "staff_login"]:
        active_mode = "STAFF"
    elif lowered in ["guest", "guest mode", "guest_mode", "/guest"]:
        active_mode = "GUEST"
    elif is_authenticated or session.get("state", "").startswith("LOGIN_") or session.get("state", "").startswith("HK_") or session.get("state", "").startswith("CHECKIN_"):
        active_mode = "STAFF"

    # Route Execution
    try:
        if active_mode == "STAFF":
            reply_text = process_staff_message(sender, message_body, profile_name)
        else:
            reply_text = process_guest_message(sender, message_body, profile_name)
    except Exception as e:
        logger.error(f"Router error for {sender}: {e}", exc_info=True)
        reply_text = "⚠️ *Assistant Service Notification*: Please resend your message."

    resp = MessagingResponse()
    resp.message(reply_text)
    return HttpResponse(str(resp), content_type="application/xml", status=200)
