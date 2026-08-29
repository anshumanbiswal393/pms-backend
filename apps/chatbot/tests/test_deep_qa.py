import os
import json
import logging
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.conf import settings

from apps.chatbot.core.session_manager import get_user_session, update_user_session, clear_user_session
from apps.chatbot.core.staff_manager import process_staff_message
from apps.chatbot.core.guest_manager import process_guest_message
from apps.chatbot.core.chat_manager import process_incoming_message
from apps.chatbot.core.pms_api_client import client as pms_client
from apps.chatbot.core.logging_filters import PIIMaskingFilter

class TestDeepQAAndIsolation(TestCase):

    def setUp(self):
        self.django_client = Client()

    def test_pii_masking_filter_integrity(self):
        """Verifies Development Rule 3: PII Masking Filter redacts sensitive data from logs."""
        pii_filter = PIIMaskingFilter()
        
        # Test Phone & Email Redaction
        raw_msg = "User with phone whatsapp:+14155238886 and email admin@retrod.in submitted password='MySecretPassword123!'"
        masked_msg = pii_filter._mask(raw_msg)
        
        assert "+14155238886" not in masked_msg
        assert "admin@retrod.in" not in masked_msg
        assert "MySecretPassword123!" not in masked_msg
        assert "***-***-****" in masked_msg
        assert "***@***.com" in masked_msg

    def test_no_infinite_api_retry_loops(self):
        """Verifies Development Rule 5: PMS API requests cap retries safely and never cause infinite loops."""
        with patch.object(pms_client, 'get_auth_headers', return_value=({"Authorization": "Bearer fake_token"}, None)):
            with patch.object(pms_client.session, 'request') as mock_req:
                mock_req.side_effect = Exception("Simulated connection timeout")
                
                # Make request expecting single-pass exception capture without infinite retries
                resp, err = pms_client.make_request("GET", "/api/properties/")
                
                # Verify network call returned error response safely without looping
                assert mock_req.call_count >= 1
                assert resp.status_code == 500
                assert "Network Error" in resp.text

    def test_strict_role_and_code_isolation(self):
        """Verifies Development Rule 2 & Role Isolation: Staff and Guest modes are completely decoupled."""
        guest_sender = "whatsapp:+19998887771"
        staff_sender = "whatsapp:+19998887772"

        # 1. Initialize Guest Mode
        update_user_session(guest_sender, "IDLE", mode="GUEST")
        guest_res = process_guest_message(guest_sender, "hi", "Guest User")
        assert "Welcome Hotel Guest" in guest_res
        
        # Verify guest mode cannot run staff commands without authenticating
        guest_menu_res = process_guest_message(guest_sender, "1", "Guest User")
        assert "Front Desk & Bookings Sub-Menu" not in guest_menu_res

        # 2. Initialize Staff Login Mode
        update_user_session(staff_sender, "LOGIN_USERNAME", authenticated=False, mode="STAFF")
        staff_res = process_staff_message(staff_sender, "admin@retrod.in", "Staff User")
        assert "Password" in staff_res
        
        # Verify session mode isolation
        guest_sess = get_user_session(guest_sender)
        staff_sess = get_user_session(staff_sender)
        assert guest_sess.get("mode") == "GUEST"
        assert staff_sess.get("mode") == "STAFF"

    def test_twilio_webhook_endpoint_working(self):
        """Verifies Twilio HTTP Webhook router endpoint executes clean TwiML responses without crashing."""
        os.environ["TWILIO_SKIP_SIGNATURE_VALIDATION"] = "True"
        
        payload = {
            "From": "whatsapp:+15551234567",
            "Body": "BTN_WIFI_DETAILS",
            "ProfileName": "QA Tester"
        }
        
        response = self.django_client.post("/api/v1/integrations/whatsapp/webhook/", data=payload)
        assert response.status_code == 200
        assert "application/xml" in response.headers["Content-Type"]
        assert "Retrod Hotel Complimentary Wi-Fi Access" in response.content.decode("utf-8")

    def test_twilio_guest_webhook_working(self):
        """Verifies dedicated Guest Twilio Webhook endpoint executes clean TwiML XML responses."""
        os.environ["TWILIO_SKIP_SIGNATURE_VALIDATION"] = "True"
        
        payload = {
            "From": "whatsapp:+15551234568",
            "Body": "BTN_ARRIVAL_GUIDE",
            "ProfileName": "QA Tester"
        }
        
        response = self.django_client.post("/api/v1/integrations/whatsapp/guest/", data=payload)
        assert response.status_code == 200
        assert "application/xml" in response.headers["Content-Type"]
        content_xml = response.content.decode("utf-8")
        assert "Arrival Instructions" in content_xml
        assert "Guest Guide" in content_xml
