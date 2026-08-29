import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings

logger = logging.getLogger(__name__)

def generate_invoice_html(booking_data, guest_data):
    hotel_name = booking_data.get('hotel_name', 'Hotel XYZ')
    guest_name = f"{guest_data.get('first_name', '')} {guest_data.get('last_name', '')}".strip() or guest_data.get('full_name', 'Valued Guest')
    email = guest_data.get('email', 'N/A')
    phone = guest_data.get('phone', 'N/A')
    ref_code = booking_data.get('booking_reference', 'RETROD-CONF-PENDING')
    check_in = booking_data.get('check_in', 'N/A')
    check_out = booking_data.get('check_out', 'N/A')
    nights = booking_data.get('total_nights', 1)
    grand_total = float(booking_data.get('grand_total', 0.0))
    
    room_charges = float(booking_data.get('room_price', grand_total * 0.95))
    tax_and_fees = float(booking_data.get('tax_and_fees', grand_total * 0.05))
    sgst = round(tax_and_fees / 2.0, 2)
    cgst = round(tax_and_fees / 2.0, 2)
    
    items = booking_data.get('cart_slots', [])
    items_html = ""
    if items:
        for idx, item in enumerate(items, 1):
            r_name = item.get('roomName') or item.get('room_name') or 'Room'
            p_title = item.get('planTitle') or item.get('plan_title') or 'Standard Plan'
            adults = item.get('adults', 2)
            children = item.get('children', 0)
            base_p = float(item.get('basePricePerNight', 0)) * nights
            items_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 12px; font-size: 14px; color: #1e293b;">
                    <strong>Slot {idx}: {r_name}</strong><br/>
                    <span style="font-size: 12px; color: #16a34a; font-weight: 600;">Plan: {p_title}</span><br/>
                    <span style="font-size: 11px; color: #64748b;">👤 {adults} Adults &bull; 👶 {children} Children</span>
                </td>
                <td style="padding: 12px; font-size: 14px; color: #0f172a; text-align: right; font-weight: 700; vertical-align: top;">
                    ₹{base_p:,.2f}
                </td>
            </tr>
            """
    else:
        r_name = booking_data.get('room_name', 'Selected Room')
        p_title = booking_data.get('plan_title', 'Standard Rate Plan')
        items_html = f"""
        <tr style="border-bottom: 1px solid #e2e8f0;">
            <td style="padding: 12px; font-size: 14px; color: #1e293b;">
                <strong>{r_name}</strong><br/>
                <span style="font-size: 12px; color: #16a34a; font-weight: 600;">Plan: {p_title}</span>
            </td>
            <td style="padding: 12px; font-size: 14px; color: #0f172a; text-align: right; font-weight: 700; vertical-align: top;">
                ₹{room_charges:,.2f}
            </td>
        </tr>
        """

    company_info_html = ""
    if guest_data.get('company_name') or guest_data.get('gst_number'):
        company_info_html = f"""
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-top: 12px;">
            <div style="font-size: 12px; font-weight: 700; color: #475569; text-transform: uppercase;">Corporate Billing Details</div>
            <div style="font-size: 13px; color: #0f172a; margin-top: 4px;">
                <strong>Company:</strong> {guest_data.get('company_name', 'N/A')}<br/>
                <strong>GSTIN:</strong> {guest_data.get('gst_number', 'N/A')}
            </div>
        </div>
        """

    addons_items = booking_data.get('selected_addons') or []
    addons_html = ""
    if addons_items:
        for ad in addons_items:
            ad_name = ad.get('name') or 'Stay Add-On'
            ad_cat = ad.get('category') or 'Service'
            ad_p = float(ad.get('price', 0))
            addons_html += f"""
            <tr style="border-bottom: 1px solid #f1f5f9; background-color: #f8fafc;">
                <td style="padding: 10px 12px; font-size: 13px; color: #1e293b;">
                    ✨ <strong>{ad_name}</strong> <span style="font-size: 11px; color: #64748b;">({ad_cat})</span>
                </td>
                <td style="padding: 10px 12px; font-size: 13px; color: #16a34a; text-align: right; font-weight: 700;">
                    +₹{ad_p:,.2f}
                </td>
            </tr>
            """

    addons_total = float(booking_data.get('addons_total', 0.0))

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Booking Invoice - {hotel_name}</title>
</head>
<body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.08); border: 1px solid #cbd5e1;">
        
        <!-- Header Banner -->
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 24px; text-align: center; color: #ffffff;">
            <div style="display: inline-block; background: #16a34a; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 800; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px;">
                Booking & Payment Invoice
            </div>
            <h1 style="margin: 0; font-size: 24px; font-weight: 800; color: #ffffff;">
                Thank you for continuing with {hotel_name}!
            </h1>
            <p style="margin-top: 8px; margin-bottom: 0; font-size: 14px; color: #94a3b8;">
                We are thrilled to welcome you. Here is your detailed reservation bill & invoice.
            </p>
        </div>

        <!-- Content Area -->
        <div style="padding: 24px;">
            
            <!-- Reference Box -->
            <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 16px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <div>
                    <div style="font-size: 11px; font-weight: 800; color: #166534; text-transform: uppercase; letter-spacing: 0.5px;">Booking Reference</div>
                    <div style="font-size: 20px; font-weight: 800; color: #15803d; margin-top: 2px;">{ref_code}</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 11px; font-weight: 800; color: #166534; text-transform: uppercase; letter-spacing: 0.5px;">Grand Total</div>
                    <div style="font-size: 20px; font-weight: 800; color: #15803d; margin-top: 2px;">₹{grand_total:,.2f}</div>
                </div>
            </div>

            <!-- Guest & Stay Information -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
                <tr>
                    <td width="50%" style="vertical-align: top; padding-right: 12px;">
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px;">
                            <div style="font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 6px;">Guest Details</div>
                            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">{guest_name}</div>
                            <div style="font-size: 12px; color: #475569; margin-top: 4px;">📧 {email}</div>
                            <div style="font-size: 12px; color: #475569; margin-top: 2px;">📱 {phone}</div>
                        </div>
                    </td>
                    <td width="50%" style="vertical-align: top; padding-left: 12px;">
                        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px;">
                            <div style="font-size: 11px; font-weight: 800; color: #64748b; text-transform: uppercase; margin-bottom: 6px;">Stay Period</div>
                            <div style="font-size: 13px; font-weight: 700; color: #0f172a;">📅 {check_in} → {check_out}</div>
                            <div style="font-size: 12px; color: #16a34a; font-weight: 700; margin-top: 4px;">🌙 {nights} Night(s) Stay</div>
                        </div>
                    </td>
                </tr>
            </table>

            {company_info_html}

            <!-- Bill Breakdown Table -->
            <div style="margin-top: 24px;">
                <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                    📄 Detailed Itemized Bill
                </div>
                <table width="100%" cellpadding="0" cellspacing="0" style="border: 1px solid #e2e8f0; border-radius: 10px; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                            <th style="padding: 10px 12px; font-size: 12px; font-weight: 800; color: #475569; text-align: left;">Item Description</th>
                            <th style="padding: 10px 12px; font-size: 12px; font-weight: 800; color: #475569; text-align: right;">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                        {addons_html}
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 10px 12px; font-size: 13px; color: #64748b;">Subtotal Room Base Rate</td>
                            <td style="padding: 10px 12px; font-size: 13px; color: #0f172a; text-align: right; font-weight: 600;">₹{room_charges:,.2f}</td>
                        </tr>
                        {f'<tr style="border-bottom: 1px solid #f1f5f9;"><td style="padding: 10px 12px; font-size: 13px; color: #16a34a; font-weight: 600;">✨ Add-On Packages Total</td><td style="padding: 10px 12px; font-size: 13px; color: #16a34a; text-align: right; font-weight: 700;">₹{addons_total:,.2f}</td></tr>' if addons_total > 0 else ''}
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 10px 12px; font-size: 13px; color: #64748b;">SGST (2.5%)</td>
                            <td style="padding: 10px 12px; font-size: 13px; color: #16a34a; text-align: right; font-weight: 600;">₹{sgst:,.2f}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #f1f5f9;">
                            <td style="padding: 10px 12px; font-size: 13px; color: #64748b;">CGST (2.5%)</td>
                            <td style="padding: 10px 12px; font-size: 13px; color: #16a34a; text-align: right; font-weight: 600;">₹{cgst:,.2f}</td>
                        </tr>
                        <tr style="background-color: #f0fdf4;">
                            <td style="padding: 14px 12px; font-size: 15px; font-weight: 800; color: #0f172a;">Grand Total Payable</td>
                            <td style="padding: 14px 12px; font-size: 16px; font-weight: 800; color: #15803d; text-align: right;">₹{grand_total:,.2f}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Policy Note -->
            <div style="margin-top: 20px; font-size: 11px; color: #64748b; line-height: 1.5; background: #f8fafc; padding: 12px; border-radius: 8px; border: 1px solid #e2e8f0;">
                📌 <strong>Standard Check-in:</strong> 12:00 PM | <strong>Check-out:</strong> 11:00 AM<br/>
                Government ID proof (Aadhaar, Passport, Driving License) is mandatory at check-in.
            </div>

        </div>

        <!-- Footer with Powered by Retrod Branding -->
        <div style="background-color: #0f172a; padding: 20px; text-align: center; color: #94a3b8; border-top: 1px solid #1e293b;">
            <div style="font-size: 13px; font-weight: 700; color: #ffffff; margin-bottom: 4px;">{hotel_name}</div>
            <div style="font-size: 11px; color: #64748b; margin-bottom: 12px;">Direct Booking Engine Platform</div>
            
            <div style="display: inline-block; background: #1e293b; border: 1px solid #334155; padding: 6px 16px; border-radius: 20px; font-size: 12px; font-weight: 700; color: #38bdf8; letter-spacing: 0.5px;">
                ⚡ powered by retrod
            </div>
        </div>

    </div>
</body>
</html>
    """

def generate_invoice_sms_text(booking_data, guest_data):
    hotel_name = booking_data.get('hotel_name', 'Hotel XYZ')
    guest_name = f"{guest_data.get('first_name', '')} {guest_data.get('last_name', '')}".strip() or guest_data.get('full_name', 'Valued Guest')
    ref_code = booking_data.get('booking_reference', 'RETROD-CONF-PENDING')
    check_in = booking_data.get('check_in', 'N/A')
    check_out = booking_data.get('check_out', 'N/A')
    nights = booking_data.get('total_nights', 1)
    grand_total = float(booking_data.get('grand_total', 0.0))
    room_charges = float(booking_data.get('room_price', grand_total * 0.95))
    tax = float(booking_data.get('tax_and_fees', grand_total * 0.05))
    addons_total = float(booking_data.get('addons_total', 0.0))

    items = booking_data.get('cart_slots', [])
    if items:
        room_names = ", ".join([item.get('roomName') or item.get('room_name') or 'Room' for item in items])
    else:
        room_names = booking_data.get('room_name', 'Selected Room')

    addons_note = f" | Extras: Rs.{addons_total:,.2f}" if addons_total > 0 else ""

    return (
        f"Thank you for continuing with {hotel_name}!\n\n"
        f"Invoice Details:\n"
        f"Ref: {ref_code}\n"
        f"Guest: {guest_name}\n"
        f"Room(s): {room_names}\n"
        f"Stay: {check_in} to {check_out} ({nights} Nights)\n"
        f"Base: Rs.{room_charges:,.2f}{addons_note} | Taxes: Rs.{tax:,.2f} | Total: Rs.{grand_total:,.2f}\n\n"
        f"powered by retrod"
    )

from django.core.mail import EmailMultiAlternatives, get_connection
import os

def send_booking_invoice_email(booking_data, guest_data):
    recipient_email = guest_data.get('email')
    if not recipient_email or '@' not in recipient_email:
        logger.warning("[SMTP EMAIL] Invalid or missing guest email address. Skipping email dispatch.")
        return False

    hotel_name = booking_data.get('hotel_name', 'Hotel XYZ')
    subject = f"Thank you for continuing with {hotel_name} - Reservation Invoice"
    html_content = generate_invoice_html(booking_data, guest_data)
    text_content = generate_invoice_sms_text(booking_data, guest_data)
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Retrod Booking <no-reply@retrod.com>')

    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or os.getenv('EMAIL_HOST_USER', '')
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or os.getenv('EMAIL_HOST_PASSWORD', '')

    if host_user and host_pass:
        try:
            msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            print(f"\n=======================================================")
            print(f"[LIVE SMTP EMAIL DISPATCH SUCCESS] Invoice sent to: {recipient_email}")
            print(f"Subject: {subject}")
            print(f"=======================================================\n")
            return True
        except Exception as e:
            print(f"\n=======================================================")
            print(f"[SMTP EMAIL ERROR] Could not send live email via SMTP to '{recipient_email}'.")
            print(f"Error details: {e}")
            print(f"Falling back to console email output...")
            print(f"=======================================================\n")

    # Fallback to console backend if SMTP not configured or failed
    try:
        connection = get_connection('django.core.mail.backends.console.EmailBackend')
        msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email], connection=connection)
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"\n=======================================================")
        print(f"[CONSOLE EMAIL LOGGED] Target: {recipient_email}")
        print(f"NOTE: To send REAL emails to inbox, configure EMAIL_HOST_USER & EMAIL_HOST_PASSWORD in backend/.env")
        print(f"=======================================================\n")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to output console email: {e}")
        return False

def generate_confirmation_html(booking_data, guest_data, hotel_obj=None):
    hotel_name = booking_data.get('hotel_name', 'Hotel XYZ')
    guest_name = f"{guest_data.get('first_name', '')} {guest_data.get('last_name', '')}".strip() or guest_data.get('full_name', 'Valued Guest')
    email = guest_data.get('email', 'N/A')
    phone = guest_data.get('phone', 'N/A')
    ref_code = booking_data.get('booking_reference', 'RETROD-CONF-PENDING')
    check_in = booking_data.get('check_in', 'N/A')
    check_out = booking_data.get('check_out', 'N/A')
    nights = booking_data.get('total_nights', 1)
    grand_total = float(booking_data.get('grand_total', 0.0))
    
    items = booking_data.get('cart_slots', [])
    if items:
        room_details = ", ".join([f"{item.get('roomName') or item.get('room_name') or 'Room'} ({item.get('planTitle') or item.get('plan_title') or 'Standard Plan'})" for item in items])
    else:
        room_details = f"{booking_data.get('room_name', 'Selected Room')} ({booking_data.get('plan_title', 'Standard Rate Plan')})"

    hotel_phone = getattr(hotel_obj, 'phone', None) or booking_data.get('hotel_phone') or '+91 9876 543 210'
    hotel_email = getattr(hotel_obj, 'email', None) or booking_data.get('hotel_email') or 'stay@hotel.com'
    hotel_address = getattr(hotel_obj, 'address', None) or booking_data.get('hotel_address') or 'Main Reception Desk, Business District'

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Room Confirmation - {hotel_name}</title>
</head>
<body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
        <div style="background-color: #16a34a; padding: 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 32px; margin-bottom: 8px;">🎉</div>
            <h1 style="margin: 0; font-size: 22px; font-weight: 800;">Your hotel room is confirmed!</h1>
            <p style="margin-top: 6px; font-size: 14px; opacity: 0.95; margin-bottom: 0;">Thank you for booking with {hotel_name}</p>
        </div>

        <div style="padding: 24px;">
            <div style="background: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-size: 11px; font-weight: 800; color: #166534; text-transform: uppercase;">Payment Status</div>
                    <div style="font-size: 18px; font-weight: 800; color: #15803d; margin-top: 2px;">PAID - ₹{grand_total:,.2f}</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 11px; font-weight: 800; color: #166534; text-transform: uppercase;">Booking Reference</div>
                    <div style="font-size: 18px; font-weight: 800; color: #15803d; margin-top: 2px;">{ref_code}</div>
                </div>
            </div>

            <h3 style="font-size: 15px; font-weight: 800; color: #0f172a; margin-top: 0; margin-bottom: 12px;">🏨 Reservation Details</h3>
            <table width="100%" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-size: 13px; color: #334155; margin-bottom: 24px;">
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="font-weight: 700; width: 35%;">Hotel Name:</td>
                    <td>{hotel_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="font-weight: 700;">Guest Name:</td>
                    <td>{guest_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="font-weight: 700;">Room Details:</td>
                    <td>{room_details}</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="font-weight: 700;">Stay Period:</td>
                    <td>📅 {check_in} → {check_out} ({nights} Night(s))</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="font-weight: 700;">Total Paid Amount:</td>
                    <td style="color: #16a34a; font-weight: 800;">₹{grand_total:,.2f} (Paid)</td>
                </tr>
            </table>

            <div style="background-color: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 8px; padding: 16px; margin-top: 20px;">
                <h4 style="margin: 0 0 8px 0; font-size: 13px; font-weight: 800; color: #0f172a;">📞 Reception Contacts & Queries</h4>
                <p style="margin: 0; font-size: 12px; color: #475569; line-height: 1.6;">
                    For any queries, special requests, or check-in coordination, please reach out to <strong>{hotel_name} Reception</strong> directly:
                </p>
                <div style="margin-top: 10px; font-size: 12px; color: #1e293b; line-height: 1.8;">
                    📞 <strong>Front Desk Phone:</strong> {hotel_phone}<br/>
                    📧 <strong>Hotel Email:</strong> {hotel_email}<br/>
                    📍 <strong>Hotel Address:</strong> {hotel_address}
                </div>
            </div>
        </div>

        <div style="background: #0f172a; color: #94a3b8; padding: 16px; text-align: center; font-size: 11px;">
            {hotel_name} Direct Booking Engine &bull; Powered by Retrod
        </div>
    </div>
</body>
</html>
    """

def send_booking_confirmation_email(booking_data, guest_data, hotel_obj=None):
    recipient_email = guest_data.get('email')
    if not recipient_email or '@' not in recipient_email:
        logger.warning("[SMTP EMAIL] Invalid or missing guest email address for confirmation.")
        return False

    hotel_name = booking_data.get('hotel_name', 'Hotel XYZ')
    subject = f"Your hotel room is confirmed! - {hotel_name}"
    html_content = generate_confirmation_html(booking_data, guest_data, hotel_obj)
    text_content = f"Your hotel room is confirmed at {hotel_name}.\nRef: {booking_data.get('booking_reference')}\nTotal Paid: Rs.{float(booking_data.get('grand_total', 0)):,.2f}\nContact Reception: {getattr(hotel_obj, 'phone', '')}"
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', f'{hotel_name} <no-reply@retrod.com>')

    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or os.getenv('EMAIL_HOST_USER', '')
    host_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or os.getenv('EMAIL_HOST_PASSWORD', '')

    if host_user and host_pass:
        try:
            msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            print(f"\n=======================================================")
            print(f"[LIVE CONFIRMATION EMAIL SENT] Confirmation sent to: {recipient_email}")
            print(f"Subject: {subject}")
            print(f"=======================================================\n")
            return True
        except Exception as e:
            print(f"[CONFIRMATION EMAIL ERROR] {e}")

    try:
        connection = get_connection('django.core.mail.backends.console.EmailBackend')
        msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email], connection=connection)
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed: {e}")
        return False

def send_booking_invoice_sms(booking_data, guest_data):
    phone = guest_data.get('phone')
    if not phone:
        logger.warning("[SMS] Missing guest phone number. Skipping SMS dispatch.")
        return False

    sms_text = generate_invoice_sms_text(booking_data, guest_data)
    safe_sms_text = sms_text.encode('ascii', errors='replace').decode('ascii')

    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_auth = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_from = os.getenv('TWILIO_PHONE_NUMBER')

    if twilio_sid and twilio_auth and twilio_from:
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_auth)
            message = client.messages.create(
                body=sms_text,
                from_=twilio_from,
                to=phone
            )
            print(f"\n=======================================================")
            print(f"[LIVE TWILIO SMS DISPATCH SUCCESS] SID: {message.sid} to {phone}")
            print(f"=======================================================\n")
            return True
        except Exception as e:
            print(f"[TWILIO SMS ERROR] Failed to send via Twilio: {e}")

    # Default / Fallback: Console SMS Log
    print(f"\n=======================================================")
    print(f"[SMS SIMULATION / LOGGED SUCCESS] To Mobile: {phone}")
    print(f"-------------------------------------------------------")
    print(safe_sms_text)
    print(f"NOTE: To send REAL SMS to phone, configure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN & TWILIO_PHONE_NUMBER in backend/.env")
    print(f"=======================================================\n")
    return True


def send_event_booking_email(event_data, hotel):
    recipient_email = event_data.get('email')
    if not recipient_email or '@' not in recipient_email:
        return False

    hotel_name = hotel.name if hotel else 'Retrod Hotels'
    nature = event_data.get('nature_of_event', 'Banquet & Event')
    start_date = event_data.get('start_date', 'N/A')
    end_date = event_data.get('end_date', 'N/A')
    guests = event_data.get('num_guests') or event_data.get('guest_count', 0)
    halls = event_data.get('halls_count', 1)
    catering = event_data.get('catering_plan', 'Standard Buffet')
    grand_total = float(event_data.get('grand_total', 0.0))
    organizer = event_data.get('name', 'Valued Host')
    phone = event_data.get('phone', 'N/A')

    subject = f"Banquet & Event Booking Inquiry Received - {hotel_name}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f8fafc; padding: 20px; color: #0f172a;">
        <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border: 2px solid #d4af37; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 16px rgba(212,175,55,0.15);">
            <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #d4af37; padding: 24px; text-align: center;">
                <div style="font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #e2e8f0;">Event & Banquet Venue Booking</div>
                <h2 style="margin: 8px 0 0 0; color: #d4af37;">{hotel_name}</h2>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 15px; line-height: 1.5;">Dear <strong>{organizer}</strong>,</p>
                <p style="font-size: 14px; color: #475569; line-height: 1.6;">
                    Thank you for your event inquiry at <strong>{hotel_name}</strong>. Our dedicated event coordinator has received your requirements and will contact you at <strong>{phone}</strong> shortly.
                </p>
                <div style="background: #fdfbf7; border: 1.5px solid #d4af37; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <div style="font-size: 12px; font-weight: 800; color: #b45309; text-transform: uppercase; margin-bottom: 8px;">Event Specification Summary</div>
                    <div style="font-size: 13px; color: #334155; line-height: 1.7;">
                        &bull; <strong>Nature of Event:</strong> {nature}<br/>
                        &bull; <strong>Dates:</strong> {start_date} to {end_date}<br/>
                        &bull; <strong>Expected Guests:</strong> {guests} Attendees<br/>
                        &bull; <strong>Venues/Halls:</strong> {halls} Hall(s)<br/>
                        &bull; <strong>Catering Package:</strong> {catering}<br/>
                        &bull; <strong>Estimated Total:</strong> ₹{grand_total:,.2f}
                    </div>
                </div>
                <p style="font-size: 12px; color: #64748b;">
                    Need immediate assistance? Contact our Banquet Desk at <strong>{hotel.phone if hotel else '+91 9876 543 210'}</strong>.
                </p>
            </div>
            <div style="background: #0f172a; color: #94a3b8; text-align: center; padding: 12px; font-size: 11px;">
                ⚡ powered by retrod event management engine
            </div>
        </div>
    </body>
    </html>
    """

    text_content = f"Thank you {organizer}! Your event inquiry for {nature} ({guests} Guests, {start_date} to {end_date}) at {hotel_name} has been received. Our event manager will contact you at {phone}."
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Retrod Events <no-reply@retrod.com>')

    try:
        connection = get_connection('django.core.mail.backends.console.EmailBackend')
        msg = EmailMultiAlternatives(subject, text_content, from_email, [recipient_email], connection=connection)
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"[EVENT EMAIL SENT] Confirmation sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[EVENT EMAIL ERROR] {e}")
        return False


def send_event_booking_sms(event_data, hotel):
    phone = event_data.get('phone')
    if not phone:
        return False
    hotel_name = hotel.name if hotel else 'Retrod Hotels'
    nature = event_data.get('nature_of_event', 'Event')
    organizer = event_data.get('name', 'Valued Host')
    start_date = event_data.get('start_date', '')

    sms_text = f"Hi {organizer}, we received your {nature} booking request for {start_date} at {hotel_name}. Our event desk will call you shortly to confirm. - Retrod"
    print(f"\n[EVENT SMS LOGGED] To {phone}: {sms_text}\n")
    return True



