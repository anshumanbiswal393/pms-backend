import logging
import re


class PIIMaskingFilter(logging.Filter):
    """
    Filter that automatically redacts Personally Identifiable Information (PII)
    such as phone numbers, email addresses, passwords, and JWT tokens from application logs.

    Works correctly with both f-string interpolated messages (where PII is already
    baked into record.msg) and %-style format messages (where PII is in record.args).
    """
    PHONE_REGEX = re.compile(r'whatsapp:\+?\d{7,15}|\+?\d{1,4}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
    EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    JWT_REGEX = re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}')
    PASSWORD_REGEX = re.compile(
        r'(?i)(password[\'"]?\s*[:=]\s*)'
        r'(".*?"|\'.*?\'|[^\s,;\'"}{)]+)'
    )

    def _mask(self, text: str) -> str:
        """Apply all PII redaction patterns to a string."""
        if not isinstance(text, str):
            return text
        text = self.JWT_REGEX.sub('***JWT_REDACTED***', text)
        text = self.PASSWORD_REGEX.sub(r'\1***REDACTED***', text)
        text = self.EMAIL_REGEX.sub('***@***.com', text)
        text = self.PHONE_REGEX.sub('***-***-****', text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Always mask the pre-interpolated message string (handles f-strings)
        if isinstance(record.msg, str):
            record.msg = self._mask(record.msg)

        # Also mask format arguments if %-style logging is used
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._mask(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._mask(a) if isinstance(a, str) else a for a in record.args)

        return True
