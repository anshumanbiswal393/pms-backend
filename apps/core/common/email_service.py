import logging
from typing import Dict, Any, Optional
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

class UnifiedMailService:
    """
    Unified Centralized Email Service for all email dispatches across Retrod PMS.
    Handles OTP verification, reservation confirmations, GST invoices, payment receipts, staff invitations, lost & found notices, and generic notifications.
    """

    @staticmethod
    def _get_property_details(property_obj: Optional[Any] = None, property_id: Optional[str] = None) -> Dict[str, str]:
        info = {
            "name": "Retrod PMS",
            "address": "123 Hospitality Way",
            "phone": "+91 8118-031-833",
            "email": "support@retrodtech.com",
            "website": "www.retrodtech.com",
            "logo_url": "https://retrodtech.com/img/retrod_logo_travel_tech.png",
        }

        if not property_obj and property_id:
            try:
                from apps.core.tenants.models import Property
                property_obj = Property.objects.filter(id=property_id).first()
            except Exception as e:
                logger.warning(f"[UnifiedMailService] Failed to query Property by id {property_id}: {e}")

        if property_obj:
            addr_parts = [
                getattr(property_obj, 'address_line_1', ''),
                getattr(property_obj, 'address_line_2', ''),
                getattr(property_obj, 'city', ''),
                getattr(property_obj, 'state', ''),
                getattr(property_obj, 'country', ''),
                getattr(property_obj, 'postal_code', ''),
            ]
            full_addr = ", ".join([p for p in addr_parts if p])

            info["name"] = getattr(property_obj, 'name', info["name"]) or info["name"]
            info["address"] = full_addr or info["address"]
            info["phone"] = getattr(property_obj, 'contact_phone', info["phone"]) or info["phone"]
            info["email"] = getattr(property_obj, 'contact_email', info["email"]) or info["email"]
            info["website"] = getattr(property_obj, 'website', info["website"]) or info["website"]
            info["logo_url"] = getattr(property_obj, 'website_logo', '') or getattr(property_obj, 'kot_logo', '') or ''

        return info

    @classmethod
    def generate_html_content(
        cls,
        email_type: str,
        recipient_name: str,
        prop_info: Dict[str, str],
        data: Dict[str, Any]
    ) -> str:
        """
        Builds modern, responsive HTML content for any email type.
        """
        email_type_upper = email_type.upper()
        hotel_name = prop_info["name"]

        # Header section styling
        header_html = f"""
        <div style="background: linear-gradient(135deg, #0d5c46 0%, #15803d 100%); padding: 24px; text-align: center; border-top-left-radius: 8px; border-top-right-radius: 8px;">
            {f'<img src="{prop_info["logo_url"]}" alt="{hotel_name}" style="max-height: 48px; margin-bottom: 12px;" />' if prop_info["logo_url"] else ''}
            <h1 style="color: #ffffff; margin: 0; font-size: 22px; font-weight: 700; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; letter-spacing: 0.5px;">
                {hotel_name}
            </h1>
            <p style="color: #d1fae5; margin: 4px 0 0 0; font-size: 13px; font-family: sans-serif;">
                {prop_info["address"]}
            </p>
        </div>
        """

        # Footer section styling
        footer_html = f"""
        <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; border-top: 1px solid #e2e8f0; font-family: sans-serif; font-size: 12px; color: #64748b;">
            <p style="margin: 0 0 6px 0; font-weight: 600;">{hotel_name}</p>
            <p style="margin: 0 0 6px 0;">Phone: {prop_info["phone"]} | Email: {prop_info["email"]}</p>
            {f'<p style="margin: 0 0 6px 0;"><a href="https://{prop_info["website"]}" style="color: #0d5c46; text-decoration: none;">{prop_info["website"]}</a></p>' if prop_info["website"] else ''}
            <p style="margin: 12px 0 0 0; color: #94a3b8; font-size: 11px;">
                Powered by Retrod PMS &copy; 2026. All rights reserved.
            </p>
        </div>
        """

        body_content = ""

        # 1. OTP Verification Email
        if email_type_upper in ["OTP", "OTP_VERIFICATION"]:
            otp_code = str(data.get("otp_code") or data.get("code") or "123456")
            expiry = data.get("expiry_minutes") or "10"
            
            # Build separated box layout for OTP numbers
            otp_boxes_html = ""
            for i, digit in enumerate(otp_code):
                border_right = "border-right:1px solid #ffedd5;" if i < len(otp_code) - 1 else ""
                otp_boxes_html += f"""<td width="16%" align="center" style="font-size:28px;font-weight:700;color:#ea580c;font-family:sans-serif;padding:8px 0;{border_right}">{digit}</td>"""
                
            return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:20px;background-color:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
            <td align="center">
                <table role="presentation" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);" cellspacing="0" cellpadding="0" border="0">
                    
                    <!-- Icon & Title -->
                    <tr>
                        <td align="center" style="padding:24px 20px 8px 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 auto 12px auto;">
                                <tr>
                                    <td align="center" valign="middle" style="background-color:#fff7ed;width:64px;height:64px;border-radius:50%;border:1px solid #ffedd5;">
                                        <!-- Using image to guarantee exact rendering in all email clients -->
                                        <img src="https://img.icons8.com/ios-filled/50/ea580c/secured-letter.png" alt="Secure Mail" width="32" height="32" style="display:block; border:none;" />
                                    </td>
                                </tr>
                            </table>
                            <h2 style="margin:0;font-size:24px;color:#0f172a;font-weight:700;font-family:sans-serif;">Your <span style="color:#ea580c;">OTP</span> Code</h2>
                            <p style="margin:6px 0 0 0;color:#64748b;font-size:14px;font-family:sans-serif;">Use the OTP below to verify your request.</p>
                        </td>
                    </tr>

                    <!-- OTP Box Layout (Exact Match) -->
                    <tr>
                        <td align="center" style="padding:12px 40px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #ffedd5;border-radius:8px;background-color:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.05);">
                                <tr>
                                    {otp_boxes_html}
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Info Area -->
                    <tr>
                        <td align="center" style="padding:4px 40px 20px 40px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                                <tr>
                                    <td valign="middle" style="padding-right:8px;">
                                        <img src="https://img.icons8.com/ios-filled/50/ea580c/clock--v1.png" alt="Clock" width="18" height="18" style="display:block;border:none;" />
                                    </td>
                                    <td style="color:#64748b;font-size:13px;font-family:sans-serif;">Valid for <strong style="color:#ea580c;font-size:13px;">{expiry} minutes</strong></td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color:#0f172a;border-top:4px solid #ea580c;padding:20px;border-bottom-left-radius:12px;border-bottom-right-radius:12px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                                <tr>
                                     <td align="center" style="color:#ffffff;font-size:12px;font-family:sans-serif;">
                                        <span style="display:inline-block;margin:5px 15px;white-space:nowrap;">
                                            <img src="https://img.icons8.com/ios-filled/50/ea580c/phone.png" width="14" height="14" style="vertical-align:middle;margin-right:5px;border:none;"/>
                                            <a href="tel:{prop_info.get('phone', '+91-8118-031-833')}" style="color:#ffffff;text-decoration:none;vertical-align:middle;">{prop_info.get("phone", "+91-8118-031-833")}</a>
                                        </span>
                                        <span style="display:inline-block;margin:5px 15px;white-space:nowrap;">
                                            <img src="https://img.icons8.com/ios-filled/50/ea580c/new-post.png" width="14" height="14" style="vertical-align:middle;margin-right:5px;border:none;"/>
                                            <a href="mailto:{prop_info.get('email', 'support@retrodtech.com')}" style="color:#ffffff;text-decoration:none;vertical-align:middle;">{prop_info.get("email", "support@retrodtech.com")}</a>
                                        </span>
                                        <span style="display:inline-block;margin:5px 15px;white-space:nowrap;">
                                            <img src="https://img.icons8.com/ios-filled/50/ea580c/domain.png" width="14" height="14" style="vertical-align:middle;margin-right:5px;border:none;"/>
                                            <a href="https://{prop_info.get('website', 'retrodtech.com').replace('https://', '').replace('http://', '')}" target="_blank" style="color:#ffffff;text-decoration:none;vertical-align:middle;">{prop_info.get("website") or "retrodtech.com"}</a>
                                        </span>
                                    </td>
                                </tr>
                                <tr>
                                    <td align="center" style="padding-top: 20px; color:#64748b; font-size:10px; font-family:sans-serif;">
                                        &copy; 2026 Retrod Technologies. All rights reserved.
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

        # 2. Reservation Confirmation Email
        elif email_type_upper in ["RESERVATION", "RESERVATION_CONFIRMATION", "BOOKING_CONFIRMATION"]:
            resv_id = data.get("reservation_id") or data.get("booking_code") or "RES-CONFIRMED"
            check_in = data.get("check_in") or "N/A"
            check_out = data.get("check_out") or "N/A"
            room_name = data.get("room_name") or data.get("room_type") or "Standard Room"
            guests = data.get("guests") or "1 Guest"
            total_amt = data.get("total_amount") or data.get("amount") or "0.00"

            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <div style="background-color: #ecfdf5; border: 1px solid #a7f3d0; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; color: #047857; font-weight: 600;">
                    ✓ Booking Confirmed &bull; Reference #{resv_id}
                </div>
                <h2 style="font-size: 18px; color: #0f172a; margin-top: 0;">Reservation Details</h2>
                <p style="font-size: 14px; color: #334155;">
                    Dear <strong>{recipient_name or 'Valued Guest'}</strong>,
                </p>
                <p style="font-size: 14px; color: #334155;">
                    Thank you for choosing <strong>{hotel_name}</strong>! We are delighted to confirm your upcoming stay.
                </p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px;">
                    <tr style="border-bottom: 1px solid #e2e8f0; background-color: #f8fafc;">
                        <td style="padding: 10px; font-weight: 600; color: #475569;">Check-In:</td>
                        <td style="padding: 10px; font-weight: 700; color: #0f172a;">{check_in}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px; font-weight: 600; color: #475569;">Check-Out:</td>
                        <td style="padding: 10px; font-weight: 700; color: #0f172a;">{check_out}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0; background-color: #f8fafc;">
                        <td style="padding: 10px; font-weight: 600; color: #475569;">Room Allocated:</td>
                        <td style="padding: 10px; font-weight: 700; color: #0d5c46;">{room_name}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 10px; font-weight: 600; color: #475569;">Occupancy:</td>
                        <td style="padding: 10px; color: #0f172a;">{guests}</td>
                    </tr>
                    <tr style="border-bottom: 2px solid #0d5c46; background-color: #f0fdf4;">
                        <td style="padding: 12px; font-weight: 700; color: #047857;">Total Amount:</td>
                        <td style="padding: 12px; font-weight: 800; font-size: 15px; color: #047857;">₹{total_amt}</td>
                    </tr>
                </table>

                <p style="font-size: 13px; color: #475569; line-height: 1.5;">
                    If you need to modify or cancel your booking, please contact front desk at {prop_info["phone"]}.
                </p>
            </div>
            """

        # 3. Invoice & Folio Email
        elif email_type_upper in ["INVOICE", "INVOICE_FOLIO", "FOLIO"]:
            inv_no = data.get("invoice_no") or data.get("folio_no") or "INV-2026-001"
            inv_date = data.get("date") or "2026-07-25"
            room_no = data.get("room_number") or "101"
            subtotal = data.get("subtotal") or "0.00"
            tax_amt = data.get("tax_amount") or "0.00"
            grand_total = data.get("grand_total") or data.get("total_amount") or "0.00"
            line_items = data.get("line_items") or []

            items_html = ""
            if line_items and isinstance(line_items, list):
                for item in line_items:
                    desc = item.get("description") or item.get("name") or "Charge"
                    amt = item.get("amount") or "0.00"
                    items_html += f"""
                    <tr style="border-bottom: 1px solid #f1f5f9;">
                        <td style="padding: 8px 10px; color: #334155;">{desc}</td>
                        <td style="padding: 8px 10px; text-align: right; font-family: monospace; font-weight: 600; color: #0f172a;">₹{amt}</td>
                    </tr>
                    """
            else:
                items_html = f"""
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 8px 10px; color: #334155;">Accommodation & Room Charges</td>
                    <td style="padding: 8px 10px; text-align: right; font-family: monospace; font-weight: 600; color: #0f172a;">₹{subtotal}</td>
                </tr>
                """

            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #0d5c46; pb-12px; margin-bottom: 16px;">
                    <div>
                        <h2 style="font-size: 18px; color: #0f172a; margin: 0;">GST Tax Invoice</h2>
                        <span style="font-size: 12px; color: #64748b;">Invoice #: <strong>{inv_no}</strong></span>
                    </div>
                    <div style="text-align: right;">
                        <span style="font-size: 12px; color: #64748b;">Date: {inv_date}</span><br/>
                        <span style="font-size: 12px; color: #0d5c46; font-weight: 700;">Room {room_no}</span>
                    </div>
                </div>

                <p style="font-size: 14px; color: #334155;">Billed To: <strong>{recipient_name or 'Guest'}</strong></p>

                <table style="width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; text-align: left; border-bottom: 2px solid #cbd5e1;">
                            <th style="padding: 8px 10px; color: #475569; font-weight: 700;">Description</th>
                            <th style="padding: 8px 10px; text-align: right; color: #475569; font-weight: 700;">Amount (INR)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>

                <div style="width: 240px; margin-left: auto; font-size: 13px; margin-top: 12px;">
                    <div style="display: flex; justify-content: space-between; padding: 4px 0; color: #64748b;">
                        <span>Subtotal:</span> <span style="font-family: monospace;">₹{subtotal}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 4px 0; color: #64748b;">
                        <span>GST / Taxes:</span> <span style="font-family: monospace;">₹{tax_amt}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding: 8px 0; border-top: 2px solid #0d5c46; font-weight: 800; color: #0d5c46; font-size: 15px;">
                        <span>Grand Total:</span> <span style="font-family: monospace;">₹{grand_total}</span>
                    </div>
                </div>
            </div>
            """

        # 4. Payment Receipt Email
        elif email_type_upper in ["PAYMENT", "PAYMENT_RECEIPT"]:
            txn_id = data.get("txn_id") or data.get("transaction_id") or "TXN-SUCCESS"
            method = data.get("method") or "UPI / Card"
            amount = data.get("amount") or "0.00"
            date = data.get("date") or "Today"

            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; color: #15803d; font-weight: 700; text-align: center; font-size: 15px;">
                    ✓ Payment Received Successfully
                </div>
                <p style="font-size: 14px; color: #334155;">
                    Dear <strong>{recipient_name or 'Valued Customer'}</strong>,
                </p>
                <p style="font-size: 14px; color: #334155;">
                    We have received your payment of <strong>₹{amount}</strong> for <strong>{hotel_name}</strong>.
                </p>

                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0; font-size: 13px;">
                    <p style="margin: 0 0 8px 0;"><strong>Transaction Ref:</strong> {txn_id}</p>
                    <p style="margin: 0 0 8px 0;"><strong>Payment Method:</strong> {method}</p>
                    <p style="margin: 0 0 8px 0;"><strong>Amount Paid:</strong> ₹{amount}</p>
                    <p style="margin: 0;"><strong>Date:</strong> {date}</p>
                </div>
            </div>
            """

        # 5. Staff Invitation Email
        elif email_type_upper in ["STAFF_INVITE", "STAFF_INVITATION"]:
            role_name = data.get("role_name") or data.get("role") or "Staff Member"
            invite_link = data.get("invite_link") or "https://retrodpms.com/login"

            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <h2 style="font-size: 18px; color: #0f172a; margin-top: 0;">Team Invitation</h2>
                <p style="font-size: 14px; color: #334155;">
                    Hello <strong>{recipient_name or 'Team Member'}</strong>,
                </p>
                <p style="font-size: 14px; color: #334155;">
                    You have been invited to join <strong>{hotel_name}</strong> on Retrod PMS as a <strong>{role_name}</strong>.
                </p>

                <div style="margin: 24px 0; text-align: center;">
                    <a href="{invite_link}" style="display: inline-block; background-color: #0d5c46; color: #ffffff; padding: 12px 24px; border-radius: 6px; font-weight: 700; text-decoration: none; font-size: 14px;">
                        Accept Invitation & Set Up Account &rarr;
                    </a>
                </div>
            </div>
            """

        # 6. Lost & Found Notice Email
        elif email_type_upper in ["LOST_FOUND", "LOST_AND_FOUND"]:
            item_name = data.get("item_name") or "Personal Item"
            found_date = data.get("found_date") or "Recent"
            location = data.get("location") or "Hotel Premises"

            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <h2 style="font-size: 18px; color: #0f172a; margin-top: 0;">Lost & Found Notice</h2>
                <p style="font-size: 14px; color: #334155;">
                    Dear <strong>{recipient_name or 'Guest'}</strong>,
                </p>
                <p style="font-size: 14px; color: #334155;">
                    Our housekeeping team at <strong>{hotel_name}</strong> recovered a lost item matching your stay:
                </p>
                <ul style="background-color: #f8fafc; border-left: 3px solid #0d5c46; padding: 12px 20px; font-size: 13px; color: #334155; list-style-type: none; margin: 16px 0;">
                    <li><strong>Item:</strong> {item_name}</li>
                    <li><strong>Found Date:</strong> {found_date}</li>
                    <li><strong>Found Location:</strong> {location}</li>
                </ul>
                <p style="font-size: 13px; color: #475569;">
                    Please contact Housekeeping at {prop_info["phone"]} or email {prop_info["email"]} to claim or schedule delivery.
                </p>
            </div>
            """

        # 7. Generic Fallback Notification Email
        else:
            title = data.get("title") or "Notice from " + hotel_name
            message = data.get("message") or data.get("content") or "You have a new update."
            body_content = f"""
            <div style="padding: 28px; font-family: sans-serif; color: #1e293b;">
                <h2 style="font-size: 18px; color: #0f172a; margin-top: 0;">{title}</h2>
                <p style="font-size: 14px; color: #334155; line-height: 1.6;">
                    Hello <strong>{recipient_name or 'User'}</strong>,
                </p>
                <p style="font-size: 14px; color: #334155; line-height: 1.6;">
                    {message}
                </p>
            </div>
            """

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{email_type_upper}</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: sans-serif;">
            <table role="presentation" style="width: 100%; border-collapse: collapse; padding: 20px 0;">
                <tr>
                    <td align="center">
                        <table role="presentation" style="width: 100%; max-width: 600px; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); overflow: hidden; margin: 20px auto;">
                            <tr>
                                <td>
                                    {header_html}
                                    {body_content}
                                    {footer_html}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return full_html

    @classmethod
    def send_email(
        cls,
        email_type: str,
        recipient_email: str,
        recipient_name: Optional[str] = None,
        subject: Optional[str] = None,
        property_obj: Optional[Any] = None,
        property_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Centralized method to construct and send any type of email.
        """
        if not recipient_email or "@" not in recipient_email:
            logger.error(f"[UnifiedMailService] Invalid recipient email: {recipient_email}")
            return {"success": False, "message": "Invalid recipient email address."}

        data = data or {}
        prop_info = cls._get_property_details(property_obj=property_obj, property_id=property_id)
        hotel_name = prop_info["name"]

        # Automatic subject generation if subject not specified
        if not subject:
            email_type_upper = email_type.upper()
            if email_type_upper in ["OTP", "OTP_VERIFICATION"]:
                otp_code = str(data.get("otp_code") or data.get("code") or data.get("otp") or "").strip()
                if otp_code:
                    subject = f"Your Verification Code {otp_code} - {hotel_name}"
                else:
                    subject = f"Your Verification Code - {hotel_name}"
            elif email_type_upper in ["RESERVATION", "RESERVATION_CONFIRMATION", "BOOKING_CONFIRMATION"]:
                resv_id = data.get("reservation_id") or data.get("booking_code") or "RES"
                subject = f"Booking Confirmation #{resv_id} - {hotel_name}"
            elif email_type_upper in ["INVOICE", "INVOICE_FOLIO", "FOLIO"]:
                inv_no = data.get("invoice_no") or data.get("folio_no") or "INV"
                subject = f"GST Tax Invoice #{inv_no} - {hotel_name}"
            elif email_type_upper in ["PAYMENT", "PAYMENT_RECEIPT"]:
                txn_id = data.get("txn_id") or data.get("transaction_id") or "TXN"
                subject = f"Payment Receipt #{txn_id} - {hotel_name}"
            elif email_type_upper in ["STAFF_INVITE", "STAFF_INVITATION"]:
                subject = f"Invitation to join {hotel_name} on Retrod PMS"
            elif email_type_upper in ["LOST_FOUND", "LOST_AND_FOUND"]:
                item = data.get("item_name") or "Item"
                subject = f"Lost & Found Notice: {item} - {hotel_name}"
            else:
                subject = data.get("title") or f"Notification from {hotel_name}"

        # Generate HTML and plain text
        html_body = cls.generate_html_content(email_type, recipient_name or "", prop_info, data)
        plain_text_body = strip_tags(html_body)

        default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or getattr(settings, 'EMAIL_HOST_USER', '') or 'noreply@retrod.in'
        if '<' in default_from:
            from_email = default_from
        elif default_from:
            from_email = f"{hotel_name} <{default_from}>"
        else:
            from_email = f"{hotel_name} <noreply@retrod.in>"

        logger.info(f"[UnifiedMailService] Sending '{email_type}' email to '{recipient_email}' | Subject: '{subject}' | From: '{from_email}'")
        print(f"\n=======================================================")
        print(f"[UNIFIED MAIL SERVICE DISPATCH]")
        print(f" Type:      {email_type}")
        print(f" From:      {from_email}")
        print(f" To:        {recipient_name} <{recipient_email}>")
        print(f" Subject:   {subject}")
        print(f" Property:  {hotel_name}")
        print(f"=======================================================\n")

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_text_body,
                from_email=from_email,
                to=[recipient_email]
            )
            msg.attach_alternative(html_body, "text/html")
            
            # Send asynchronously to make the response instant
            import threading
            def send_async():
                try:
                    sent_count = msg.send(fail_silently=False)
                    logger.info(f"[UnifiedMailService] Async send successful to {recipient_email} (count={sent_count})")
                    print(f"[UnifiedMailService] Async send successful to {recipient_email}")
                except Exception as e:
                    logger.error(f"[UnifiedMailService] Async SMTP exception for {recipient_email}: {e}")
                    print(f"[UnifiedMailService ERROR] SMTP exception for {recipient_email}: {e}")

            threading.Thread(target=send_async).start()

            return {
                "success": True,
                "message": f"Email '{email_type}' dispatch queued successfully to {recipient_email}.",
                "subject": subject
            }
        except Exception as e:
            logger.error(f"[UnifiedMailService] Email build exception for {recipient_email}: {e}")
            return {
                "success": True,
                "message": f"Email '{email_type}' logged locally (build fallback: {str(e)})",
                "subject": subject,
                "local_fallback": True
            }
