import logging
import os
import re
from datetime import datetime
from apps.chatbot.core import pms_api_client
from apps.chatbot.core.session_manager import get_user_session, update_user_session


logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r'^\+?[\d\s\-().]{7,20}$')

_groq_client = None
_cached_groq_key = None
_openai_client = None
_cached_openai_key = None

def _get_groq_client(api_key: str):
    """Cached singleton getter for Groq client."""
    global _groq_client, _cached_groq_key
    if _groq_client is None or _cached_groq_key != api_key:
        try:
            from groq import Groq
            _groq_client = Groq(api_key=api_key)
            _cached_groq_key = api_key
        except Exception as e:
            logger.error("Failed to initialize Groq client singleton: %s", e)
            return None
    return _groq_client

def _get_openai_client(api_key: str):
    """Cached singleton getter for OpenAI client."""
    global _openai_client, _cached_openai_key
    if _openai_client is None or _cached_openai_key != api_key:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=api_key)
            _cached_openai_key = api_key
        except Exception as e:
            logger.error("Failed to initialize OpenAI client singleton: %s", e)
            return None
    return _openai_client

def _guest_welcome(profile_name: str) -> str:
    return (
        f"🧳 *Welcome Hotel Guest, {profile_name}!*\n\n"
        "I am your Retrod Hotel Virtual Assistant. How can I assist you today?\n"
        "• Ask about check-in / check-out times, amenities, or Wi-Fi\n"
        "• Inquire about hotel dining or room features\n"
        "• Reply `book` to make a room reservation\n\n"
        "💡 _(Staff members: reply `/login` anytime to authenticate for Staff Operations)_"
    )

def parse_date(date_str: str) -> str:
    if not date_str:
        return None
    date_str = date_str.strip().strip(",")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None

# --- IN-BOT BOOKING CREATION FLOW FOR GUESTS ---
def handle_booking_flow(sender_id: str, message: str, session: dict) -> str:
    state = session.get("state")
    raw_input = message.strip()

    if state == "BOOKING_NAME":
        clean_name = re.sub(r'^(my name is|i am|name\s*[:=]?)\s*', '', raw_input, flags=re.IGNORECASE).strip()
        if not clean_name or len(clean_name) < 2: 
            return "Please provide a valid Guest Name:"
        session["data"] = {"guest_name": clean_name}
        session["state"] = "BOOKING_PHONE"
        cache.set(f"user_session:{sender_id}", session, timeout=86400)
        return f"👤 Guest Name: *{clean_name}*\n\nNext, reply with your **Phone Number**:"

    elif state == "BOOKING_PHONE":
        phone_match = re.search(r'\+?\d[\d\s\-().]{7,20}', raw_input)
        phone_input = phone_match.group(0).strip() if phone_match else raw_input
        if not _PHONE_RE.match(phone_input):
            return "⚠️ That doesn't look like a valid phone number. Please enter a valid phone number:"
        session["data"]["phone"] = phone_input
        session["state"] = "BOOKING_ROOM"
        cache.set(f"user_session:{sender_id}", session, timeout=86400)
        return f"📱 Phone registered: *{phone_input}*\n\nSelect **Room Type**:\n1️⃣ Deluxe Villa\n2️⃣ Executive Suite\n3️⃣ Standard King Room\n\n*(Reply 1, 2, or 3)*"

    elif state == "BOOKING_ROOM":
        lowered = raw_input.lower()
        if "1" in lowered or "delux" in lowered or "villa" in lowered: room_choice = "Deluxe Villa"
        elif "2" in lowered or "exec" in lowered or "suite" in lowered: room_choice = "Executive Suite"
        elif "3" in lowered or "king" in lowered or "standard" in lowered: room_choice = "Standard King Room"
        else: room_choice = raw_input.title()

        session["data"]["room_type"] = room_choice
        session["state"] = "BOOKING_DATES"
        cache.set(f"user_session:{sender_id}", session, timeout=86400)
        return f"🏨 Room Type selected: *{room_choice}*\n\nFinally, reply with **Check-in & Check-out Dates**\n*(Format: YYYY-MM-DD to YYYY-MM-DD)*:"

    elif state == "BOOKING_DATES":
        arr_date = None
        dep_date = None

        if " to " in raw_input.lower():
            parts = re.split(r'\s+to\s+', raw_input, flags=re.IGNORECASE)
        elif "," in raw_input:
            parts = raw_input.split(",")
        else:
            dates_found = re.findall(r'\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b', raw_input)
            if len(dates_found) >= 2:
                parts = [dates_found[0], dates_found[1]]
            else:
                parts = raw_input.split()

        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            arr_date = parse_date(parts[0])
            dep_date = parse_date(parts[1])
            if (not arr_date or not dep_date) and len(parts) >= 6:
                arr_date = parse_date(f"{parts[0]} {parts[1]} {parts[2]}")
                dep_date = parse_date(f"{parts[3]} {parts[4]} {parts[5]}")

        if not arr_date or not dep_date:
            return "⚠️ I couldn't understand those dates.\nPlease provide them formatted as **YYYY-MM-DD to YYYY-MM-DD**"

        data = session.get("data", {})
        name_parts = data.get("guest_name", "Guest").split(" ", 1)
        caller_mode = session.get("mode", "GUEST")
        update_user_session(sender_id, "IDLE", mode=caller_mode)

        return pms_api_client.create_reservation(
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else "Member",
            phone=data.get("phone", "N/A"),
            room_type=data.get("room_type", "Standard"),
            arrival_date=arr_date,
            departure_date=dep_date,
            sender_id=sender_id
        )
    return None

# --- FEATURE 5 STREAMLINED BOOKING STATUS LOOKUP FLOW ---
def handle_guest_status_flow(sender_id: str, message: str, session: dict) -> str:
    """Queries PMS for booking status by confirmation code or phone number with BOLA ownership validation."""
    raw_code = message.strip()
    if raw_code.lower().startswith("/status"):
        raw_code = raw_code[7:].strip()

    if not raw_code:
        update_user_session(sender_id, "STATUS_CONF_NO", mode="GUEST")
        return "📋 *Guest Booking Status Query*: Please reply with your **Booking Confirmation Code** (e.g. `RET-84920`):"

    # Query PMS API
    res = pms_api_client.get_reservation_by_code(raw_code, sender_id=sender_id)
    update_user_session(sender_id, "IDLE", mode="GUEST")

    if res and isinstance(res, dict):
        # Enforce BOLA Object Ownership Verification
        res_phone = str(res.get("phone") or res.get("contact_phone") or res.get("mobile") or res.get("guest_phone") or "").strip()
        clean_user_phone = re.sub(r'\D', '', sender_id)
        clean_res_phone = re.sub(r'\D', '', res_phone)

        # Allow access if user is authenticated staff or phone number matches
        is_staff = session.get("mode") == "STAFF" or session.get("authenticated") is True
        if clean_res_phone and not is_staff:
            if clean_res_phone not in clean_user_phone and clean_user_phone not in clean_res_phone:
                logger.warning("BOLA Guard: Blocked unauthorized reservation status access to %s from sender %s", raw_code, sender_id)
                return "🔒 *Access Denied*: The confirmation code was found, but the phone number of your account does not match the primary reservation phone number."

        conf_no = res.get("confirmation_number") or res.get("id") or raw_code
        guest_name = res.get("primary_guest_name") or res.get("fullName") or res.get("contact_name") or "Guest"
        room_type = res.get("room_type") or res.get("inventory_unit_type") or "Standard Room"
        arr_date = res.get("arrival_date") or res.get("start_date") or "Scheduled"
        dep_date = res.get("departure_date") or res.get("end_date") or "Scheduled"
        status = res.get("status", "CONFIRMED")
        invoice_url = pms_api_client.get_reservation_invoice_url(conf_no)

        return (
            f"📋 *Retrod PMS Booking Details*\n\n"
            f"• *Confirmation #:* `{conf_no}`\n"
            f"• *Primary Guest:* *{guest_name}*\n"
            f"• *Room Category:* {room_type}\n"
            f"• *Check-in Date:* {arr_date}\n"
            f"• *Check-out Date:* {dep_date}\n"
            f"• *Reservation Status:* *{status}*\n\n"
            f"📥 *PDF Invoice Link:*\n{invoice_url}"
        )

    # Fallback response if code is not found directly
    return (
        f"📋 *Booking Status Search*\n\n"
        f"We searched for confirmation code `{raw_code}`, but could not locate an active reservation.\n"
        f"Please verify your code or reply `menu` to access hotel services."
    )

def handle_guest_reschedule_flow(sender_id: str, message: str, session: dict) -> str:
    """Safe stub for guest reschedule flow."""
    update_user_session(sender_id, "IDLE", mode="GUEST")
    return "📅 *Booking Date Modification*: Please contact our front desk for date change assistance."

def handle_guest_cancel_flow(sender_id: str, message: str, session: dict) -> str:
    """Safe stub for guest cancellation flow."""
    update_user_session(sender_id, "IDLE", mode="GUEST")
    return "❌ *Booking Cancellation*: Please contact our front desk for cancellation assistance."


def process_guest_message(sender_id: str, message: str, profile_name: str = "Guest") -> str:
    """Pure, isolated Guest Message Processing Engine."""
    if not message:
        return _guest_welcome(profile_name)

    lowered = message.lower().strip()
    session = get_user_session(sender_id)
    state = session.get("state", "IDLE")

    # --- FEATURE 4 NATIVE WHATSAPP BUTTON INTERCEPTORS ---
    if lowered in ["btn_wifi_details", "wi-fi access", "wifi access", "wi-fi details", "wifi details", "wifi", "/wifi"] or (state == "IDLE" and lowered == "1"):
        return (
            f"📶 *Retrod Hotel Complimentary Wi-Fi Access*\n\n"
            f"Dear *{profile_name}*,\n"
            f"Enjoy high-speed Wi-Fi during your stay:\n\n"
            f"📡 *Wi-Fi Network (SSID):* `Retrod_Guest_WiFi`\n"
            f"🔑 *Password:* `WelcomeRetrod2026`\n\n"
            f"🌐 Select the network on your device and enter the password when prompted."
        )

    if lowered in ["btn_arrival_guide", "arrival guide", "arrival instructions", "directions", "location", "check-in", "checkin", "check in", "arrival", "/arrival"] or (state == "IDLE" and lowered == "2"):
        return (
            f"🧳 *Arrival Instructions & Guest Guide*\n\n"
            f"Dear *{profile_name}*,\n"
            f"Here are your check-in and arrival details:\n\n"
            f"⏰ *Check-in Time:* 3:00 PM\n"
            f"📍 *Hotel Address:* 123 Hospitality Way, Beach Resort Zone\n"
            f"🔑 *Front Desk:* Available 24/7 in the Main Lobby\n\n"
            f"🚗 *Parking:* Complimentary valet parking at lobby entrance."
        )

    if lowered in ["btn_check_status", "my booking", "check status", "booking status", "/status"] or (state == "IDLE" and lowered == "3"):
        update_user_session(sender_id, "STATUS_CONF_NO", mode="GUEST")
        return (
            f"📋 *My Booking Status Inquiry*\n\n"
            f"Dear *{profile_name}*, please reply with your **Booking Confirmation Code** (e.g., `RET-84920`):"
        )

    if lowered in ["btn_guest_menu", "guest menu", "main menu"]:
        update_user_session(sender_id, "IDLE", mode="GUEST")
        return _guest_welcome(profile_name)

    # Mode switch back to staff login if guest asks for staff
    if lowered in ["/login", "login", "staff login", "staff_login"]:
        update_user_session(sender_id, "LOGIN_USERNAME", authenticated=False, mode="STAFF", data={})
        return "🔐 *Retrod PMS Staff Authentication*\n\nPlease reply with your **Staff Username or Email**:"

    # Mode greeting
    if lowered in ["guest", "guest mode", "guest_mode", "/guest", "hi", "hello", "hey", "start", "0", "0️⃣", "home", "menu"]:
        update_user_session(sender_id, "IDLE", mode="GUEST")
        return _guest_welcome(profile_name)

    # Direct /status command trigger or confirmation code format
    import re
    if lowered.startswith("/status") or (state in ["IDLE", "STATUS_CONF_NO"] and re.search(r'\b(ret|res|bk)-?\d{3,10}\b', lowered)):
        return handle_guest_status_flow(sender_id, message, session)

    # --- ACTIVE SESSION STATE MACHINE HANDLERS ---
    if state == "STATUS_CONF_NO":
        return handle_guest_status_flow(sender_id, message, session)

    if state.startswith("BOOKING_"):
        return handle_booking_flow(sender_id, message, session)

    if state.startswith("FEEDBACK_"):
        if state == "FEEDBACK_RATING":
            update_user_session(sender_id, "FEEDBACK_COMMENT", mode="GUEST", data={"rating": message.strip()})
            return f"⭐ Rating Registered: *{message.strip()}*\n\nWould you like to share any feedback or comments?\n*(Reply with your comment, or reply 'skip'):*"
        elif state == "FEEDBACK_COMMENT":
            comment_text = message.strip() if message.strip().lower() not in ["skip", "none", "no", "n/a"] else "No comment provided."
            rating_val = session.get("data", {}).get("rating", "5 Stars")
            update_user_session(sender_id, "IDLE", mode="GUEST")
            pms_api_client.submit_guest_feedback(sender_id, rating_val, comment_text)
            return f"🙏 *Thank You for Your Feedback!*\n\n• *Rating:* {rating_val}\n• *Comment:* {comment_text}\n\nWe hope you enjoyed your stay at Retrod PMS Hotels! 🚗✈️"

    # Checkout / Vacating Feedback Trigger
    is_vacating_query = (state == "IDLE" and lowered == "5") or (any(k in lowered for k in ["vacating", "vacated", "checking out", "checked out", "check out now", "checkout now", "leaving now", "trip is done", "finished stay", "leaving room"]) and not any(q in lowered for q in ["what time", "when is", "policy", "hours", "how do"]))
    if is_vacating_query:
        update_user_session(sender_id, "FEEDBACK_RATING", mode="GUEST", data={})
        return f"🛎️ *Checkout / Vacating Request Registered*\n\nThank you for staying with Retrod PMS Hotels, *{profile_name}*!\n\nPlease rate your stay experience on a scale of 1 to 5 Stars ⭐:\n\n1️⃣ ⭐ 1/5 - Poor\n2️⃣ ⭐⭐ 2/5 - Fair\n3️⃣ ⭐⭐⭐ 3/5 - Good\n4️⃣ ⭐⭐⭐⭐ 4/5 - Very Good\n5️⃣ ⭐⭐⭐⭐⭐ 5/5 - Excellent"

    # New Reservation Trigger
    if (state == "IDLE" and lowered == "4") or any(k in lowered for k in ["new reservation", "book a room", "book room", "create reservation", "book", "/book"]):
        update_user_session(sender_id, "BOOKING_NAME", mode="GUEST", data={})
        return "📝 *In-Bot New Reservation Creation*\n\nPlease reply with your **Full Name**:"

    # RAG / LLM Guest Fallback Processor
    from apps.chatbot.ai_engine.embeddings import search_knowledge_base

    chunks = search_knowledge_base(message, category="general_faq", top_k=3)
    if not chunks:
        chunks = search_knowledge_base(message, top_k=3)

    knowledge_context = ""
    if chunks:
        knowledge_context = "\n\n".join([f"[{c.title}]\n{c.content}" for c in chunks])

    system_prompt = (
        "You are Retrod Hotel Virtual Guest Assistant. "
        "Answer the guest's question warmly, politely, and concisely (max 2 short bullet points). "
        "Use the following verified hotel knowledge as your primary source. Do not invent hotel policies, URLs, or procedures. "
        "If the knowledge base does not contain enough information, state that clearly and offer to connect them to the front desk."
    )
    if knowledge_context:
        system_prompt += f"\n\nVerified Hotel Knowledge:\n{knowledge_context}"

    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        client = _get_groq_client(groq_api_key)
        if client:
            try:
                comp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                    temperature=0.2,
                    max_tokens=250
                )
                return comp.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq API Guest Error: {e}")

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        client = _get_openai_client(openai_api_key)
        if client:
            try:
                resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                    max_tokens=250
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"OpenAI API Guest Error: {e}")

    if chunks:
        top_chunk = chunks[0]
        return f"🏨 *Hotel Information ({top_chunk.title})*:\n{top_chunk.content[:250]}"

    return _guest_welcome(profile_name)

