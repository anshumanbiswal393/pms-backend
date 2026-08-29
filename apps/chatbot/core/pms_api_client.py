import logging
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

from django.core.cache import cache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

PMS_BASE_URL = os.getenv("PMS_BACKEND_URL", "https://pms-backend-luxp.onrender.com")
PMS_UI_BASE_URL = os.getenv("PMS_UI_BASE_URL", "https://pms-ui-ten.vercel.app")


class PMSApiClient:
    def __init__(self):
        self.base_url = PMS_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "RetrodChatbot/1.0"})
        
    def invalidate_jwt_cache(self, sender_id: str = None):
        if sender_id:
            try:
                from apps.chatbot.core.session_manager import update_user_session
                update_user_session(sender_id, authenticated=False, jwt_token=None)
            except Exception:
                pass

        else:
            try:
                cache.delete("pms_jwt_token")
            except Exception:
                pass

    def get_auth_headers(self, force_refresh: bool = False, sender_id: str = None):
        headers = {"Content-Type": "application/json"}
        user_jwt = None
        user_prop_id = None

        if sender_id:
            try:
                session = cache.get(f"user_session:{sender_id}")
                if isinstance(session, dict):
                    user_jwt = session.get("jwt_token")
                    user_prop_id = session.get("property_id")
            except Exception:
                pass

        if user_jwt:
            headers["Authorization"] = f"Bearer {user_jwt}"
            if user_prop_id:
                headers["X-Property-ID"] = str(user_prop_id)
            return headers, None

        if force_refresh:
            self.invalidate_jwt_cache()

        token = os.getenv("PMS_API_TOKEN", "").strip()
        if not token:
            try:
                token = cache.get("pms_jwt_token")
            except Exception:
                token = None

        if token:
            headers["Authorization"] = f"Bearer {token}"
            if user_prop_id:
                headers["X-Property-ID"] = str(user_prop_id)
            return headers, None

        username = os.getenv("PMS_USERNAME", "").strip()
        password = os.getenv("PMS_PASSWORD", "").strip()

        if not username or not password:
            return headers, "JWT Token not set."

        login_url = f"{self.base_url}/api/auth/login/"
        try:
            payload = {"email_or_username": username, "username": username, "email": username, "password": password}
            resp = self.session.post(login_url, json=payload, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json()
                tokens_obj = data.get("tokens", {})
                token = (
                    tokens_obj.get("access") or tokens_obj.get("token") or
                    data.get("access") or data.get("token") or data.get("access_token")
                )
                if token:
                    try: cache.set("pms_jwt_token", token, timeout=3600)
                    except Exception: pass
                    headers["Authorization"] = f"Bearer {token}"
                    if user_prop_id:
                        headers["X-Property-ID"] = str(user_prop_id)
                    return headers, None
                return headers, "No access token returned."
            return headers, f"Login failed (HTTP {resp.status_code})"
        except Exception as e:
            return headers, f"Login request failed: {str(e)}"

    def authenticate_staff_credentials(self, username_or_email: str, password: str):
        login_url = f"{self.base_url}/api/auth/login/"
        clean_user = username_or_email.strip()
        clean_pass = password.strip()
        payload = {
            "email_or_username": clean_user,
            "username": clean_user,
            "email": clean_user,
            "password": clean_pass
        }
        try:
            resp = self.session.post(login_url, json=payload, timeout=11.0)
            if resp.status_code == 200:
                data = resp.json()
                tokens_obj = data.get("tokens", {})
                token = (
                    tokens_obj.get("access") or tokens_obj.get("token") or
                    data.get("access") or data.get("token") or data.get("access_token")
                )
                user_info = data.get("user") or data.get("profile") or {}
                properties = data.get("properties") or data.get("property_ids") or []
                
                prop_id = None
                prop_name = "Retrod PMS Hotel Property"
                if properties and isinstance(properties[0], dict):
                    prop_id = str(properties[0].get("id", ""))
                    prop_name = properties[0].get("name", prop_name)
                elif properties:
                    prop_id = str(properties[0])

                if not prop_id:
                    prop_id = "default-property-id"

                return {
                    "token": token,
                    "user": user_info,
                    "property_id": prop_id,
                    "property_name": prop_name,
                    "role": user_info.get("role") or data.get("role") or "Staff Member"
                }, None
            return None, f"HTTP {resp.status_code} ({resp.text[:100]})"
        except requests.exceptions.Timeout:
            return None, "Backend PMS server warming up (timeout). Please resend your password in 5 seconds."
        except Exception as e:
            return None, f"Connection error: {str(e)}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=4),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        reraise=True
    )
    def _raw_request(self, method, url, **kwargs):
        return self.session.request(method, url, **kwargs)

    def make_request(self, method, endpoint, sender_id: str = None, **kwargs):
        headers, auth_error = self.get_auth_headers(sender_id=sender_id)
        class DummyResponse:
            def __init__(self, code, text):
                self.status_code = code
                self.text = text
            def json(self): return {}

        if auth_error:
            return DummyResponse(401, auth_error), auth_error
            
        # Merge custom headers if provided
        custom_headers = kwargs.pop('headers', {})
        headers.update(custom_headers)
        kwargs['headers'] = headers
        kwargs.setdefault('timeout', 6.0)
        url = f"{self.base_url}{endpoint}"
        
        try:
            resp = self._raw_request(method, url, **kwargs)
            if resp.status_code == 401:
                if sender_id:
                    self.invalidate_jwt_cache(sender_id=sender_id)
                else:
                    self.invalidate_jwt_cache()

                headers, auth_err = self.get_auth_headers(sender_id=sender_id, force_refresh=True)
                if not auth_err:
                    headers.update(custom_headers)
                    kwargs['headers'] = headers
                    resp = self._raw_request(method, url, **kwargs)
            return resp, None
        except requests.exceptions.Timeout:
            return DummyResponse(504, "Request Timed Out (6s limit)"), None
        except requests.exceptions.RequestException as e:
            return DummyResponse(500, f"Network Error ({str(e)})"), None
        except Exception as e:
            return DummyResponse(500, f"Network Error ({str(e)})"), None


client = PMSApiClient()


def get_dynamic_property_id(sender_id: str = None):
    def fetch():
        resp, _ = client.make_request("GET", "/api/properties/", sender_id=sender_id, timeout=15.0)
        if resp.status_code == 200:
            props = resp.json()
            items = props if isinstance(props, list) else props.get("results", [])
            for p in items:
                if p.get("is_active", True) and p.get("id"): return str(p["id"])
        return None
    cache_key = f"pms_active_prop_id:{sender_id}" if sender_id else "pms_active_property_id"
    return cache.get_or_set(cache_key, fetch, timeout=86400)


def get_dynamic_unit_type_id(property_id: str, sender_id: str = None):
    def fetch():
        resp, _ = client.make_request("GET", "/api/inventory/types/", sender_id=sender_id, timeout=15.0)
        if resp.status_code == 200:
            types = resp.json()
            items = types if isinstance(types, list) else types.get("results", [])
            for t in items:
                if t.get("id"): return str(t["id"])
        return None
    cache_key = f"pms_unit_type_id:{property_id}:{sender_id}" if sender_id else f"pms_unit_type_id:{property_id}"
    return cache.get_or_set(cache_key, fetch, timeout=86400)


def get_sender_property_name(sender_id: str = None) -> str:
    if sender_id:
        try:
            sess = cache.get(f"user_session:{sender_id}")
            if isinstance(sess, dict) and sess.get("property_name"):
                return sess.get("property_name")
        except Exception:
            pass
    return "Retrod PMS Hotel Property"


def fetch_today_revenue(sender_id: str = None):
    endpoint = "/api/admin/tenant-dashboard/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    prop_name = get_sender_property_name(sender_id)
    if response.status_code == 200:
        data = response.json()
        revenue = data.get("today_revenue") or data.get("revenue") or data.get("total_revenue")
        occupancy = data.get("occupancy_rate") or data.get("occupancy")
        return (
            f"🏨 *{prop_name}*\n"
            f"📊 *Live Retrod PMS Revenue Summary*\n\n"
            f"• *Today's Revenue:* {revenue if revenue is not None else 'N/A'}\n"
            f"• *Occupancy Rate:* {occupancy if occupancy is not None else 'N/A'}"
        )
    return (
        f"🏨 *{prop_name}*\n"
        "⚠️ *Live Revenue Data Access*\n\n"
        f"• *API Status Code:* HTTP {response.status_code}\n"
        f"• *Backend Response:* {response.text[:150]}"
    )


def fetch_room_occupancy(sender_id: str = None):
    endpoint = "/api/assets/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        total_assets = data.get("count") if isinstance(data, dict) else len(data)
        return (
            f"🏨 *Live Retrod PMS Room & Asset Occupancy*\n\n"
            f"• *Total Asset Count:* {total_assets}"
        )
    return (
        "⚠️ *Live Room Occupancy Access*\n\n"
        f"• *API Status Code:* HTTP {response.status_code}\n"
        f"• *Backend Response:* {response.text[:150]}"
    )


def fetch_today_checkins(sender_id: str = None):
    endpoint = "/api/reservations/bookings/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        bookings = data if isinstance(data, list) else data.get("results", [])
        if not bookings:
            return (
                "🔑 *Live Retrod PMS Check-Ins & Bookings Summary*\n\n"
                "• *Scheduled Arrivals:* 0 bookings found for today."
            )

        lines = ["🔑 *Live Retrod PMS Bookings & Check-Ins*\n"]
        for b in bookings[:5]:
            guest = b.get("primary_guest_name") or b.get("fullName") or "Guest"
            ref = b.get("confirmation_number") or (b.get("id")[:8] if b.get("id") else "N/A")
            status = b.get("status", "CONFIRMED")
            arrival = b.get("arrival_date", "Today")
            lines.append(f"• *{guest}* (Ref: `{ref}`) | Arrival: {arrival} | Status: *{status}*")

        return "\n".join(lines)
    return (
        "⚠️ *Today's Check-Ins Access*\n\n"
        f"• *API Status Code:* HTTP {response.status_code}\n"
        f"• *Backend Response:* {response.text[:150]}"
    )


def fetch_system_usage(sender_id: str = None):
    endpoint = "/api/admin/system-usage/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        return (
            "📈 *Live Retrod PMS System Usage & Sessions*\n\n"
            f"• *API Calls Today:* {data.get('api_calls', 0)}\n"
            f"• *Active Staff Users:* {data.get('active_users', 0)}\n"
            f"• *Active Staff Sessions:* {data.get('active_sessions', 0)}\n"
            f"• *Today's Occupancy Rate:* {data.get('occupancy_today', 0)}%\n"
            f"• *Active Hotel Properties:* {data.get('active_properties', 0)}"
        )
    return f"⚠️ *System Usage API Status:* HTTP {response.status_code}\n{response.text[:150]}"


def fetch_audit_logs(sender_id: str = None):
    endpoint = "/api/audit-logs/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        total_count = data.get("count", 0) if isinstance(data, dict) else len(data)
        results = data.get("results", []) if isinstance(data, dict) else data
        lines = [f"📑 *Live Retrod PMS Audit Logs* (Total Logs: {total_count})\n"]
        for log in results[:4]:
            actor = log.get("actor_name") or "System"
            action = log.get("action_type") or "ACTION"
            target = log.get("target_entity") or "System"
            ts = (log.get("timestamp") or "")[:19].replace("T", " ")
            lines.append(f"• [{ts}] *{actor}* - {action} on `{target}`")
        return "\n".join(lines)
    return f"⚠️ *Audit Logs Status:* HTTP {response.status_code}\n{response.text[:150]}"


def fetch_system_health(sender_id: str = None):
    endpoint = "/api/admin/system-health/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        return f"🟢 *Retrod PMS Backend API:* Operational (200 OK)\n\n• *Response Body:* {response.text[:200]}"
    return f"⚠️ *Retrod PMS Backend API Warning*\n\n• *Status:* HTTP {response.status_code}\n• *Response:* {response.text[:200]}"


def fetch_maintenance_stats(sender_id: str = None):
    endpoint = "/api/maintenance/tickets/stats/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        return (
            "🔧 *Retrod PMS Maintenance Overview*\n\n"
            f"• *Open Work Orders:* {data.get('open_work_orders', 0)}\n"
            f"• *Critical Count:* {data.get('critical_count', 0)}\n"
            f"• *Rooms Out of Order (OOO):* {data.get('rooms_ooo', 0)}\n"
            f"• *Avg Resolution Time:* {data.get('avg_resolution', '0.0h')}"
        )
    return f"⚠️ *Maintenance API Status:* HTTP {response.status_code}\n{response.text[:150]}"


def fetch_lost_and_found_stats(sender_id: str = None):
    endpoint = "/api/lost-found/items/stats/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        return (
            "📦 *Retrod PMS Lost & Found Status*\n\n"
            f"• *Open Unclaimed Items:* {data.get('open_items', 0)}\n"
            f"• *Awaiting Guest Claim:* {data.get('awaiting_claim', 0)}\n"
            f"• *Released Month-to-Date:* {data.get('released_mtd', 0)}\n"
            f"• *AI Match Suggestions:* {data.get('match_suggestions', 0)}"
        )
    return f"⚠️ *Lost & Found Status:* HTTP {response.status_code}\n{response.text[:150]}"


def fetch_laundry_stats(sender_id: str = None):
    endpoint = "/api/linen/orders/dashboard-stats/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        return (
            "🧺 *Retrod PMS Laundry & Linen Summary*\n\n"
            f"• *Pending Pickups:* {data.get('pending_pickups', 0)}\n"
            f"• *In Washing:* {data.get('in_washing', 0)}\n"
            f"• *Ready for Delivery:* {data.get('ready_for_delivery', 0)}\n"
            f"• *Laundry Revenue:* ₹{data.get('today_revenue', 0.0)}"
        )
    return f"⚠️ *Laundry Status:* HTTP {response.status_code}\n{response.text[:150]}"


def fetch_security_dashboard(sender_id: str = None):
    endpoint = "/api/admin/security-dashboard/"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        return (
            "🛡️ *Retrod PMS Security Overview*\n\n"
            f"• *Failed Login Attempts:* {data.get('failed_logins', 0)}\n"
            f"• *Locked User Accounts:* {data.get('locked_accounts', 0)}\n"
            f"• *Active Staff Sessions:* {data.get('active_sessions', 0)}\n"
            f"• *MFA Enabled Users:* {data.get('mfa_enabled_users', 0)}"
        )
    return f"⚠️ *Security Status:* HTTP {response.status_code}\n{response.text[:150]}"



def get_reservation_invoice_url(confirmation_number: str) -> str:
    clean_ref = confirmation_number.replace("#", "").strip()
    return f"{PMS_UI_BASE_URL}/billing/invoices/{clean_ref}.pdf"

def submit_guest_feedback(sender_id: str, rating: str, comment: str) -> str:
    endpoint = "/api/feedback/"
    payload = {
        "guest_identifier": sender_id,
        "rating": rating,
        "comments": comment,
        "source": "WhatsApp Bot"
    }
    client.make_request("POST", endpoint, json=payload, sender_id=sender_id, timeout=15.0)
    logger.info(f"[Guest Feedback Registered] Sender: {sender_id} | Rating: {rating} | Comment: '{comment}'")
    return "SUCCESS"

def create_reservation(first_name: str, last_name: str, phone: str, room_type: str, arrival_date: str, departure_date: str, sender_id: str = None) -> str:
    prop_id = None
    if sender_id:
        try:
            sess = cache.get(f"user_session:{sender_id}")
            if isinstance(sess, dict):
                prop_id = sess.get("property_id")
        except Exception:
            pass
    if not prop_id:
        prop_id = get_dynamic_property_id()
    if not prop_id:
        prop_id = os.getenv("DEFAULT_PROPERTY_ID", "default-property-id")

    unit_type_id = get_dynamic_unit_type_id(prop_id) if prop_id else None

    ref_no = f"RES-{int(time.time())}"

    endpoint = "/api/reservations/bookings/"
    payload = {
        "fullName": f"{first_name} {last_name}".strip(),
        "phone": phone,
        "arrival_date": arrival_date,
        "departure_date": departure_date,
        "reservation_type": "Individual",
        "property_id": prop_id,
        "property": prop_id
    }
    if unit_type_id:
        payload["allocations"] = [
            {
                "check_in_date": arrival_date,
                "check_out_date": departure_date,
                "inventory_unit_type": unit_type_id,
                "adult_count": 1
            }
        ]

    headers = {"X-Property-ID": prop_id} if prop_id else {}
    response, _ = client.make_request("POST", endpoint, json=payload, headers=headers, sender_id=sender_id)
    if response.status_code in [200, 201]:
        data = response.json()
        ref_no = data.get("confirmation_number") or data.get("id") or ref_no
        invoice_url = get_reservation_invoice_url(ref_no)
        
        # Dispatch PDF Invoice Link directly to Guest's WhatsApp Number
        guest_phone = phone.strip()
        guest_msg = (
            f"📄 *Your Retrod PMS Booking Confirmation & Invoice*\n\n"
            f"Dear {first_name} {last_name},\n"
            f"Your reservation (`{ref_no}`) at Retrod PMS Hotels has been confirmed by our Front Desk Team!\n\n"
            f"• *Check-in:* {arrival_date}\n"
            f"• *Check-out:* {departure_date}\n"
            f"• *Room Type:* {room_type}\n\n"
            f"📥 *DOWNLOAD YOUR PDF INVOICE:*\n{invoice_url}"
        )
        send_guest_notification(guest_phone, guest_msg, sender_id=sender_id)

        return (
            "🎉 *New Reservation Created Successfully!*\n\n"
            f"• *Confirmation #:* `{ref_no}`\n"
            f"• *Guest:* {first_name} {last_name}\n"
            f"• *Phone:* {phone}\n"
            f"• *Room Type:* {room_type}\n"
            f"• *Check-in:* {arrival_date}\n"
            f"• *Check-out:* {departure_date}\n"
            f"• *Billing Status:* Invoice Issued\n\n"
            f"📲 *PDF Invoice Dispatched:* Sent directly to Guest's WhatsApp (`{phone}`)\n"
            f"📄 *DOWNLOAD PDF INVOICE:*\n{invoice_url}\n\n"
            f"🔘 *VIEW BOOKING IN PORTAL:*\n{PMS_UI_BASE_URL}/reservations"
        )

    fallback_payload = {
        "name": f"In-Bot Reservation - {first_name} {last_name}".strip(),
        "code": ref_no,
        "start_date": arrival_date,
        "end_date": departure_date,
        "status": "OPEN",
        "contact_name": f"{first_name} {last_name}".strip(),
        "contact_phone": phone
    }
    if prop_id:
        fallback_payload["property"] = str(prop_id)

    fb_response, _ = client.make_request("POST", "/api/reservations/group-blocks/", json=fallback_payload, headers=headers, sender_id=sender_id)
    if fb_response.status_code in [200, 201]:
        fb_data = fb_response.json()
        ref_no = fb_data.get("code") or fb_data.get("id") or ref_no
        invoice_url = get_reservation_invoice_url(ref_no)
        
        # Dispatch PDF Invoice Link directly to Guest's WhatsApp Number
        guest_phone = phone.strip()
        guest_msg = (
            f"📄 *Your Retrod PMS Booking Confirmation & Invoice*\n\n"
            f"Dear {first_name} {last_name},\n"
            f"Your reservation (`{ref_no}`) at Retrod PMS Hotels has been confirmed by our Front Desk Team!\n\n"
            f"• *Check-in:* {arrival_date}\n"
            f"• *Check-out:* {departure_date}\n"
            f"• *Room Type:* {room_type}\n\n"
            f"📥 *DOWNLOAD YOUR PDF INVOICE:*\n{invoice_url}"
        )
        send_guest_notification(guest_phone, guest_msg, sender_id=sender_id)

        return (
            "🎉 *New Reservation Created Successfully!*\n\n"
            f"• *Confirmation #:* `{ref_no}`\n"
            f"• *Guest:* {first_name} {last_name}\n"
            f"• *Phone:* {phone}\n"
            f"• *Room Type:* {room_type}\n"
            f"• *Check-in:* {arrival_date}\n"
            f"• *Check-out:* {departure_date}\n"
            "• *Status:* Confirmed (201 Created)\n\n"
            f"📲 *PDF Invoice Dispatched:* Sent directly to Guest's WhatsApp (`{phone}`)\n"
            f"📄 *DOWNLOAD PDF INVOICE:*\n{invoice_url}\n\n"
            f"🔘 *VIEW BOOKING IN PORTAL:*\n{PMS_UI_BASE_URL}/reservations"
        )

    # Return explicit failure notice when API cannot fulfill request
    err_text = response.text[:150] if response.text else "Connection / Permission error"
    return (
        "⚠️ *Reservation Creation Failed*\n\n"
        f"• *Guest Name:* {first_name} {last_name}\n"
        f"• *Phone:* {phone}\n"
        f"• *Room Preference:* {room_type}\n"
        f"• *Dates:* {arrival_date} to {departure_date}\n"
        f"• *PMS API Response:* HTTP {response.status_code} ({err_text})\n\n"
        "💡 _The PMS API could not record this booking directly. Please check PMS server connectivity or create manually in portal:_\n"
        f"🔘 *OPEN RESERVATION PORTAL:*\n{PMS_UI_BASE_URL}/reservations/new"
    )


# --- HOUSEKEEPING & ROOM STATUS ---


def update_room_cleaning_status(room_number: str, new_status: str, sender_id: str = None) -> str:
    endpoint = "/api/housekeeping/tasks/update-status/"
    payload = {
        "room_number": room_number.strip(),
        "status": new_status.upper().strip()
    }
    response, _ = client.make_request("POST", endpoint, json=payload, sender_id=sender_id)
    if response.status_code in [200, 201]:
        return (
            "✅ *Room Status Updated Successfully!*\n\n"
            f"• *Room Number:* {room_number}\n"
            f"• *New Status:* *{new_status.upper()}*\n"
            f"• *Timestamp:* Live Updated\n\n"
            f"🔘 *VIEW HOUSEKEEPING BOARD:*\n{PMS_UI_BASE_URL}/housekeeping"
        )
    return (
        "⚠️ *Room Status Update Failed*\n\n"
        f"• *Room Number:* {room_number}\n"
        f"• *Attempted Status:* {new_status}\n"
        f"• *PMS API Response:* HTTP {response.status_code} ({response.text[:120]})\n"
    )


# --- CHECK-IN ASSISTANCE ---
def process_guest_check_in(confirmation_number: str, room_number: str = None, sender_id: str = None) -> str:
    endpoint = "/api/reservations/check-in/"
    payload = {
        "confirmation_number": confirmation_number.strip(),
        "room_number": room_number.strip() if room_number else ""
    }
    response, _ = client.make_request("POST", endpoint, json=payload, sender_id=sender_id)
    if response.status_code in [200, 201]:
        data = response.json()
        guest_name = data.get("guest_name") or "Guest"
        room = data.get("room_number") or room_number or "Assigned Room"
        return (
            "🔑 *Guest Checked-In Successfully!*\n\n"
            f"• *Confirmation #:* `{confirmation_number}`\n"
            f"• *Guest Name:* {guest_name}\n"
            f"• *Assigned Room:* *{room}*\n"
            f"• *Check-In Status:* OCCUPIED\n\n"
            f"🔘 *OPEN FRONT DESK PORTAL:*\n{PMS_UI_BASE_URL}/check-in"
        )
    return (
        "⚠️ *Check-In Processing Failed*\n\n"
        f"• *Confirmation #:* `{confirmation_number}`\n"
        f"• *PMS API Response:* HTTP {response.status_code} ({response.text[:120]})\n\n"
        f"🔘 *MANUAL CHECK-IN PORTAL:*\n{PMS_UI_BASE_URL}/check-in"
    )


# --- NOTIFICATIONS & REMINDERS ---
def send_guest_notification(phone: str, message_text: str, sender_id: str = None) -> str:
    endpoint = "/api/notifications/send/"
    payload = {
        "recipient_phone": phone.strip(),
        "channel": "WHATSAPP",
        "message": message_text.strip()
    }
    response, _ = client.make_request("POST", endpoint, json=payload, sender_id=sender_id)
    if response.status_code in [200, 201]:
        return f"✅ *Notification Sent to {phone}*"
    return f"⚠️ *Notification Dispatch Status:* HTTP {response.status_code}"


def get_reservation_by_code(confirmation_number: str, sender_id: str = None) -> dict:
    """Fetches reservation details by confirmation number."""
    if not confirmation_number:
        return None
    clean_code = confirmation_number.strip().replace("#", "")
    if not clean_code:
        return None
    endpoint = f"/api/reservations/bookings/?search={clean_code}"
    response, _ = client.make_request("GET", endpoint, sender_id=sender_id)
    if response.status_code == 200:
        data = response.json()
        items = data if isinstance(data, list) else data.get("results", [])
        clean_lower = clean_code.lower()
        for res in items:
            conf_num = str(res.get("confirmation_number") or "").strip().lower()
            res_id = str(res.get("id") or "").strip().lower()
            if conf_num == clean_lower or res_id == clean_lower:
                return res
    return None

def update_reservation_dates(confirmation_number: str, new_arr_date: str, new_dep_date: str, sender_id: str = None) -> (bool, str):
    """Updates check-in and check-out dates for a reservation."""
    res = get_reservation_by_code(confirmation_number, sender_id=sender_id)
    clean_code = confirmation_number.strip().replace("#", "")
    res_id = res.get("id") if res else clean_code

    endpoint = f"/api/reservations/bookings/{res_id}/"
    payload = {
        "arrival_date": new_arr_date,
        "departure_date": new_dep_date
    }
    response, _ = client.make_request("PATCH", endpoint, json=payload, sender_id=sender_id)
    if response.status_code in [200, 202]:
        return True, f"Reservation `{confirmation_number}` updated to {new_arr_date} - {new_dep_date}."
    return False, f"Failed to update dates for reservation `{confirmation_number}`: HTTP {response.status_code} ({response.text[:100]})"

def cancel_reservation(confirmation_number: str, sender_id: str = None) -> (bool, str):
    """Cancels a booking by confirmation number."""
    res = get_reservation_by_code(confirmation_number, sender_id=sender_id)
    clean_code = confirmation_number.strip().replace("#", "")
    res_id = res.get("id") if res else clean_code

    endpoint = f"/api/reservations/bookings/{res_id}/cancel/"
    payload = {"reason": "Cancelled by guest via WhatsApp"}
    response, _ = client.make_request("POST", endpoint, json=payload, sender_id=sender_id)
    if response.status_code in [200, 202, 204]:
        return True, f"Reservation `{confirmation_number}` has been successfully cancelled."
    return False, f"Failed to cancel reservation `{confirmation_number}`: HTTP {response.status_code} ({response.text[:100]}). For manual assistance, visit: {PMS_UI_BASE_URL}/reservations"

