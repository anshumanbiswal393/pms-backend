import logging
import os
import json
from apps.chatbot.integrations.twilio_buttons import _get_twilio_client


logger = logging.getLogger(__name__)

def send_whatsapp_message(to_number: str, message_body: str) -> bool:
    """Sends a standard WhatsApp text message via Twilio REST API."""
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")
    if not from_number:
        logger.warning("TWILIO_WHATSAPP_FROM not configured.")
        return False
    
    client = _get_twilio_client()
    if not client:
        logger.warning("Twilio client unavailable.")
        return False

    try:
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"
        msg = client.messages.create(
            body=message_body,
            from_=from_number,
            to=to_number
        )
        logger.info(f"WhatsApp notification sent to {to_number}. SID: {msg.sid}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}")
        return False

def send_booking_confirmation_reminder(to_number: str, guest_name: str, conf_no: str, room_type: str, arrival_date: str, departure_date: str) -> bool:
    """
    Sends automated booking confirmation reminder via WhatsApp.
    Uses Twilio Content Template SID if configured, else sends rich WhatsApp text template.
    """
    content_sid = os.getenv("TWILIO_CONTENT_SID_CONFIRMATION", "").strip().strip('"').strip("'")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")

    client = _get_twilio_client()
    if content_sid and from_number and client:
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            vars_payload = json.dumps({
                "1": guest_name,
                "2": conf_no,
                "3": room_type,
                "4": arrival_date,
                "5": departure_date
            })
            msg = client.messages.create(
                from_=from_number,
                to=to_number,
                content_sid=content_sid,
                content_variables=vars_payload
            )
            logger.info(f"Confirmation template SID {content_sid} sent to {to_number}. SID: {msg.sid}")
            return True
        except Exception as e:
            logger.warning(f"Failed sending confirmation template SID, falling back to text: {e}")

    body = (
        f"🎉 *Booking Confirmation Reminder*\n\n"
        f"Dear *{guest_name}*,\n"
        f"We are excited to welcome you to Retrod PMS Hotels!\n\n"
        f"📋 *Confirmation Code:* `{conf_no}`\n"
        f"🏨 *Room Category:* {room_type}\n"
        f"📅 *Check-in Date:* {arrival_date}\n"
        f"📅 *Check-out Date:* {departure_date}\n\n"
        f"💡 _Reply `/status {conf_no}` anytime to check your booking details, or `/wifi` for hotel amenities._"
    )
    return send_whatsapp_message(to_number, body)

def send_arrival_instructions(to_number: str, guest_name: str, hotel_name: str = "Retrod Hotel", checkin_time: str = "3:00 PM", address: str = "123 Hospitality Way, Beach Resort Zone") -> bool:
    """Sends arrival instructions and directions to guest."""
    content_sid = os.getenv("TWILIO_CONTENT_SID_ARRIVAL", "").strip().strip('"').strip("'")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")
    client = _get_twilio_client()

    if content_sid and from_number and client:
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            vars_payload = json.dumps({"1": guest_name, "2": hotel_name, "3": checkin_time, "4": address})
            msg = client.messages.create(from_=from_number, to=to_number, content_sid=content_sid, content_variables=vars_payload)
            logger.info(f"Arrival template SID sent to {to_number}. SID: {msg.sid}")
            return True
        except Exception as e:
            logger.warning(f"Arrival template SID fallback: {e}")

    body = (
        f"🧳 *Arrival Instructions & Guest Guide*\n\n"
        f"Dear *{guest_name}*,\n"
        f"Here are your check-in and arrival details for *{hotel_name}*:\n\n"
        f"⏰ *Check-in Time:* {checkin_time}\n"
        f"📍 *Hotel Address:* {address}\n"
        f"🔑 *Front Desk:* Available 24/7 in the Main Lobby\n\n"
        f"🚗 *Parking:* Complimentary valet parking at lobby entrance.\n"
        f"💡 _If you arrive early, our front desk will happily store your luggage!_"
    )
    return send_whatsapp_message(to_number, body)

def send_hotel_wifi_details(to_number: str, guest_name: str, ssid: str = "Retrod_Guest_WiFi", password: str = "WelcomeRetrod2026") -> bool:
    """Sends hotel WiFi access details to guest."""
    content_sid = os.getenv("TWILIO_CONTENT_SID_WIFI", "").strip().strip('"').strip("'")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip().strip('"').strip("'")
    client = _get_twilio_client()

    if content_sid and from_number and client:
        try:
            if not to_number.startswith("whatsapp:"):
                to_number = f"whatsapp:{to_number}"
            vars_payload = json.dumps({"1": guest_name, "2": ssid, "3": password})
            msg = client.messages.create(from_=from_number, to=to_number, content_sid=content_sid, content_variables=vars_payload)
            logger.info(f"WiFi template SID sent to {to_number}. SID: {msg.sid}")
            return True
        except Exception as e:
            logger.warning(f"WiFi template SID fallback: {e}")

    body = (
        f"📶 *Retrod Hotel Complimentary Wi-Fi Access*\n\n"
        f"Dear *{guest_name}*,\n"
        f"Enjoy high-speed Wi-Fi during your stay:\n\n"
        f"📡 *Wi-Fi Network (SSID):* `{ssid}`\n"
        f"🔑 *Password:* `{password}`\n\n"
        f"🌐 Simply select the network on your device and enter the password when prompted."
    )
    return send_whatsapp_message(to_number, body)
