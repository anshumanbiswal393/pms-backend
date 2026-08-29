from django.core.management.base import BaseCommand
from apps.booking.models import Booking
from apps.booking.notifications import send_booking_invoice_email, send_booking_invoice_sms

class Command(BaseCommand):
    help = 'Manually send or resend email and SMS booking invoice to a guest'

    def add_arguments(self, parser):
        parser.add_argument('--ref', type=str, help='Booking Reference ID (e.g. RETROD-XYZ-12345)')
        parser.add_argument('--email', type=str, help='Recipient Email address to send invoice to')
        parser.add_argument('--phone', type=str, help='Recipient Mobile phone number')

    def handle(self, *args, **options):
        ref = options.get('ref')
        override_email = options.get('email')
        override_phone = options.get('phone')

        booking = None
        if ref:
            booking = Booking.objects.filter(booking_reference__iexact=ref).first()
            if not booking:
                self.stderr.write(self.style.ERROR(f"Booking reference '{ref}' not found in database."))

        if booking:
            hotel_name = booking.hotel.name if booking.hotel else 'Retrod Hotel'
            guest = booking.guest
            guest_name = guest.full_name or f"{guest.first_name} {guest.last_name}".strip() if guest else 'Valued Guest'
            email = override_email or (guest.email if guest else None)
            phone = override_phone or (guest.phone if guest else None)
            check_in = str(booking.check_in)
            check_out = str(booking.check_out)
            nights = booking.total_nights
            total = float(booking.grand_total)
            ref_code = booking.booking_reference
        else:
            self.stdout.write(self.style.WARNING("No existing booking reference supplied. Using test notification payload."))
            hotel_name = "Grand Palace Hotel"
            guest_name = "Manual Test Guest"
            email = override_email or "guest@example.com"
            phone = override_phone or "+919876543210"
            check_in = "2026-08-10"
            check_out = "2026-08-12"
            nights = 2
            total = 4500.00
            ref_code = ref or "RETROD-MANUAL-TEST"

        booking_data = {
            'hotel_name': hotel_name,
            'booking_reference': ref_code,
            'check_in': check_in,
            'check_out': check_out,
            'total_nights': nights,
            'grand_total': total,
            'room_price': round(total * 0.90, 2),
            'tax_and_fees': round(total * 0.10, 2),
            'room_name': 'Deluxe Room'
        }

        guest_data = {
            'full_name': guest_name,
            'email': email,
            'phone': phone
        }

        self.stdout.write(self.style.MIGRATE_HEADING(f"\n--- Triggering Manual Email & SMS Dispatch ---"))
        self.stdout.write(f"Recipient Email: {email}")
        self.stdout.write(f"Recipient Phone: {phone}")
        self.stdout.write(f"Booking Reference: {ref_code}\n")

        email_ok = send_booking_invoice_email(booking_data, guest_data)
        sms_ok = send_booking_invoice_sms(booking_data, guest_data)

        if email_ok:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] Email dispatch completed successfully."))
        else:
            self.stdout.write(self.style.ERROR("[FAILED] Email dispatch failed or missing email address."))

        if sms_ok:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] SMS dispatch completed successfully."))
        else:
            self.stdout.write(self.style.ERROR("[FAILED] SMS dispatch failed or missing phone number."))
