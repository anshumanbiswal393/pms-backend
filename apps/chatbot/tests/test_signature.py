import os
from django.test import TestCase, RequestFactory
from django.http import HttpResponseForbidden
from apps.chatbot.integrations.decorators import validate_twilio_signature

class TwilioSignatureTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_missing_signature_rejected(self):
        @validate_twilio_signature
        def dummy_view(request):
            return "OK"

        os.environ["DEBUG"] = "False"
        os.environ["TWILIO_SKIP_SIGNATURE_VALIDATION"] = "False"
        os.environ["TWILIO_AUTH_TOKEN"] = "testauthtoken123456"

        request = self.factory.post("/api/v1/integrations/whatsapp/webhook/", {"Body": "hi"})
        response = dummy_view(request)
        self.assertIsInstance(response, HttpResponseForbidden)

    def test_debug_mode_bypasses_signature(self):
        @validate_twilio_signature
        def dummy_view(request):
            return "OK"

        os.environ["DEBUG"] = "True"
        request = self.factory.post("/api/v1/integrations/whatsapp/webhook/", {"Body": "hi"})
        response = dummy_view(request)
        self.assertEqual(response, "OK")
