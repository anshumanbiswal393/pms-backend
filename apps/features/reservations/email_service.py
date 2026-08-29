import logging
import threading
from decimal import Decimal
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from apps.features.reservations.models import Reservation
from apps.features.reservations.invoice_pdf import generate_reservation_invoice_pdf

logger = logging.getLogger(__name__)

def _send_email_thread(reservation_id):
    try:
        reservation = Reservation.objects.select_related(
            'primary_guest', 'property', 'reservation_source'
        ).prefetch_related(
            'room_allocations__inventory_unit_type',
            'room_allocations__inventory_unit',
            'room_allocations__rate_snapshots__rate_plan__default_meal_plan',
            'services',
            'packages'
        ).filter(id=reservation_id).first()
        if not reservation:
            logger.warning(f"[EMAIL SERVICE] Reservation {reservation_id} not found.")
            return

        # 1. Resolve recipient email
        guest = reservation.primary_guest
        guest_email = None
        guest_name = "Valued Guest"
        if guest:
            guest_name = f"{guest.first_name} {guest.last_name}".strip() or "Valued Guest"
            contact = guest.contacts.filter(is_primary=True).first() or guest.contacts.first()
            if contact and contact.email:
                guest_email = contact.email

        # If email not on guest profile, check snapshot
        if not guest_email and reservation.notes:
            pass

        if not guest_email:
            logger.info(f"[EMAIL SERVICE] No guest email found for reservation {reservation.confirmation_number}. Skipping email dispatch.")
            return

        # 2. Generate PDF Invoice Attachment
        try:
            pdf_bytes = generate_reservation_invoice_pdf(reservation)
        except Exception as e:
            logger.error(f"[EMAIL SERVICE] Error generating PDF invoice for {reservation.confirmation_number}: {e}")
            pdf_bytes = None

        property_name = reservation.property.name if reservation.property else "Retrod Hospitality"
        subject = f"Booking Confirmation & Invoice: {reservation.confirmation_number} - {property_name}"
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'reservations@retrodpms.com')

        arrival_str = reservation.arrival_date.strftime('%d %b %Y') if reservation.arrival_date else "N/A"
        departure_str = reservation.departure_date.strftime('%d %b %Y') if reservation.departure_date else "N/A"
        
        # Calculate nights
        nights = 1
        if reservation.arrival_date and reservation.departure_date:
            nights = max(1, (reservation.departure_date - reservation.arrival_date).days)

        room_types = ", ".join(list(set([a.inventory_unit_type.name for a in reservation.room_allocations.all() if a.inventory_unit_type]))) or "Standard Suite"

        subtotal = reservation.total_amount or Decimal("0.00")
        tax_amt = reservation.tax_amount or Decimal("0.00")
        discount_amt = reservation.discount_amount or Decimal("0.00")
        grand_total = (subtotal + tax_amt) - discount_amt
        paid_amt = reservation.paid_amount or Decimal("0.00")
        balance_amt = reservation.balance_amount or Decimal("0.00")

        # 3. HTML Content
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
                .header {{ background: #0f766e; color: #ffffff; padding: 28px 24px; text-align: center; }}
                .header h1 {{ margin: 0 0 6px; font-size: 22px; font-weight: 700; }}
                .header p {{ margin: 0; font-size: 13px; opacity: 0.9; }}
                .content {{ padding: 24px; }}
                .greeting {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #0f766e; }}
                .intro {{ font-size: 14px; line-height: 1.5; color: #475569; margin-bottom: 20px; }}
                .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
                .card-title {{ font-size: 13px; font-weight: 700; color: #0f766e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
                .grid {{ display: table; width: 100%; }}
                .row {{ display: table-row; }}
                .label {{ display: table-cell; padding: 4px 8px 4px 0; font-size: 13px; color: #64748b; font-weight: 500; width: 40%; }}
                .value {{ display: table-cell; padding: 4px 0; font-size: 13px; color: #1e293b; font-weight: 600; }}
                .highlight-row {{ border-top: 1px dashed #cbd5e1; margin-top: 6px; padding-top: 6px; }}
                .notice {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px; font-size: 13px; color: #166534; margin-bottom: 20px; line-height: 1.4; }}
                .footer {{ background: #f1f5f9; padding: 16px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{property_name}</h1>
                    <p>Reservation Confirmation & Invoice</p>
                </div>
                <div class="content">
                    <div class="greeting">Dear {guest_name},</div>
                    <div class="intro">
                        Thank you for booking with <b>{property_name}</b>. We are delighted to confirm your upcoming stay.
                        Your official Tax Invoice & Booking Voucher is attached to this email as a PDF.
                    </div>

                    <div class="card">
                        <div class="card-title">Reservation Summary</div>
                        <div class="grid">
                            <div class="row">
                                <div class="label">Confirmation Number:</div>
                                <div class="value" style="color: #0f766e; font-size: 14px;">{reservation.confirmation_number}</div>
                            </div>
                            <div class="row">
                                <div class="label">Check-In Date:</div>
                                <div class="value">{arrival_str} ({reservation.check_in_time or '12:00 PM'})</div>
                            </div>
                            <div class="row">
                                <div class="label">Check-Out Date:</div>
                                <div class="value">{departure_str} ({reservation.check_out_time or '11:00 AM'})</div>
                            </div>
                            <div class="row">
                                <div class="label">Duration of Stay:</div>
                                <div class="value">{nights} Night(s)</div>
                            </div>
                            <div class="row">
                                <div class="label">Room Category:</div>
                                <div class="value">{room_types}</div>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-title">Payment & Billing Details</div>
                        <div class="grid">
                            <div class="row">
                                <div class="label">Base Tariff:</div>
                                <div class="value">₹{subtotal:,.2f}</div>
                            </div>
                            <div class="row">
                                <div class="label">Taxes & GST:</div>
                                <div class="value">+ ₹{tax_amt:,.2f}</div>
                            </div>
                            <div class="row">
                                <div class="label">Grand Total:</div>
                                <div class="value" style="font-size: 15px; color: #0f766e;">₹{grand_total:,.2f}</div>
                            </div>
                            <div class="row">
                                <div class="label">Deposit Paid:</div>
                                <div class="value">₹{paid_amt:,.2f}</div>
                            </div>
                            <div class="row">
                                <div class="label" style="font-weight: 700;">Balance Due at Desk:</div>
                                <div class="value" style="font-weight: 700; color: {'#dc2626' if balance_amt > 0 else '#059669'};">₹{balance_amt:,.2f}</div>
                            </div>
                        </div>
                    </div>

                    <div class="notice">
                        📎 <b>Attached Document:</b> Please find your attached <b>Tax Invoice & Confirmation Voucher PDF</b> for complete breakdown, payment details, and check-in requirements.
                    </div>
                </div>
                <div class="footer">
                    © {timezone.now().year} {property_name}. All rights reserved.<br>
                    Need assistance? Contact our front desk directly at {getattr(reservation.property, 'contact_phone', '') or getattr(reservation.property, 'contact_email', '') or 'front desk'}.
                </div>
            </div>
        </body>
        </html>
        """

        plain_text = f"""
Dear {guest_name},

Thank you for choosing {property_name}. Your reservation is confirmed!

Confirmation Number: {reservation.confirmation_number}
Check-In: {arrival_str} ({reservation.check_in_time or '12:00 PM'})
Check-Out: {departure_str} ({reservation.check_out_time or '11:00 AM'})
Room: {room_types}
Grand Total: ₹{grand_total:,.2f}
Deposit Paid: ₹{paid_amt:,.2f}
Balance Due: ₹{balance_amt:,.2f}

Please check the attached PDF for your complete Invoice and Booking Voucher.

Warm regards,
{property_name} Team
        """

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=from_email,
            to=[guest_email]
        )
        msg.attach_alternative(html_body, "text/html")

        if pdf_bytes:
            filename = f"Invoice-{reservation.confirmation_number}.pdf"
            msg.attach(filename, pdf_bytes, "application/pdf")

        msg.send(fail_silently=False)
        logger.info(f"[EMAIL SERVICE] Confirmation email with PDF invoice dispatched successfully to {guest_email} for reservation {reservation.confirmation_number}.")
    except Exception as e:
        logger.error(f"[EMAIL SERVICE] Failed to send reservation confirmation email for {reservation_id}: {e}")

def send_reservation_confirmation_email_async(reservation_id):
    """
    Triggers asynchronous sending of the reservation confirmation email with PDF invoice attachment.
    """
    thread = threading.Thread(target=_send_email_thread, args=(reservation_id,), daemon=True)
    thread.start()
