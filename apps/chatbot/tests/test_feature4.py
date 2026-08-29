import os
from django.test import TestCase
from django.core.cache import cache
from apps.chatbot.core.guest_manager import process_guest_message
from apps.chatbot.core.session_manager import get_user_session, update_user_session
from apps.chatbot.integrations.notifications import (
    send_booking_confirmation_reminder,
    send_arrival_instructions,
    send_hotel_wifi_details
)

class Feature4Tests(TestCase):
    def setUp(self):
        cache.clear()

    def test_feature4_button_interception_wifi(self):
        sender = "whatsapp:+15550001111"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        response = process_guest_message(sender, "BTN_WIFI_DETAILS", "Alex Guest")
        self.assertIn("Retrod Hotel Complimentary Wi-Fi Access", response)
        self.assertIn("Retrod_Guest_WiFi", response)
        self.assertIn("WelcomeRetrod2026", response)

    def test_feature4_button_interception_arrival(self):
        sender = "whatsapp:+15550001112"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        response = process_guest_message(sender, "BTN_ARRIVAL_GUIDE", "Alex Guest")
        self.assertIn("Arrival Instructions & Guest Guide", response)
        self.assertIn("123 Hospitality Way", response)

    def test_feature4_button_interception_status(self):
        sender = "whatsapp:+15550001113"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        response = process_guest_message(sender, "BTN_CHECK_STATUS", "Alex Guest")
        self.assertIn("My Booking Status Inquiry", response)
        self.assertIn("Booking Confirmation Code", response)

    def test_feature4_button_interception_menu(self):
        sender = "whatsapp:+15550001114"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        response = process_guest_message(sender, "BTN_GUEST_MENU", "Alex Guest")
        self.assertIn("Welcome Hotel Guest, Alex Guest", response)

    def test_feature4_notification_helpers_fallback(self):
        res_conf = send_booking_confirmation_reminder("whatsapp:+15550002222", "Alex", "RET-1001", "Deluxe Suite", "2026-09-01", "2026-09-05")
        res_arr = send_arrival_instructions("whatsapp:+15550002222", "Alex")
        res_wifi = send_hotel_wifi_details("whatsapp:+15550002222", "Alex")
        
        self.assertIsInstance(res_conf, bool)
        self.assertIsInstance(res_arr, bool)
        self.assertIsInstance(res_wifi, bool)

    def test_regression_staff_login(self):
        sender = "whatsapp:+15550003333"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        response = process_guest_message(sender, "/login", "Staff User")
        self.assertIn("Retrod PMS Staff Authentication", response)
        
        session = get_user_session(sender)
        self.assertEqual(session.get("mode"), "STAFF")
        self.assertEqual(session.get("state"), "LOGIN_USERNAME")

    def test_booking_status_lookup_flow(self):
        sender = "whatsapp:+15550004444"
        update_user_session(sender, "IDLE", mode="GUEST")
        
        # 1. Tap My Booking button
        resp1 = process_guest_message(sender, "BTN_CHECK_STATUS", "Test Guest")
        self.assertIn("Booking Confirmation Code", resp1)
        
        # 2. Provide confirmation code
        resp2 = process_guest_message(sender, "RET-94812", "Test Guest")
        self.assertTrue("Booking Status Search" in resp2 or "Retrod PMS Booking Details" in resp2)
