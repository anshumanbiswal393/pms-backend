import time
import json
import logging
import requests
from typing import Dict, Any, Optional, List
from django.utils import timezone
from apps.features.channel_manager.models import StaahConfig, StaahSyncLog

logger = logging.getLogger(__name__)

class StaahSuClient:
    """
    Robust HTTP client for communicating with STAAH Su API / ChannelConnect.
    Handles authentication, 30s timeouts, payload validation, and automatic DB logging.
    """

    def __init__(self, config: Optional[StaahConfig] = None, **kwargs):
        if config:
            self.config = config
            self.domain = config.domain.rstrip('/')
            self.app_id = config.app_id
            self.auth_token = config.auth_token
            self.hotel_id = config.hotel_id
        else:
            self.config = None
            self.domain = kwargs.get('domain', 'https://connect.su-api.com').rstrip('/')
            self.app_id = kwargs.get('app_id', '')
            self.auth_token = kwargs.get('auth_token', '')
            self.hotel_id = kwargs.get('hotel_id', '')

        # Standard headers
        self.headers = {
            'Content-Type': 'application/json',
            'app-id': self.app_id,
            'Authorization': self.auth_token if self.auth_token.startswith('Basic ') else f'Basic {self.auth_token}',
        }

    def _log_transaction(
        self,
        sync_type: str,
        direction: str,
        endpoint: str,
        status: str,
        req_payload: Any,
        res_payload: Any,
        error_msg: Optional[str] = None,
        records_count: int = 0,
        duration_ms: int = 0
    ):
        if not self.config:
            return

        try:
            # Ensure JSON-serializable
            safe_req = req_payload if isinstance(req_payload, (dict, list)) else {'raw': str(req_payload)}
            safe_res = res_payload if isinstance(res_payload, (dict, list)) else {'raw': str(res_payload)}

            StaahSyncLog.objects.create(
                config=self.config,
                sync_type=sync_type,
                direction=direction,
                status=status,
                endpoint=endpoint,
                request_payload=safe_req,
                response_payload=safe_res,
                error_message=error_msg,
                records_count=records_count,
                duration_ms=duration_ms
            )
        except Exception as e:
            logger.error(f"Failed to record StaahSyncLog: {str(e)}")

    def _post(self, path: str, payload: Dict[str, Any], sync_type: str = 'Inventory') -> Dict[str, Any]:
        """Performs HTTP POST to STAAH Su API with 30s timeout and audit logging."""
        url = f"{self.domain}{path}"
        start_time = time.time()
        
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)

            try:
                res_json = response.json()
            except Exception:
                res_json = {"raw_text": response.text}

            is_success = response.status_code in [200, 201] and (
                isinstance(res_json, dict) and res_json.get('status') != 'fail'
            )
            status_label = 'Success' if is_success else 'Error'
            error_msg = None if is_success else (
                res_json.get('error_desc') or res_json.get('message') or f"HTTP {response.status_code}"
            )

            self._log_transaction(
                sync_type=sync_type,
                direction='OUTBOUND',
                endpoint=path,
                status=status_label,
                req_payload=payload,
                res_payload=res_json,
                error_msg=error_msg,
                duration_ms=duration_ms
            )

            if is_success and self.config:
                self.config.last_synced_at = timezone.now()
                self.config.last_error = None
                self.config.save(update_fields=['last_synced_at', 'last_error', 'updated_at'])

            return {
                "success": is_success,
                "status_code": response.status_code,
                "data": res_json,
                "duration_ms": duration_ms
            }

        except requests.exceptions.RequestException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_str = str(e)
            
            self._log_transaction(
                sync_type=sync_type,
                direction='OUTBOUND',
                endpoint=path,
                status='Error',
                req_payload=payload,
                res_payload={},
                error_msg=error_str,
                duration_ms=duration_ms
            )

            if self.config:
                self.config.last_error = error_str
                self.config.save(update_fields=['last_error', 'updated_at'])

            return {
                "success": False,
                "status_code": 500,
                "error": error_str,
                "duration_ms": duration_ms
            }

    def _get(self, path: str, sync_type: str = 'Content') -> Dict[str, Any]:
        """Performs HTTP GET to STAAH Su API with 30s timeout and audit logging."""
        url = f"{self.domain}{path}"
        start_time = time.time()

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            duration_ms = int((time.time() - start_time) * 1000)

            try:
                res_json = response.json()
            except Exception:
                res_json = {"raw_text": response.text}

            is_success = response.status_code == 200
            status_label = 'Success' if is_success else 'Error'
            error_msg = None if is_success else f"HTTP {response.status_code}: {response.text[:200]}"

            self._log_transaction(
                sync_type=sync_type,
                direction='OUTBOUND',
                endpoint=path,
                status=status_label,
                req_payload={},
                res_payload=res_json,
                error_msg=error_msg,
                duration_ms=duration_ms
            )

            return {
                "success": is_success,
                "status_code": response.status_code,
                "data": res_json,
                "duration_ms": duration_ms
            }
        except requests.exceptions.RequestException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_str = str(e)

            self._log_transaction(
                sync_type=sync_type,
                direction='OUTBOUND',
                endpoint=path,
                status='Error',
                req_payload={},
                res_payload={},
                error_msg=error_str,
                duration_ms=duration_ms
            )

            return {
                "success": False,
                "status_code": 500,
                "error": error_str,
                "duration_ms": duration_ms
            }

    # ==========================================
    # 1. Connectivity & Diagnostic Health
    # ==========================================
    def test_connection(self) -> Dict[str, Any]:
        """Tests credentials against STAAH by listing rooms or properties."""
        res = self.fetch_room_details()
        if res.get('success'):
            return {"connected": True, "message": "STAAH Su API connected successfully", "data": res.get('data')}
        # Fallback test with property listing
        res_prop = self.get_property_listing()
        if res_prop.get('success'):
            return {"connected": True, "message": "STAAH Su API connected successfully", "data": res_prop.get('data')}
        return {"connected": False, "message": res.get('error') or "Failed to connect to STAAH Su API"}

    def get_property_listing(self) -> Dict[str, Any]:
        """GET /SUAPI/jservice/pmsproperty"""
        return self._get('/SUAPI/jservice/pmsproperty', sync_type='Content')

    def toggle_property_status(self, is_active: bool, force_deactivation: bool = False) -> Dict[str, Any]:
        """POST /SUAPI/jservice/TogglePropertyStatus"""
        payload = {
            "hotelid": self.hotel_id,
            "is_active": 1 if is_active else 0,
            "force_deactivation": force_deactivation
        }
        return self._post('/SUAPI/jservice/TogglePropertyStatus', payload, sync_type='Content')

    # ==========================================
    # 2. Rooms & Rate Plans Mapping
    # ==========================================
    def fetch_room_details(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/roomdetails"""
        return self._post('/SUAPI/jservice/roomdetails', {"hotelid": self.hotel_id}, sync_type='Mapping')

    def sync_room_type(self, sellable_product: Dict[str, Any]) -> Dict[str, Any]:
        """POST /SUAPI/jservice/OTA_HotelRoom"""
        payload = {
            "SellableProducts": {
                "hotelid": self.hotel_id,
                "SellableProduct": [sellable_product] if isinstance(sellable_product, dict) else sellable_product
            }
        }
        return self._post('/SUAPI/jservice/OTA_HotelRoom', payload, sync_type='Mapping')

    def fetch_rate_details(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/ratedetails"""
        return self._post('/SUAPI/jservice/ratedetails', {"hotelid": self.hotel_id}, sync_type='Mapping')

    def sync_rate_plan(self, rate_plan: Dict[str, Any]) -> Dict[str, Any]:
        """POST /SUAPI/jservice/OTA_HotelRatePlan"""
        payload = {
            "RatePlans": {
                "hotelid": self.hotel_id,
                "RatePlan": [rate_plan] if isinstance(rate_plan, dict) else rate_plan
            }
        }
        return self._post('/SUAPI/jservice/OTA_HotelRatePlan', payload, sync_type='Mapping')

    def fetch_channel_mappings(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """POST /SUAPI/jservice/mappings"""
        payload = {"hotelid": self.hotel_id}
        if channel_id:
            payload["channelid"] = str(channel_id)
        return self._post('/SUAPI/jservice/mappings', payload, sync_type='Mapping')

    # ==========================================
    # 3. Availability, Rates & Inventory (ARI)
    # ==========================================
    def push_availability(self, room_availability_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        POST /SUAPI/jservice/availability
        Core ARI endpoint to push availability, stop-sell, min/max stay, and prices.
        """
        payload = {
            "hotelid": self.hotel_id,
            "room": room_availability_list
        }
        return self._post('/SUAPI/jservice/availability', payload, sync_type='Inventory')

    def push_channel_rates(self, rooms_payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST /SUAPI/jservice/channel-rates"""
        payload = {
            "hotelid": self.hotel_id,
            "rooms": rooms_payload
        }
        return self._post('/SUAPI/jservice/channel-rates', payload, sync_type='Rates')

    def push_inv_rate_control(self, inventory_control: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST /SUAPI/jservice/invratecontrol"""
        payload = {
            "hotelid": self.hotel_id,
            "inventorycontrol": inventory_control
        }
        return self._post('/SUAPI/jservice/invratecontrol', payload, sync_type='Restrictions')

    # ==========================================
    # 4. Reservations Ingest & Confirmation
    # ==========================================
    def fetch_pending_reservations(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/Reservation"""
        return self._post('/SUAPI/jservice/Reservation', {"hotelid": self.hotel_id}, sync_type='Reservations')

    def list_bookings(self, date_from: str, date_to: str) -> Dict[str, Any]:
        """
        POST /SUAPI/jservice/Bookings
        Format for date: 'MM-DD-YYYY'
        """
        payload = {
            "Su_hotelid": self.hotel_id,
            "date_from": date_from,
            "date_to": date_to
        }
        return self._post('/SUAPI/jservice/Bookings', payload, sync_type='Reservations')

    def refetch_booking(self, booking_id: str) -> Dict[str, Any]:
        """POST /SUAPI/jservice/getReservation"""
        payload = {
            "hotelid": self.hotel_id,
            "bookingid": str(booking_id)
        }
        return self._post('/SUAPI/jservice/getReservation', payload, sync_type='Reservations')

    def confirm_reservation(self, channel_booking_id: str) -> Dict[str, Any]:
        """
        POST /SUAPI/jservice/ConfirmReservation
        Confirms/Acknowledges to STAAH that PMS saved the booking.
        """
        payload = {
            "hotelid": self.hotel_id,
            "channel_bookingid": str(channel_booking_id)
        }
        return self._post('/SUAPI/jservice/ConfirmReservation', payload, sync_type='Reservations')

    def cancel_reservation(self, channel_booking_id: str) -> Dict[str, Any]:
        """POST /SUAPI/jservice/CancelReservationMeta"""
        payload = {
            "hotelid": self.hotel_id,
            "channel_bookingid": str(channel_booking_id)
        }
        return self._post('/SUAPI/jservice/CancelReservationMeta', payload, sync_type='Reservations')

    # ==========================================
    # 5. Sync Logs & Audit Queries
    # ==========================================
    def get_update_log(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/updatelog"""
        return self._post('/SUAPI/jservice/updatelog', {"hotelid": self.hotel_id}, sync_type='Mapping')

    def get_failed_updates(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/FailedUpdates"""
        return self._post('/SUAPI/jservice/FailedUpdates', {"hotelid": self.hotel_id}, sync_type='Mapping')

    def resync_failed_updates(self) -> Dict[str, Any]:
        """POST /SUAPI/jservice/resync"""
        return self._post('/SUAPI/jservice/resync', {"hotelid": self.hotel_id}, sync_type='Inventory')

    def get_inv_rate_details(self, room_id: str, rate_plan_id: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """POST /SUAPI/jservice/invratedetails"""
        payload = {
            "hotelid": self.hotel_id,
            "roomid": room_id,
            "rateplanid": rate_plan_id,
            "date": {"from": from_date, "to": to_date}
        }
        return self._post('/SUAPI/jservice/invratedetails', payload, sync_type='Inventory')

    def get_bulk_ari_details(self, from_date: str, to_date: str) -> Dict[str, Any]:
        """POST /SUAPI/jservice/BulkARIdetails"""
        payload = {
            "hotelid": self.hotel_id,
            "date": {"from": from_date, "to": to_date}
        }
        return self._post('/SUAPI/jservice/BulkARIdetails', payload, sync_type='Inventory')

    # ==========================================
    # 6. Incident Reporting & Guest Communications
    # ==========================================
    def report_incident(self, reservation_notif_id: str, report_type: str) -> Dict[str, Any]:
        """
        POST /SUAPI/jservice/reporting
        report_type options: 'cc_is_invalid' | 'cancel_reservation_invalid_cc'
        """
        payload = {
            "hotelid": self.hotel_id,
            "reservation_notif_id": str(reservation_notif_id),
            "report": report_type
        }
        return self._post('/SUAPI/jservice/reporting', payload, sync_type='Incident')

    def reply_guest_message(
        self,
        channel_id: str,
        thread_id: str,
        guest_id: str,
        booking_id: str,
        listing_id: str,
        message: str
    ) -> Dict[str, Any]:
        """POST /SUAPI/jservice/messagingAB"""
        payload = {
            "hotelid": self.hotel_id,
            "channelid": str(channel_id),
            "message": message,
            "threadid": str(thread_id),
            "guestid": str(guest_id),
            "bookingid": str(booking_id),
            "listingid": str(listing_id)
        }
        return self._post('/SUAPI/jservice/messagingAB', payload, sync_type='Incident')

    def reply_review(
        self,
        channel_id: str,
        listing_id: str,
        location_id: str,
        reply_text: str
    ) -> Dict[str, Any]:
        """POST /SUAPI/jservice/OTA_ReplyReview"""
        payload = {
            "hotelid": self.hotel_id,
            "channelid": str(channel_id),
            "replytext": reply_text,
            "listingid": str(listing_id),
            "locationid": str(location_id)
        }
        return self._post('/SUAPI/jservice/OTA_ReplyReview', payload, sync_type='Incident')
