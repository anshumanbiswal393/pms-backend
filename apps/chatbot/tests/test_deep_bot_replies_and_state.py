import os
from unittest.mock import patch
from django.test import TestCase
from apps.chatbot.core.session_manager import get_user_session, update_user_session, clear_user_session
from apps.chatbot.core.guest_manager import process_guest_message
from apps.chatbot.core.staff_manager import process_staff_message

class TestBotRepliesAndStateRobustness(TestCase):

    def setUp(self):
        self.guest_id = "whatsapp:+19997771111"
        self.staff_id = "whatsapp:+19997772222"
        clear_user_session(self.guest_id)
        clear_user_session(self.staff_id)

    def test_phrasing_variations_and_whitespace_robustness(self):
        """Verifies bot handles extra spaces, uppercase, and punctuation variations without losing intent."""
        # 1. Extra spaces and uppercase WiFi query
        res1 = process_guest_message(self.guest_id, "   WIFI ACCESS   ", "Test User")
        assert "Retrod_Guest_WiFi" in res1
        assert "WelcomeRetrod2026" in res1

        # 2. Mixed case and trailing punctuation for check-in
        res2 = process_guest_message(self.guest_id, "CHECK-IN instructions??", "Test User")
        assert any(k in res2 for k in ["Arrival Instructions", "check-in", "3 PM", "3:00 PM"])

        # 3. Status lookup with spaces and lowercase
        res3 = process_guest_message(self.guest_id, "  /status   ret-94812  ", "Test User")
        assert any(k in res3 for k in ["Booking Status Search", "Retrod PMS Booking Details", "ret-94812", "RET-94812"])

    def test_multi_turn_state_machine_continuity(self):
        """Verifies bot maintains state mid-flow across turns without unexpected state resets."""
        # Step 1: Start booking flow
        res1 = process_guest_message(self.guest_id, "book a room", "Alice Cooper")
        assert "Full Name" in res1
        sess1 = get_user_session(self.guest_id)
        assert sess1.get("state") == "BOOKING_NAME"

        # Step 2: Provide Full Name
        res2 = process_guest_message(self.guest_id, "Alice Cooper", "Alice Cooper")
        assert "Phone Number" in res2
        sess2 = get_user_session(self.guest_id)
        assert sess2.get("state") == "BOOKING_PHONE"
        assert sess2.get("data", {}).get("guest_name") == "Alice Cooper"

        # Step 3: Provide Phone Number with leading spaces
        res3 = process_guest_message(self.guest_id, "  +15559998888  ", "Alice Cooper")
        assert "Room Type" in res3
        sess3 = get_user_session(self.guest_id)
        assert sess3.get("state") == "BOOKING_ROOM"
        assert sess3.get("data", {}).get("phone") == "+15559998888"

        # Step 4: Provide Room Option (1 for Deluxe Villa)
        # Verify choice 1 does NOT trigger Wi-Fi menu but progresses booking flow!
        res4 = process_guest_message(self.guest_id, "1", "Alice Cooper")
        assert "Deluxe Villa" in res4
        assert "Check-in & Check-out Dates" in res4
        sess4 = get_user_session(self.guest_id)
        assert sess4.get("state") == "BOOKING_DATES"

    def test_feedback_flow_state_continuity(self):
        """Verifies feedback rating flow maintains state and does not hallucinate output."""
        # Step 1: Trigger vacating request
        res1 = process_guest_message(self.guest_id, "I am checking out of room 305 now", "Bob Miller")
        assert "1 to 5 Stars" in res1
        sess1 = get_user_session(self.guest_id)
        assert sess1.get("state") == "FEEDBACK_RATING"

        # Step 2: Submit 5 star rating (choice 5 does NOT trigger new reservation flow!)
        res2 = process_guest_message(self.guest_id, "5", "Bob Miller")
        assert "Rating Registered" in res2
        sess2 = get_user_session(self.guest_id)
        assert sess2.get("state") == "FEEDBACK_COMMENT"
        assert sess2.get("data", {}).get("rating") == "5"

        # Step 3: Submit text comment
        res3 = process_guest_message(self.guest_id, "Great stay and awesome breakfast!", "Bob Miller")
        assert "Thank You for Your Feedback" in res3
        sess3 = get_user_session(self.guest_id)
        assert sess3.get("state") == "IDLE"

    def test_zero_hallucination_and_pms_data_retrieval(self):
        """Verifies unknown booking codes return factual search results without hallucinating fake guest data."""
        res = process_guest_message(self.guest_id, "RET-0000000", "QA User")
        assert "could not locate an active reservation" in res
        assert "John Doe" not in res
        assert "Alice" not in res

    def test_staff_authentication_state_isolation(self):
        """Verifies staff login state machine is completely decoupled from guest sessions."""
        update_user_session(self.guest_id, "IDLE", mode="GUEST")
        
        # Staff initiates login
        res1 = process_staff_message(self.staff_id, "/login", "Staff User")
        assert "Staff Username" in res1
        staff_sess = get_user_session(self.staff_id)
        assert staff_sess.get("mode") == "STAFF"
        assert staff_sess.get("state") == "LOGIN_USERNAME"

        # Guest session remains isolated in GUEST mode
        guest_sess = get_user_session(self.guest_id)
        assert guest_sess.get("mode") == "GUEST"
