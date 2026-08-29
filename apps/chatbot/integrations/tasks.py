import logging
import os
from celery import shared_task
from apps.chatbot.core.chat_manager import process_incoming_message

logger = logging.getLogger(__name__)

@shared_task
def send_whatsapp_async(sender_id: str, message_body: str, profile_name: str):
    """
    Asynchronous Celery task:
    1. Processes message using RAG search & Groq LLM.
    2. Sends reply back to WhatsApp via Twilio REST API.
    """
    logger.info(f"[Celery Worker] Processing message from {sender_id}: '{message_body}'")

    # 1. Process message via AI RAG Chat Manager
    reply_text = process_incoming_message(
        sender_id=sender_id,
        message=message_body,
        profile_name=profile_name,
        channel="whatsapp"
    )

    # 2. Send WhatsApp response via Twilio REST API Client
    from apps.chatbot.integrations.twilio_buttons import _get_twilio_client
    client = _get_twilio_client()

    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")

    if client and from_number:
        try:
            message = client.messages.create(
                body=reply_text,
                from_=from_number,
                to=sender_id
            )
            logger.info(f"[Celery Worker] Message sent successfully to {sender_id}. SID: {message.sid}")
            return message.sid
        except Exception as e:
            logger.error(f"[Celery Worker] Error sending WhatsApp message via Twilio REST API: {e}")
            raise e

    logger.warning("[Celery Worker] Twilio credentials missing, returning reply_text directly.")
    return reply_text
