import io
import logging
from decimal import Decimal
from django.utils import timezone

logger = logging.getLogger(__name__)

def fmt_money(amount, prefix="Rs. ") -> str:
    try:
        amt = Decimal(str(amount or 0))
        return f"{prefix}{amt:,.2f}"
    except Exception:
        return f"{prefix}0.00"

def generate_reservation_invoice_pdf(reservation) -> bytes:
    """
    Generates a professional, branded PDF invoice and booking voucher for a Reservation.
    Returns the generated PDF as bytes.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
        )
    except ImportError as e:
        logger.error(f"[INVOICE PDF] ReportLab is not available: {e}")
        return b""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0f766e")   # Deep Teal/Emerald
    text_dark = colors.HexColor("#1e293b")       # Slate 800
    text_muted = colors.HexColor("#64748b")      # Slate 500
    border_color = colors.HexColor("#e2e8f0")    # Slate 200
    bg_light = colors.HexColor("#f8fafc")        # Slate 50

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=text_muted,
    )
    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=primary_color,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=text_dark,
    )
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=text_dark,
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=text_dark,
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=text_dark,
    )
    table_cell_right = ParagraphStyle(
        'TableCellRight',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=text_dark,
    )
    table_cell_right_bold = ParagraphStyle(
        'TableCellRightBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=text_dark,
    )

    story = []

    # 1. PROPERTY & INVOICE HEADER (FROM DATABASE PROPERTY RECORD)
    prop = getattr(reservation, 'property', None)
    property_name = prop.name if prop and prop.name else ""
    
    # Assemble real property address from database
    addr_parts = []
    if prop:
        if prop.address_line_1:
            addr_parts.append(prop.address_line_1.strip())
        if prop.address_line_2:
            addr_parts.append(prop.address_line_2.strip())
        loc_parts = []
        if prop.city:
            loc_parts.append(prop.city.strip())
        if prop.state:
            loc_parts.append(prop.state.strip())
        if loc_parts:
            addr_parts.append(", ".join(loc_parts))
        if prop.country:
            addr_parts.append(prop.country.strip())
        if prop.postal_code:
            addr_parts.append(f"- {prop.postal_code.strip()}")
            
    prop_address = " ".join(addr_parts) if addr_parts else ""
    prop_phone = (prop.contact_phone.strip() if prop and prop.contact_phone else "")
    prop_email = (prop.contact_email.strip() if prop and prop.contact_email else "")
    prop_tax_id = (prop.tax_id.strip() if prop and prop.tax_id else "")

    header_left = [Paragraph(property_name, title_style)]
    if prop_address:
        header_left.append(Paragraph(prop_address, subtitle_style))
    
    contact_bits = []
    if prop_phone:
        contact_bits.append(f"Phone: {prop_phone}")
    if prop_email:
        contact_bits.append(f"Email: {prop_email}")
    if contact_bits:
        header_left.append(Paragraph(" · ".join(contact_bits), subtitle_style))
        
    if prop_tax_id:
        header_left.append(Paragraph(f"GSTIN / Tax ID: {prop_tax_id}", subtitle_style))

    header_right = [
        Paragraph("<b>BOOKING CONFIRMATION & INVOICE</b>", ParagraphStyle('InvTitle', parent=body_bold, fontSize=11, leading=14, alignment=2, textColor=primary_color)),
        Paragraph(f"<b>Conf #:</b> {reservation.confirmation_number}", ParagraphStyle('Conf', parent=body_style, alignment=2)),
        Paragraph(f"<b>Date:</b> {timezone.now().strftime('%d %b %Y')}", ParagraphStyle('Dt', parent=body_style, alignment=2)),
        Paragraph(f"<b>Status:</b> {reservation.status}", ParagraphStyle('St', parent=body_style, alignment=2)),
    ]

    header_table = Table([[header_left, header_right]], colWidths=[320, 200])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1.5, color=primary_color, spaceAfter=14))

    # 2. GUEST DETAILS & STAY SUMMARY (2 COLUMN CARDS)
    guest = reservation.primary_guest
    guest_name = f"{guest.first_name} {guest.last_name}".strip() if guest else "Guest"
    guest_contact = None
    if guest and hasattr(guest, 'contacts'):
        guest_contact = guest.contacts.filter(is_primary=True).first() or guest.contacts.first()
    
    guest_email = guest_contact.email if guest_contact and guest_contact.email else "Not Provided"
    guest_phone = guest_contact.phone if guest_contact and guest_contact.phone else "Not Provided"
    guest_addr = f"{guest_contact.city or ''}, {guest_contact.country or ''}".strip(", ") if guest_contact else "Direct Customer"

    source_name = (
        reservation.reservation_source.name if reservation.reservation_source
        else (getattr(reservation, 'source', '') or 'Direct / Walk-In')
    )

    guest_info = [
        Paragraph("<b>GUEST INFORMATION</b>", section_heading),
        Paragraph(f"<b>Name:</b> {guest_name}", body_style),
        Paragraph(f"<b>Email:</b> {guest_email}", body_style),
        Paragraph(f"<b>Phone:</b> {guest_phone}", body_style),
        Paragraph(f"<b>Location:</b> {guest_addr or 'N/A'}", body_style),
    ]

    arrival_str = reservation.arrival_date.strftime('%d %b %Y') if reservation.arrival_date else "N/A"
    departure_str = reservation.departure_date.strftime('%d %b %Y') if reservation.departure_date else "N/A"
    
    # Calculate nights
    nights = 1
    if reservation.arrival_date and reservation.departure_date:
        nights = max(1, (reservation.departure_date - reservation.arrival_date).days)

    total_adults = sum(a.adult_count for a in reservation.room_allocations.all()) or 1
    total_children = sum(a.child_count for a in reservation.room_allocations.all()) or 0

    stay_info = [
        Paragraph("<b>STAY DETAILS</b>", section_heading),
        Paragraph(f"<b>Check-In:</b> {arrival_str} ({reservation.check_in_time or '12:00 PM'})", body_style),
        Paragraph(f"<b>Check-Out:</b> {departure_str} ({reservation.check_out_time or '11:00 AM'})", body_style),
        Paragraph(f"<b>Duration:</b> {nights} Night{'s' if nights > 1 else ''}", body_style),
        Paragraph(f"<b>Occupants:</b> {total_adults} Adult(s), {total_children} Child(ren)", body_style),
        Paragraph(f"<b>Booking Source:</b> {source_name}", body_style),
    ]

    info_table = Table([[guest_info, stay_info]], colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), bg_light),
        ('BACKGROUND', (1, 0), (1, 0), bg_light),
        ('BOX', (0, 0), (0, 0), 1, border_color),
        ('BOX', (1, 0), (1, 0), 1, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 16))

    # 3. ROOM ALLOCATIONS & CHARGES TABLE
    story.append(Paragraph("<b>ITEMIZED CHARGES BREAKDOWN</b>", section_heading))

    table_data = [
        [
            Paragraph("<b>Item / Room Type</b>", table_cell_bold),
            Paragraph("<b>Assigned Unit</b>", table_cell_bold),
            Paragraph("<b>Meal / Rate Plan</b>", table_cell_bold),
            Paragraph("<b>Dates</b>", table_cell_bold),
            Paragraph("<b>Qty / Nights</b>", table_cell_right_bold),
            Paragraph("<b>Amount (INR)</b>", table_cell_right_bold),
        ]
    ]

    allocations = list(reservation.room_allocations.all())
    if allocations:
        for alloc in allocations:
            type_name = alloc.inventory_unit_type.name if alloc.inventory_unit_type else "Room"
            room_no = alloc.inventory_unit.name if alloc.inventory_unit else "Unassigned"
            
            # Rate snapshots
            snapshots = list(alloc.rate_snapshots.all())
            alloc_total = sum(s.amount_charged for s in snapshots) if snapshots else Decimal("0.00")
            if alloc_total == Decimal("0.00") and reservation.total_amount:
                alloc_total = reservation.total_amount
            
            # Resolve actual rate / meal plan name dynamically
            plan_name = ""
            if snapshots:
                s0 = snapshots[0]
                if s0.rate_snapshot and isinstance(s0.rate_snapshot, dict):
                    plan_name = (
                        s0.rate_snapshot.get('meal_plan_name')
                        or s0.rate_snapshot.get('rate_plan_name')
                        or s0.rate_snapshot.get('meal_plan')
                        or s0.rate_snapshot.get('rate_plan_code')
                    )
                if not plan_name and s0.rate_plan:
                    plan_name = s0.rate_plan.name or s0.rate_plan.code
                    if getattr(s0.rate_plan, 'default_meal_plan', None):
                        dmp = s0.rate_plan.default_meal_plan.name
                        if dmp and dmp.lower() not in plan_name.lower():
                            plan_name = f"{plan_name} ({dmp})"

            if not plan_name and alloc.inventory_snapshot and isinstance(alloc.inventory_snapshot, dict):
                plan_name = alloc.inventory_snapshot.get('meal_plan') or alloc.inventory_snapshot.get('rate_plan') or alloc.inventory_snapshot.get('rate_plan_name')

            if not plan_name:
                plan_name = "Standard Plan"

            checkin_d = alloc.check_in_date.strftime('%d/%m') if alloc.check_in_date else arrival_str
            checkout_d = alloc.check_out_date.strftime('%d/%m') if alloc.check_out_date else departure_str

            table_data.append([
                Paragraph(f"<b>{type_name}</b>", table_cell),
                Paragraph(f"Room {room_no}", table_cell),
                Paragraph(plan_name, table_cell),
                Paragraph(f"{checkin_d} - {checkout_d}", table_cell),
                Paragraph(f"{nights}", table_cell_right),
                Paragraph(fmt_money(alloc_total), table_cell_right),
            ])
    else:
        table_data.append([
            Paragraph("Room Reservation", table_cell),
            Paragraph("Standard", table_cell),
            Paragraph("Standard Plan", table_cell),
            Paragraph(f"{arrival_str} - {departure_str}", table_cell),
            Paragraph(f"{nights}", table_cell_right),
            Paragraph(fmt_money(reservation.total_amount), table_cell_right),
        ])

    # Add packages if any
    for pkg in reservation.packages.all():
        pkg_name = pkg.package.name if pkg.package else "Hospitality Package"
        table_data.append([
            Paragraph(f"Package: {pkg_name}", table_cell),
            Paragraph("-", table_cell),
            Paragraph("-", table_cell),
            Paragraph("-", table_cell),
            Paragraph("1", table_cell_right),
            Paragraph(fmt_money(pkg.price), table_cell_right),
        ])

    # Add services if any
    for svc in reservation.services.all():
        svc_name = svc.service.name if svc.service else "Service Addon"
        table_data.append([
            Paragraph(f"Service: {svc_name}", table_cell),
            Paragraph("-", table_cell),
            Paragraph("-", table_cell),
            Paragraph("-", table_cell),
            Paragraph("1", table_cell_right),
            Paragraph(fmt_money(svc.price), table_cell_right),
        ])

    charges_table = Table(table_data, colWidths=[140, 75, 95, 80, 50, 80])
    charges_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, bg_light]),
        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
    ]))
    story.append(charges_table)
    story.append(Spacer(1, 14))

    # 4. SUMMARY & BALANCE CALCULATION (DYNAMIC TAX LABEL)
    subtotal = reservation.total_amount or Decimal("0.00")
    tax_amt = reservation.tax_amount or Decimal("0.00")
    discount_amt = reservation.discount_amount or Decimal("0.00")
    grand_total = (subtotal + tax_amt) - discount_amt
    paid_amt = reservation.paid_amount or Decimal("0.00")
    balance_amt = reservation.balance_amount or Decimal("0.00")

    # Dynamic tax label from DB or calculated rate
    tax_label = "Taxes & Fees:"
    try:
        from apps.core.common.models import SystemTax
        active_taxes = list(SystemTax.objects.filter(tenant=reservation.tenant, status='active'))
        if active_taxes:
            tax_names = [
                f"{t.name} ({int(t.rate) if t.rate == int(t.rate) else t.rate}%)" if t.type == 'percentage'
                else t.name
                for t in active_taxes
            ]
            tax_label = f"Taxes ({', '.join(tax_names)}):"
        elif tax_amt > Decimal("0.00") and subtotal > Decimal("0.00"):
            eff_rate = round((tax_amt / subtotal) * 100)
            tax_label = f"Taxes & GST ({eff_rate}%):"
        else:
            tax_label = "Taxes & GST:"
    except Exception:
        tax_label = "Taxes & GST:"

    summary_rows = [
        [Paragraph("Base Subtotal:", table_cell_bold), Paragraph(fmt_money(subtotal), table_cell_right)],
        [Paragraph(tax_label, table_cell_bold), Paragraph(f"+ {fmt_money(tax_amt)}", table_cell_right)],
    ]
    if discount_amt > Decimal("0.00"):
        summary_rows.append([Paragraph("Discounts / Coupons:", table_cell_bold), Paragraph(f"- {fmt_money(discount_amt)}", table_cell_right)])

    summary_rows.extend([
        [Paragraph("<b>Grand Total:</b>", table_cell_bold), Paragraph(f"<b>{fmt_money(grand_total)}</b>", table_cell_right_bold)],
        [Paragraph("<b>Deposit Paid:</b>", table_cell_bold), Paragraph(fmt_money(paid_amt), table_cell_right)],
        [Paragraph("<b>Folio Balance Due:</b>", table_cell_bold), Paragraph(f"<b>{fmt_money(balance_amt)}</b>", table_cell_right_bold)],
    ])

    summary_table = Table(summary_rows, colWidths=[150, 100])
    summary_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -3), (-1, -3), 1, primary_color),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#fef2f2") if balance_amt > 0 else colors.HexColor("#f0fdf4")),
    ]))

    # Special instructions / Remarks box alongside summary table
    remarks_text = reservation.remarks or reservation.special_requests or "Standard reservation guaranteed. Please present valid photo ID during check-in."
    checkin_time_str = reservation.check_in_time or (prop.check_in_time if prop and prop.check_in_time else "12:00 PM")
    checkout_time_str = reservation.check_out_time or (prop.check_out_time if prop and prop.check_out_time else "11:00 AM")

    policy_box = [
        Paragraph("<b>GUEST NOTES & INSTRUCTIONS</b>", ParagraphStyle('NoteH', parent=body_bold, fontSize=9, leading=12, textColor=primary_color)),
        Spacer(1, 4),
        Paragraph(remarks_text, ParagraphStyle('NoteB', parent=body_style, fontSize=8, leading=11)),
        Spacer(1, 6),
        Paragraph(f"<b>Standard Check-In:</b> {checkin_time_str} · <b>Check-Out:</b> {checkout_time_str}", ParagraphStyle('TimeB', parent=body_style, fontSize=7.5, leading=10, textColor=text_muted)),
        Paragraph("Valid Government Photo ID (Aadhaar / Passport / DL) required at front desk.", ParagraphStyle('IdB', parent=body_style, fontSize=7.5, leading=10, textColor=text_muted)),
    ]

    totals_layout = Table([[policy_box, summary_table]], colWidths=[260, 260])
    totals_layout.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, 0), bg_light),
        ('BOX', (0, 0), (0, 0), 1, border_color),
        ('TOPPADDING', (0, 0), (0, 0), 8),
        ('BOTTOMPADDING', (0, 0), (0, 0), 8),
        ('LEFTPADDING', (0, 0), (0, 0), 10),
        ('RIGHTPADDING', (0, 0), (0, 0), 10),
        ('LEFTPADDING', (1, 0), (1, 0), 10),
    ]))
    story.append(totals_layout)
    story.append(Spacer(1, 16))

    # 5. TERMS & SIGNATURE FOOTER
    footer_text = Paragraph(
        f"Thank you for choosing {property_name}! For any modifications or assistance, please reach out to front desk. "
        "This is a computer-generated confirmation voucher and tax invoice.",
        ParagraphStyle('Footer', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=7.5, leading=10, alignment=1, textColor=text_muted)
    )
    story.append(KeepTogether([HRFlowable(width="100%", thickness=0.5, color=border_color, spaceAfter=8), footer_text]))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
