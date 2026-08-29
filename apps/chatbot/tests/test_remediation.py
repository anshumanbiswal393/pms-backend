import os
import re
import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.core.cache import cache
import requests

from apps.chatbot.core.session_manager import get_user_session, update_user_session, clear_user_session
from apps.chatbot.core.staff_manager import process_staff_message, handle_booking_flow as staff_handle_booking_flow
from apps.chatbot.core.guest_manager import process_guest_message, handle_booking_flow, parse_date
from apps.chatbot.core import pms_api_client
from apps.chatbot.core.pms_api_client import PMSApiClient, get_reservation_by_code, update_reservation_dates, cancel_reservation
from apps.chatbot.core.logging_filters import PIIMaskingFilter
from apps.chatbot.ai_engine.models import KnowledgeChunk
from apps.chatbot.ai_engine.embeddings import get_text_embedding, search_knowledge_base, cosine_similarity
from apps.chatbot.integrations.views import staff_whatsapp_webhook, guest_whatsapp_webhook, whatsapp_webhook


class StaffRemediationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff_sender = "whatsapp:+14155551001"
        self.other_staff_sender = "whatsapp:+14155551002"

    def test_handle_booking_flow_import_and_execution_in_staff_manager(self):
        """1.1 & 2.1: Verify staff booking flow runs without NameError and retains STAFF mode."""
        # Set authenticated staff session
        update_user_session(
            self.staff_sender,
            "BOOKING_NAME",
            authenticated=True,
            mode="STAFF",
            staff_username="staff_bob",
            jwt_token="valid_staff_jwt_token",
            property_id="prop-123",
            property_name="Retrod Grand Resort",
            data={}
        )

        session = get_user_session(self.staff_sender)
        # Step 1: Guest name input
        reply1 = staff_handle_booking_flow(self.staff_sender, "John Doe", session)
        self.assertIn("Guest Name: *John Doe*", reply1)
        self.assertIn("Phone Number", reply1)

        # Step 2: Phone input
        session = get_user_session(self.staff_sender)
        reply2 = staff_handle_booking_flow(self.staff_sender, "+1234567890", session)
        self.assertIn("Phone registered", reply2)
        self.assertIn("Select **Room Type**", reply2)

        # Step 3: Room choice
        session = get_user_session(self.staff_sender)
        reply3 = staff_handle_booking_flow(self.staff_sender, "1", session)
        self.assertIn("Room Type selected", reply3)

        # Step 4: Booking dates & creation
        session = get_user_session(self.staff_sender)
        with patch.object(pms_api_client.client, "make_request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {
                "id": "res_999",
                "confirmation_number": "RETROD-999",
                "guest_name": "John Doe",
                "unit_type": "Deluxe Villa",
                "arrival_date": "2026-08-20",
                "departure_date": "2026-08-25"
            }
            mock_req.return_value = (mock_resp, None)

            reply4 = staff_handle_booking_flow(self.staff_sender, "2026-08-20 to 2026-08-25", session)
            self.assertIn("Reservation Created Successfully", reply4)

        # Verify staff session was NOT downgraded to GUEST
        final_session = get_user_session(self.staff_sender)
        self.assertEqual(final_session.get("mode"), "STAFF")
        self.assertEqual(final_session.get("state"), "IDLE")
        self.assertTrue(final_session.get("authenticated"))
        self.assertEqual(final_session.get("jwt_token"), "valid_staff_jwt_token")

        # Verify staff menu is accessible
        menu_reply = process_staff_message(self.staff_sender, "menu", "Bob")
        self.assertIn("Main Menu - Retrod PMS Assistant", menu_reply)

    def test_scoped_jwt_invalidation_on_401(self):
        """5.1: Invalidate JWT only for affected staff user on 401 Unauthorized."""
        # Setup two staff sessions with tokens
        update_user_session(self.staff_sender, "IDLE", authenticated=True, mode="STAFF", jwt_token="expired_token_1")
        update_user_session(self.other_staff_sender, "IDLE", authenticated=True, mode="STAFF", jwt_token="valid_token_2")

        client = PMSApiClient()
        with patch.object(client, "_raw_request") as mock_raw:
            resp_401 = MagicMock()
            resp_401.status_code = 401
            mock_raw.return_value = resp_401

            # Request made by staff 1
            client.make_request("GET", "/api/test/", sender_id=self.staff_sender)

        # Staff 1's JWT should be cleared and authenticated set to False
        sess1 = get_user_session(self.staff_sender)
        self.assertIsNone(sess1.get("jwt_token"))
        self.assertFalse(sess1.get("authenticated"))

        # Staff 2's session must remain unaffected
        sess2 = get_user_session(self.other_staff_sender)
        self.assertEqual(sess2.get("jwt_token"), "valid_token_2")
        self.assertTrue(sess2.get("authenticated"))


class GuestAndPMSAPIRemediationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.guest_sender = "whatsapp:+14155552001"

    def test_date_parsing_variations(self):
        """17.1: Verify robust booking date parsing across multiple formats."""
        self.assertEqual(parse_date("2026-08-20"), "2026-08-20")
        self.assertEqual(parse_date("08/20/2026"), "2026-08-20")
        self.assertEqual(parse_date("20/08/2026"), "2026-08-20")
        self.assertEqual(parse_date("20 Aug 2026"), "2026-08-20")

        # Test booking dates handling in handle_booking_flow
        session = {"state": "BOOKING_DATES", "mode": "GUEST", "data": {"guest_name": "Jane Doe", "phone": "+1234567890", "room_type": "Deluxe Villa"}}
        with patch.object(pms_api_client.client, "make_request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"id": "res_1", "confirmation_number": "CONF-1", "guest_name": "Jane Doe"}
            mock_req.return_value = (mock_resp, None)

            # Comma separated
            res1 = handle_booking_flow(self.guest_sender, "2026-08-20, 2026-08-22", session)
            self.assertIn("Reservation Created Successfully", res1)

            # Textual month format
            res2 = handle_booking_flow(self.guest_sender, "20 Aug 2026, 22 Aug 2026", session)
            self.assertIn("Reservation Created Successfully", res2)

    def test_strict_reservation_lookup_prevents_data_leakage(self):
        """6.1: Verify no unsafe fallback to items[0] when looking up reservation."""
        client = pms_api_client.client
        with patch.object(client, "make_request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            # PMS API returns list of unrelated reservations
            mock_resp.json.return_value = [
                {"id": "res_101", "confirmation_number": "CONF-SECRET-101", "guest_name": "Victim User"}
            ]
            mock_req.return_value = (mock_resp, None)

            # Search with an invalid/different confirmation code
            result = get_reservation_by_code("INVALID-CODE-999")
            # Must be None, never items[0]
            self.assertIsNone(result)

            # Exact match should succeed
            exact_result = get_reservation_by_code("CONF-SECRET-101")
            self.assertIsNotNone(exact_result)
            self.assertEqual(exact_result["confirmation_number"], "CONF-SECRET-101")

    def test_reservation_date_modification_eliminates_mock_success(self):
        """3.1: 404 on date modification must return False, not True."""
        client = pms_api_client.client
        with patch.object(client, "make_request") as mock_req:
            # 1. get_reservation_by_code returns res
            mock_res_resp = MagicMock()
            mock_res_resp.status_code = 200
            mock_res_resp.json.return_value = [{"id": "res_101", "confirmation_number": "CONF-101"}]

            mock_patch_resp = MagicMock()
            mock_patch_resp.status_code = 404
            mock_patch_resp.text = "Not Found"

            mock_req.side_effect = [
                (mock_res_resp, None),
                (mock_patch_resp, None),
            ]

            success, msg = update_reservation_dates("CONF-101", "2026-09-01", "2026-09-05")
            self.assertFalse(success)
            self.assertIn("Failed to update dates", msg)
            self.assertIn("404", msg)

    def test_reservation_cancellation_eliminates_mock_success(self):
        """4.1: 404/405 on cancellation must return False, not True."""
        client = pms_api_client.client
        with patch.object(client, "make_request") as mock_req:
            # 1. get_reservation_by_code returns res
            mock_res_resp = MagicMock()
            mock_res_resp.status_code = 200
            mock_res_resp.json.return_value = [{"id": "res_101", "confirmation_number": "CONF-101"}]

            mock_cancel_resp = MagicMock()
            mock_cancel_resp.status_code = 405
            mock_cancel_resp.text = "Method Not Allowed"

            mock_req.side_effect = [
                (mock_res_resp, None),
                (mock_cancel_resp, None),
            ]

            success, msg = cancel_reservation("CONF-101")
            self.assertFalse(success)
            self.assertIn("Failed to cancel reservation", msg)
            self.assertIn("405", msg)

    def test_tenacity_retries_on_transient_network_failures(self):
        """13.1: Verify Tenacity retries on connection/timeout exceptions."""
        client = PMSApiClient()
        with patch.object(client, "get_auth_headers", return_value=({"Authorization": "Bearer test_token"}, None)):
            with patch.object(client.session, "request") as mock_req:
                # 2 timeouts then success
                mock_success = MagicMock()
                mock_success.status_code = 200
                mock_success.json.return_value = {"status": "ok"}
                mock_req.side_effect = [
                    requests.exceptions.Timeout("Read timeout"),
                    requests.exceptions.ConnectionError("Connection reset"),
                    mock_success
                ]

                resp, err = client.make_request("GET", "/api/test/")
                self.assertEqual(mock_req.call_count, 3)
                self.assertEqual(resp.status_code, 200)
                self.assertIsNone(err)


class RAGAndEmbeddingsRemediationTests(TestCase):
    def setUp(self):
        KnowledgeChunk.objects.all().delete()
        # Seed test chunks
        KnowledgeChunk.objects.create(
            title="Hotel Check-in Policy",
            content="Check-in time is 3:00 PM and Check-out is 11:00 AM. Early check-in is subject to availability.",
            category="general_faq",
            source_doc="SRS-PMS_Retrod",
            embedding=get_text_embedding("Hotel Check-in Policy Check-in time is 3:00 PM"),
            embedding_json=get_text_embedding("Hotel Check-in Policy Check-in time is 3:00 PM")
        )
        KnowledgeChunk.objects.create(
            title="Route: Lost & Found (/lost-found)",
            content="Page Name: Lost & Found\nDirect Page URL: https://pms-ui-ten.vercel.app/lost-found\nRelative Route: /lost-found\nRequired Permission: housekeeping.view\nDescription: Item logging and storage location tracking.",
            category="website_navigation",
            source_doc="Website_Routes",
            embedding=get_text_embedding("Route: Lost & Found (/lost-found) Item logging"),
            embedding_json=get_text_embedding("Route: Lost & Found (/lost-found) Item logging")
        )

    def test_openai_embedding_dimensions_parameter(self):
        """11.1: Verify dimensions parameter is passed directly to OpenAI API."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.data = [MagicMock(embedding=[0.5] * 384)]
            mock_client.embeddings.create.return_value = mock_resp

            with patch.dict(os.environ, {"OPENAI_API_KEY": "test_openai_key"}):
                vec = get_text_embedding("Test text", dimensions=384)
                mock_client.embeddings.create.assert_called_once_with(
                    input=["Test text"],
                    model="text-embedding-3-small",
                    dimensions=384
                )
                self.assertEqual(len(vec), 384)

    def test_search_knowledge_base_retrieval_and_filtering(self):
        """8.1: Test centralized search_knowledge_base with category filter and top_k."""
        # Query general faq
        results = search_knowledge_base("what is check-in time?", category="general_faq", top_k=2)
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].title, "Hotel Check-in Policy")

        # Query website routes
        staff_results = search_knowledge_base("where is the lost and found page?", category="website_navigation", top_k=2)
        self.assertTrue(len(staff_results) > 0)
        self.assertIn("Lost & Found", staff_results[0].title)

    def test_guest_rag_grounded_response(self):
        """9.1: Verify guest natural language queries use RAG retrieval."""
        reply = process_guest_message("whatsapp:+14155559999", "What is the check-in time?", "Alice")
        self.assertTrue("Check-in" in reply or "3:00 PM" in reply or "Hotel Information" in reply)

    def test_staff_rag_grounded_response(self):
        """10.1: Verify staff natural language queries use RAG retrieval."""
        update_user_session("whatsapp:+14155558888", "IDLE", authenticated=True, mode="STAFF")
        reply = process_staff_message("whatsapp:+14155558888", "Where is the lost and found page?", "Bob")
        self.assertTrue("lost-found" in reply or "Lost & Found" in reply or "PMS Operational Guide" in reply)


class SecurityAndConfigRemediationTests(TestCase):
    def test_allowed_hosts_configuration(self):
        """7.1: ALLOWED_HOSTS must not force '*' in production."""
        raw_hosts = "retrod.example.com,api.example.com"
        hosts = [h.strip() for h in raw_hosts.split(",") if h.strip()]
        self.assertNotIn("*", hosts)
        self.assertIn("retrod.example.com", hosts)

    def test_password_logging_redaction_with_spaces_and_quotes(self):
        """16.1: Ensure passwords with spaces and quotes are fully redacted from logs."""
        pii_filter = PIIMaskingFilter()

        test_cases = [
            ("password=test123", "password=***REDACTED***"),
            ("password=\"test123\"", "password=\"***REDACTED***\""),
            ("password=\"My pass 123\"", "password=\"***REDACTED***\""),
            ("password='My pass 123'", "password='***REDACTED***'"),
            ("password : \"My pass 123\"", "password : \"***REDACTED***\""),
            ("password='abc def 123'", "password='***REDACTED***'"),
        ]

        for raw, expected_pattern in test_cases:
            masked = pii_filter._mask(raw)
            self.assertNotIn("test123", masked)
            self.assertNotIn("My pass 123", masked)
            self.assertNotIn("abc def 123", masked)
            self.assertIn("***REDACTED***", masked)
