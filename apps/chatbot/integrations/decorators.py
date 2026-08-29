import logging
import os
from functools import wraps
from django.http import HttpResponseForbidden, HttpRequest
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)

def validate_twilio_signature(view_func):
    """
    Decorator to validate incoming webhook requests from Twilio using X-Twilio-Signature.
    Bypasses validation if DEBUG=True or TWILIO_SKIP_SIGNATURE_VALIDATION=True (for local dev testing).
    Rejects all unauthenticated/forged requests with HTTP 403 Forbidden.
    """
    @wraps(view_func)
    def _wrapped_view(request: HttpRequest, *args, **kwargs):
        # Skip validation only on explicit opt-out
        if os.getenv("TWILIO_SKIP_SIGNATURE_VALIDATION", "False").lower() == "true":
            return view_func(request, *args, **kwargs)

        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        if not auth_token:
            logger.error("Twilio Signature Validation Error: TWILIO_AUTH_TOKEN is missing!")
            return HttpResponseForbidden("Twilio auth token configuration missing.")

        signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
        if not signature:
            logger.warning("Rejected webhook request: Missing X-Twilio-Signature header!")
            return HttpResponseForbidden("Missing X-Twilio-Signature header.")

        # Reconstruct absolute request URL (accounting for HTTPS reverse proxies)
        url = request.build_absolute_uri()
        forwarded_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "").lower()
        if forwarded_proto == "https" or request.is_secure():
            url = url.replace("http://", "https://")

        validator = RequestValidator(auth_token)
        post_data = request.POST.dict()

        # Try exact URL, stripped trailing slash, and added trailing slash to handle reverse proxy normalization
        is_valid = (
            validator.validate(url, post_data, signature) or
            validator.validate(url.rstrip('/'), post_data, signature) or
            validator.validate(url.rstrip('/') + '/', post_data, signature)
        )

        if not is_valid:
            logger.error(f"Security Alert: Rejected invalid Twilio signature for URL '{url}'!")
            return HttpResponseForbidden("Invalid Twilio Request Signature.")

        return view_func(request, *args, **kwargs)

    return _wrapped_view
