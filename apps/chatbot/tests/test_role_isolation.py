import os
from django.test import TestCase, RequestFactory
from django.core.cache import cache
from apps.chatbot.core.session_manager import get_user_session, update_user_session
from apps.chatbot.core.staff_manager import process_staff_message
from apps.chatbot.core.guest_manager import process_guest_message
from apps.chatbot.integrations.views import staff_whatsapp_webhook, guest_whatsapp_webhook, whatsapp_webhook

class RoleIsolationTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.staff_sender = "whatsapp:+14155550001"
        self.guest_sender = "whatsapp:+14155550002"
        os.environ["DEBUG"] = "True"
        cache.clear()

    def test_guest_mode_welcome(self):
        reply = process_guest_message(self.guest_sender, "hi", "Alice Guest")
        self.assertIn("Welcome Hotel Guest, Alice Guest!", reply)

    def test_staff_mode_isolation(self):
        reply = process_staff_message(self.staff_sender, "/login", "Bob Staff")
        self.assertIn("Staff Authentication", reply)
        self.assertIn("Staff Username or Email", reply)

    def test_session_namespace_isolation(self):
        update_user_session(self.guest_sender, "IDLE", mode="GUEST")
        update_user_session(self.staff_sender, "LOGIN_USERNAME", mode="STAFF")

        sess_guest = get_user_session(self.guest_sender)
        sess_staff = get_user_session(self.staff_sender)

        self.assertEqual(sess_guest.get("mode"), "GUEST")
        self.assertEqual(sess_staff.get("mode"), "STAFF")
        self.assertEqual(sess_staff.get("state"), "LOGIN_USERNAME")

    def test_dedicated_webhooks(self):
        req_staff = self.factory.post("/api/v1/integrations/whatsapp/staff/", {"From": self.staff_sender, "Body": "/login", "ProfileName": "Bob"})
        resp_staff = staff_whatsapp_webhook(req_staff)
        self.assertEqual(resp_staff.status_code, 200)
        self.assertIn("Staff Authentication", resp_staff.content.decode("utf-8"))

        req_guest = self.factory.post("/api/v1/integrations/whatsapp/guest/", {"From": self.guest_sender, "Body": "hi", "ProfileName": "Alice"})
        resp_guest = guest_whatsapp_webhook(req_guest)
        self.assertEqual(resp_guest.status_code, 200)
        self.assertIn("Welcome Hotel Guest", resp_guest.content.decode("utf-8"))

    def test_unified_sandbox_router(self):
        req1 = self.factory.post("/api/v1/integrations/whatsapp/webhook/", {"From": self.guest_sender, "Body": "guest", "ProfileName": "Alice"})
        resp1 = whatsapp_webhook(req1)
        self.assertIn("Welcome Hotel Guest", resp1.content.decode("utf-8"))

        req2 = self.factory.post("/api/v1/integrations/whatsapp/webhook/", {"From": self.staff_sender, "Body": "/login", "ProfileName": "Bob"})
        resp2 = whatsapp_webhook(req2)
        self.assertIn("Staff Authentication", resp2.content.decode("utf-8"))
