import logging
import os
import re
from django.core.cache import cache
from apps.chatbot.core import pms_api_client
from apps.chatbot.core.session_manager import get_user_session, update_user_session, clear_user_session
from apps.chatbot.integrations.twilio_buttons import send_native_whatsapp_buttons, send_sub_category_buttons
from apps.chatbot.core.guest_manager import handle_booking_flow


logger = logging.getLogger(__name__)

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

# Reusable Main Menu Body for Staff
STAFF_MAIN_MENU_BODY = (
    "👇 *Select an operational domain below:*\n\n"
    "1️⃣ 🔑 *Front Desk & Bookings*\n"
    "2️⃣ 📊 *Analytics & Reports*\n"
    "3️⃣ 🔧 *Operations & Housekeeping*\n"
    "4️⃣ 🛡️ *System Health & Security*\n\n"
    "💡 _(Or reply with a number 1-4, or ask any question naturally!)_"
)

def _unauthenticated_welcome(profile_name: str) -> str:
    return (
        f"👋 *Welcome to Retrod PMS Assistant, {profile_name}!*\n\n"
        "⚠️ **Access Restricted**: Please authenticate or select an access mode to continue:\n\n"
        "1️⃣ 🔐 **Staff Login**: Reply `/login` or enter your **Staff Username/Email**\n"
        "2️⃣ 🧳 **Guest Mode**: Reply `guest` for hotel guest assistance"
    )

def handle_staff_login_flow(sender_id: str, message: str, session: dict) -> str:
    state = session.get("state")
    if state == "LOGIN_USERNAME":
        username = message.strip()
        if not username or len(username) < 3:
            return "⚠️ Please provide a valid Staff Username or Email:"
        session["data"] = {"username": username}
        session["state"] = "LOGIN_PASSWORD"
        cache.set(f"user_session:{sender_id}", session, timeout=86400)
        return f"🔑 Username registered: *{username}*\n\n🔒 Next, reply with your **Password**:"

    elif state == "LOGIN_PASSWORD":
        username = session.get("data", {}).get("username", "")
        password = message.strip()

        auth_data, err = pms_api_client.client.authenticate_staff_credentials(username, password)
        if auth_data:
            role = auth_data.get("role", "Staff Member")
            prop_id = auth_data.get("property_id", "N/A")
            prop_name = auth_data.get("property_name", "Retrod PMS Hotel Property")
            token = auth_data.get("token")

            authenticated_session = {
                "state": "IDLE",
                "authenticated": True,
                "mode": "STAFF",
                "staff_username": username,
                "staff_role": role,
                "property_id": prop_id,
                "property_name": prop_name,
                "jwt_token": token
            }
            cache.set(f"user_session:{sender_id}", authenticated_session, timeout=86400)

            # Trigger native GUI template buttons automatically
            try:
                send_native_whatsapp_buttons(to_number=sender_id, profile_name=username)
            except Exception as e:
                logger.error(f"Post-login button dispatch error: {e}")

            return (
                f"🎉 *Staff Authentication Successful!*\n\n"
                f"• *User:* `{username}`\n"
                f"• *Role:* *{role}*\n"
                f"• *Assigned Hotel:* 🏨 *{prop_name}*\n"
                f"• *Active Property ID:* `{prop_id}`\n\n"
                f"✅ Your session is active. All operations will target **{prop_name}**.\n\n"
                + STAFF_MAIN_MENU_BODY
            )
        else:
            cache.set(f"user_session:{sender_id}", {"state": "LOGIN_PASSWORD", "data": {"username": username}, "authenticated": False, "mode": None}, timeout=86400)
            return (
                "❌ *Authentication Failed*\n\n"
                f"• *Username:* `{username}`\n"
                f"• *Reason:* {err}\n\n"
                "💡 Reply with your **Password** again to retry, or `/login` to restart."
            )
    return None

def handle_housekeeping_flow(sender_id: str, message: str, session: dict) -> str:
    state = session.get("state")
    lowered = message.lower().strip()

    if state == "HK_STATUS_ROOM":
        room_no = message.strip()
        if not room_no:
            return "⚠️ Please reply with a valid **Room Number**:"
        session["data"] = {"room_number": room_no}
        session["state"] = "HK_STATUS_SELECT"
        cache.set(f"user_session:{sender_id}", session, timeout=86400)
        return (
            f"🧹 *Room Number:* `{room_no}`\n\n"
            "Select **New Cleaning Status**:\n"
            "1️⃣ 🟢 **CLEAN**\n"
            "2️⃣ ⭐ **INSPECTED**\n"
            "3️⃣ 🔴 **DIRTY**\n"
            "4️⃣ 🛠️ **OUT OF ORDER (OOO)**\n\n"
            "*(Reply 1, 2, 3, or status name)*"
        )

    elif state == "HK_STATUS_SELECT":
        status_map = {
            "1": "CLEAN", "clean": "CLEAN",
            "2": "INSPECTED", "inspected": "INSPECTED",
            "3": "DIRTY", "dirty": "DIRTY",
            "4": "OOO", "out of order": "OOO", "ooo": "OOO"
        }
        selected_status = status_map.get(lowered, message.upper().strip())
        room_no = session.get("data", {}).get("room_number", "")
        update_user_session(sender_id, "IDLE")
        return pms_api_client.update_room_cleaning_status(room_no, selected_status, sender_id=sender_id)

    return None

def handle_checkin_flow(sender_id: str, message: str, session: dict) -> str:
    state = session.get("state")
    if state == "CHECKIN_CONFIRMATION":
        conf_no = message.strip()
        if not conf_no:
            return "⚠️ Please reply with the **Booking Confirmation Number**:"
        update_user_session(sender_id, "IDLE")
        return pms_api_client.process_guest_check_in(conf_no, sender_id=sender_id)
    return None

def route_staff_submenu(curr_state: str, lowered: str, sender_id: str, profile_name: str = "Staff Member") -> str:
    if curr_state == "IN_FRONTDESK_MENU":
        if lowered in ["1", "1️⃣"] or any(k in lowered for k in ["checkins", "check-ins"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_today_checkins(sender_id=sender_id)
        elif lowered in ["2", "2️⃣"] or any(k in lowered for k in ["occupancy", "room availability"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_room_occupancy(sender_id=sender_id)
        elif lowered in ["3", "3️⃣"] or any(k in lowered for k in ["create reservation", "new reservation", "book"]):
            update_user_session(sender_id, "BOOKING_NAME", data={})
            return "📝 *In-Bot New Reservation Creation*\n\nPlease reply with the Guest's **Full Name**:"

    elif curr_state == "IN_ANALYTICS_MENU":
        if lowered in ["1", "1️⃣"] or any(k in lowered for k in ["revenue", "btn_revenue"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_today_revenue(sender_id=sender_id)
        elif lowered in ["2", "2️⃣"] or any(k in lowered for k in ["usage", "btn_usage"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_system_usage(sender_id=sender_id)
        elif lowered in ["3", "3️⃣"] or any(k in lowered for k in ["audit", "btn_audit"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_audit_logs(sender_id=sender_id)

    elif curr_state == "IN_OPERATIONS_MENU":
        if lowered in ["1", "1️⃣"] or any(k in lowered for k in ["maintenance", "btn_maintenance"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_maintenance_stats(sender_id=sender_id)
        elif lowered in ["2", "2️⃣"] or any(k in lowered for k in ["lost", "btn_lost_found"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_lost_and_found_stats(sender_id=sender_id)
        elif lowered in ["3", "3️⃣"] or any(k in lowered for k in ["laundry", "btn_laundry"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_laundry_stats(sender_id=sender_id)

    elif curr_state == "IN_SECURITY_MENU":
        if lowered in ["1", "1️⃣"] or any(k in lowered for k in ["health", "btn_health"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_system_health(sender_id=sender_id)
        elif lowered in ["2", "2️⃣"] or any(k in lowered for k in ["security", "btn_security"]):
            update_user_session(sender_id, "IDLE")
            return pms_api_client.fetch_security_dashboard(sender_id=sender_id)
    return None

def route_staff_categories_and_buttons(curr_state: str, lowered: str, sender_id: str, profile_name: str = "Staff Member") -> str:
    if lowered in ["1", "1️⃣", "cat_frontdesk", "frontdesk"]:
        update_user_session(sender_id, "IN_FRONTDESK_MENU")
        send_sub_category_buttons(to_number=sender_id, category_key="frontdesk", profile_name=profile_name)
        return "🔑 *Front Desk & Bookings Menu*\n\n1️⃣ 📋 *Today's Check-ins*\n2️⃣ 🏨 *Room Availability & Occupancy*\n3️⃣ ➕ *Create New Reservation*"

    if lowered in ["2", "2️⃣", "cat_analytics", "analytics"]:
        update_user_session(sender_id, "IN_ANALYTICS_MENU")
        send_sub_category_buttons(to_number=sender_id, category_key="analytics", profile_name=profile_name)
        return "📊 *Analytics & Financial Reports*\n\n1️⃣ 💰 *Today's Revenue*\n2️⃣ 📈 *System Usage & Sessions*\n3️⃣ 📑 *Audit Logs Summary*"

    if lowered in ["3", "3️⃣", "cat_operations", "operations"]:
        update_user_session(sender_id, "IN_OPERATIONS_MENU")
        send_sub_category_buttons(to_number=sender_id, category_key="operations", profile_name=profile_name)
        return "🔧 *Hotel Operations*\n\n1️⃣ 🔨 *Maintenance Work Orders*\n2️⃣ 📦 *Lost & Found Status*\n3️⃣ 🧺 *Linen & Laundry*"

    if lowered in ["4", "4️⃣", "cat_security", "security"]:
        update_user_session(sender_id, "IN_SECURITY_MENU")
        send_sub_category_buttons(to_number=sender_id, category_key="security", profile_name=profile_name)
        return "🛡️ *System Health & Security*\n\n1️⃣ 🟢 *PMS API Backend Health*\n2️⃣ 🔐 *Security Overview & Logins*"

    direct_actions = [
        (["btn_checkins", "today's check-ins", "today's checkin", "checkins", "check-ins", "expected arrivals"], "IDLE", lambda: pms_api_client.fetch_today_checkins(sender_id=sender_id)),
        (["btn_occupancy", "room availability & occupancy", "room availability", "occupancy", "available rooms", "occupied rooms"], "IDLE", lambda: pms_api_client.fetch_room_occupancy(sender_id=sender_id)),
        (["btn_revenue", "today's revenue", "today revenue", "revenue", "earnings", "financial report", "income"], "IDLE", lambda: pms_api_client.fetch_today_revenue(sender_id=sender_id)),
        (["btn_usage", "system usage & sessions", "system usage", "active sessions", "usage stats"], "IDLE", lambda: pms_api_client.fetch_system_usage(sender_id=sender_id)),
        (["btn_audit", "audit logs summary", "audit logs", "audit log", "audit summary"], "IDLE", lambda: pms_api_client.fetch_audit_logs(sender_id=sender_id)),
        (["btn_maintenance", "maintenance work orders", "maintenance", "work orders", "maintenance tickets"], "IDLE", lambda: pms_api_client.fetch_maintenance_stats(sender_id=sender_id)),
        (["btn_lost_found", "lost & found status", "lost & found", "lost and found", "lost found"], "IDLE", lambda: pms_api_client.fetch_lost_and_found_stats(sender_id=sender_id)),
        (["btn_laundry", "linen & laundry", "laundry", "linen"], "IDLE", lambda: pms_api_client.fetch_laundry_stats(sender_id=sender_id)),
        (["btn_health", "pms api backend health", "system health", "backend health", "api status", "health check"], "IDLE", lambda: pms_api_client.fetch_system_health(sender_id=sender_id)),
        (["btn_security", "security overview & logins", "security overview", "security dashboard", "logins security"], "IDLE", lambda: pms_api_client.fetch_security_dashboard(sender_id=sender_id)),
    ]

    for keywords, state, reply in direct_actions:
        if any(k in lowered for k in keywords):
            update_user_session(sender_id, state)
            return reply() if callable(reply) else reply

    return None

def process_staff_message(sender_id: str, message: str, profile_name: str) -> str:
    """Pure, isolated Staff Message Processing Engine."""
    if not message:
        return _unauthenticated_welcome(profile_name)

    lowered = message.lower().strip()
    session = get_user_session(sender_id)
    state = session.get("state", "IDLE")

    # Logout
    if lowered in ["/logout", "logout", "staff logout", "staff_logout", "signout", "sign out"]:
        clear_user_session(sender_id)
        return (
            "🔓 *Staff Logout Successful*\n\n"
            "You have been logged out of your staff account. All active session tokens and property contexts have been cleared.\n\n"
            "💡 _Reply `/login` to log in again, or 'guest' for Guest Mode._"
        )

    # Login Activation
    if lowered in ["/login", "login", "staff login", "staff_login"]:
        update_user_session(sender_id, "LOGIN_USERNAME", authenticated=False, mode="STAFF", data={})
        return "🔐 *Retrod PMS Staff Authentication*\n\nPlease reply with your **Staff Username or Email**:"

    # Active State Handlers
    if state.startswith("LOGIN_"):
        reply = handle_staff_login_flow(sender_id, message, session)
        if reply: return reply

    if state.startswith("BOOKING_"):
        reply = handle_booking_flow(sender_id, message, session)
        if reply: return reply

    if state.startswith("HK_STATUS_"):
        reply = handle_housekeeping_flow(sender_id, message, session)
        if reply: return reply

    if state.startswith("CHECKIN_"):
        reply = handle_checkin_flow(sender_id, message, session)
        if reply: return reply

    # Main Navigation
    if lowered in ["0", "0️⃣", "home", "main menu", "menu", "go back", "back", "cancel", "reset"]:
        update_user_session(sender_id, "IDLE")
        prop_name = session.get("property_name", "Retrod PMS Hotel Property")
        send_native_whatsapp_buttons(to_number=sender_id, profile_name=profile_name)
        return f"🏠 *Main Menu - Retrod PMS Assistant*\n🏨 Hotel: *{prop_name}*\n\n" + STAFF_MAIN_MENU_BODY

    # Triggers
    if any(k in lowered for k in ["update room status", "room cleaning status", "housekeeping update", "mark room clean"]):
        update_user_session(sender_id, "HK_STATUS_ROOM", data={})
        return "🧹 *Housekeeping Room Status Update*\n\nPlease reply with the **Room Number** you want to update:"

    if any(k in lowered for k in ["walkin checkin", "process checkin", "checkin guest", "check-in guest"]):
        update_user_session(sender_id, "CHECKIN_CONFIRMATION", data={})
        return "🔑 *Front Desk Walk-In Check-In Assistance*\n\nPlease reply with the **Booking Confirmation Number**:"

    # Submenus & Categories
    submenu_reply = route_staff_submenu(state, lowered, sender_id, profile_name)
    if submenu_reply: return submenu_reply

    direct_reply = route_staff_categories_and_buttons(state, lowered, sender_id, profile_name)
    if direct_reply: return direct_reply

    # RAG / LLM Staff Operational Knowledge Processor
    from apps.chatbot.ai_engine.embeddings import search_knowledge_base

    chunks = search_knowledge_base(message, top_k=3)
    if chunks:
        knowledge_context = "\n\n".join([f"[{c.title}]\n{c.content}" for c in chunks])
        system_prompt = (
            "You are Retrod PMS Staff Operational Assistant.\n"
            "Provide direct, accurate, and concise operational instructions for hotel staff members based on the provided PMS documentation, system features, and web navigation routes.\n"
            "Use the following verified PMS knowledge as your primary source.\n\n"
            f"Verified PMS Knowledge:\n{knowledge_context}"
        )

        groq_api_key = os.getenv("GROQ_API_KEY")
        if groq_api_key:
            client = _get_groq_client(groq_api_key)
            if client:
                try:
                    comp = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        temperature=0.2,
                        max_tokens=300
                    )
                    return comp.choices[0].message.content.strip()
                except Exception as e:
                    logger.error(f"Groq API Staff Error: {e}")

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if openai_api_key:
            client = _get_openai_client(openai_api_key)
            if client:
                try:
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": message}],
                        max_tokens=300
                    )
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    logger.error(f"OpenAI API Staff Error: {e}")

        top_chunk = chunks[0]
        return f"📖 *PMS Operational Guide ({top_chunk.title})*:\n\n{top_chunk.content}"

    # Default Staff Response
    prop_name = session.get("property_name", "Retrod PMS Hotel Property")
    return f"👋 *Retrod Staff Assistant*\n🏨 Hotel: *{prop_name}*\n\n" + STAFF_MAIN_MENU_BODY
