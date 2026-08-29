import os
import logging
from apps.chatbot.ai_engine.models import KnowledgeChunk
from apps.chatbot.ai_engine.embeddings import get_text_embedding


logger = logging.getLogger(__name__)

BASE_URL = os.getenv("PMS_UI_BASE_URL", "https://pms-ui-ten.vercel.app")

DEFAULT_ROUTES_DATA = [
    # 1. Front Desk & Reservations
    {"route": "/reservations", "feature": "Reservations List & Timeline", "perm": "reservations.view", "desc": "Interactive timeline view of room bookings, status filters, and daily occupancy percentage headers."},
    {"route": "/reservations/new", "feature": "New Reservation", "perm": "reservations.create", "desc": "Multi-step booking engine with OCR guest document extraction, room allocation, and payment method selection."},
    {"route": "/groups", "feature": "Group Bookings", "perm": "reservations.view", "desc": "Corporate and tour group block reservations, room allocation matrices, master folio setup, and group payments."},
    {"route": "/events", "feature": "Event Bookings", "perm": "reservations.view", "desc": "Banquet, conference hall, and event space reservations, setup timing, catering details, and billing."},
    {"route": "/housekeeping", "feature": "Housekeeping & Room Ops", "perm": "housekeeping.view", "desc": "Live room cleaning status matrix, staff assignment, and maintenance reporting."},
    {"route": "/housekeeping/mobile", "feature": "Housekeeping Mobile View", "perm": "housekeeping.view", "desc": "Optimized mobile interface for cleaning staff to update room status on-the-go."},
    {"route": "/lost-found", "feature": "Lost & Found", "perm": "housekeeping.view", "desc": "Item logging, guest inquiry matching, storage location tracking, and claim verification."},
    {"route": "/maintenance", "feature": "Work Orders & Maintenance", "perm": "maintenance.view", "desc": "Property maintenance ticket console, issue priority, room blocking for maintenance, and repair status tracking."},
    {"route": "/laundry", "feature": "Laundry & Linen Management", "perm": "dashboard.view", "desc": "Guest laundry request submission with room-first guest lookup, service lead time validation, linen stock tracking."},
    {"route": "/dashboard/multi-property", "feature": "Multi-Property Dashboard", "perm": "dashboard.view", "desc": "Executive view aggregating performance metrics, occupancy, and revenue across all group properties."},

    # 2. Guests & CRM
    {"route": "/guests", "feature": "Guest Profiles Directory", "perm": "guests.view", "desc": "Complete guest database with stay history, total spend, preferences, VIP tags, and contact details."},
    {"route": "/notifications", "feature": "Notification Center", "perm": "dashboard.view", "desc": "Real-time system alerts, guest request notifications, stock low alerts, and operational updates."},
    {"route": "/loyalty", "feature": "Loyalty Program", "perm": "guests.view", "desc": "Guest reward points, tier progression (Silver, Gold, Platinum), points redemption, and member benefits."},
    {"route": "/communications", "feature": "Guest Communications", "perm": "guests.view", "desc": "Automated SMS, WhatsApp, and email messaging for pre-arrival greetings, check-in instructions."},
    {"route": "/guest-requests", "feature": "Guest Requests Console", "perm": "guests.view", "desc": "Room service, housekeeping, amenities, and extra luggage request tracking with response timers."},
    {"route": "/feedback", "feature": "Guest Feedback & Reviews", "perm": "guests.view", "desc": "Post-stay survey responses, NPS scores, review sentiment analysis, and staff response logging."},

    # 3. Commercial, Billing & Revenue
    {"route": "/billing", "feature": "Billing & Invoicing", "perm": "billing.view", "desc": "Full folio management, official GST Tax Invoice generator with A4 print layout, PDF download, email template preview."},
    {"route": "/payments", "feature": "Payments Console", "perm": "billing.view", "desc": "Payment transactions log, multi-tender payment splits, and refund logs."},
    {"route": "/taxes-fees", "feature": "Taxes & Fees Setup", "perm": "billing.view", "desc": "GST tax rates setup (CGST 9%, SGST 9%, IGST 18%), service charges, and luxury tax rules."},
    {"route": "/revenue", "feature": "Revenue Management", "perm": "rates.view", "desc": "ADR, RevPAR, Occupancy trend analytics, rate optimization suggestions, and yield management rules."},
    {"route": "/rate-plans", "feature": "Rate Plans", "perm": "rates.view", "desc": "BAR, Corporate, EP/CP/MAP/AP meal plans, promotional rates, and cancellation policies."},
    {"route": "/availability", "feature": "Availability Matrix", "perm": "rates.view", "desc": "Room inventory availability calendar across all room types with stop-sell and minimum stay restrictions."},
    {"route": "/add-ons", "feature": "Add-On Services", "perm": "packages.view", "desc": "Upsell catalog for airport transfers, spa packages, room decoration, and late check-out fees."},
    {"route": "/concierge", "feature": "Concierge Services", "perm": "services.view", "desc": "Tour bookings, restaurant reservations, local attraction ticketing, and guest assistance requests."},
    {"route": "/transport", "feature": "Transportation Management", "perm": "services.view", "desc": "Airport pickup/drop scheduling, driver assignment, vehicle roster, and transport billing."},

    # 4. Channel Manager & Direct Booking
    {"route": "/channel-manager", "feature": "Channel Manager Overview", "perm": "rates.view", "desc": "Live synchronization status with OTAs (Booking.com, Agoda, MakeMyTrip, Expedia, Airbnb)."},
    {"route": "/booking-engine", "feature": "Direct Booking Engine", "perm": "settings.view", "desc": "Guest-facing online reservation widget, room availability search, and instant payment integration."},

    # 5. Point of Sale (POS)
    {"route": "/pos", "feature": "POS Dashboard", "perm": "pos.view", "desc": "Outlet selection (Restaurant, Bar, Room Service, Spa), live table status, and sales summary."},
    {"route": "/pos/new", "feature": "New POS Order", "perm": "pos.create", "desc": "Interactive touch order screen, item search, variant modifiers, table selection, and guest room charge linking."},
    {"route": "/pos/billing", "feature": "POS Billing & Settlement", "perm": "pos.view", "desc": "Settlement terminal for cash, card, UPI, or room charge posting (Room Folio)."},
    {"route": "/pos/kot", "feature": "Kitchen Order Ticket (KOT)", "perm": "pos.view", "desc": "Live KOT kitchen display screen and printer dispatcher for food prep stations."},

    # 6. Intelligence & System Setup
    {"route": "/search", "feature": "Global Search", "perm": "dashboard.view", "desc": "Fast universal search across guests, reservations, rooms, invoices, and work orders."},
    {"route": "/reports", "feature": "Reports & Analytics", "perm": "reports.view", "desc": "Comprehensive library of operational reports (Manager Flash, Police Inquiry, Housekeeping Summary, Tax Return)."},
    {"route": "/rooms", "feature": "Rooms & Inventory Setup", "perm": "rooms.view", "desc": "Room category creation, amenities setup, base occupancy limits, and individual room number inventory."},
    {"route": "/staff", "feature": "Staff Management", "perm": "staff.view", "desc": "Employee directory, department assignments, contact details, and account status."},
    {"route": "/settings", "feature": "System Setup", "perm": "settings.view", "desc": "General property settings, currency formatting, check-in/out default times, logo upload, and invoice headers."}
]

class IngestionService:
    """Service layer encapsulating knowledge base document parsing and ingestion logic."""

    @classmethod
    def ingest_docx_file(cls, file_path: str) -> int:
        """Parses MS Word docx or fallback XML structure and ingests into KnowledgeChunk model."""
        if not os.path.exists(file_path):
            logger.warning("IngestionService: Document path '%s' does not exist.", file_path)
            return 0

        paragraphs_list = []
        try:
            import docx
            doc = docx.Document(file_path)
            for paragraph in doc.paragraphs:
                t = paragraph.text.strip()
                if t:
                    is_head = paragraph.style.name.startswith("Heading") or (len(t) < 60 and t.isupper())
                    paragraphs_list.append((t, is_head))
        except Exception:
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(file_path) as docx_zip:
                    xml_content = docx_zip.read('word/document.xml')
                    root = ET.fromstring(xml_content)
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    for p in root.findall('.//w:p', ns):
                        texts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                        if texts:
                            line = ''.join(texts).strip()
                            if line:
                                is_head = len(line) < 60 and (line.isupper() or line.endswith(":"))
                                paragraphs_list.append((line, is_head))
            except Exception as ex:
                logger.error("Failed to parse docx file '%s': %s", file_path, ex)
                return 0

        if not paragraphs_list:
            return 0

        KnowledgeChunk.objects.filter(source_doc="SRS-PMS_Retrod").delete()
        current_title = "PMS Retrod Overview"
        current_chunk = []
        srs_count = 0

        for text, is_head in paragraphs_list:
            if is_head:
                if current_chunk:
                    full_text = "\n".join(current_chunk)
                    if len(full_text) > 30:
                        vector = get_text_embedding(f"{current_title} {full_text}")
                        KnowledgeChunk.objects.create(
                            title=current_title,
                            content=full_text,
                            category='staff_assistance' if 'staff' in current_title.lower() else 'pms_workflow',
                            source_doc="SRS-PMS_Retrod",
                            embedding=vector,
                            embedding_json=vector
                        )
                        srs_count += 1
                    current_chunk = []
                current_title = text
            else:
                current_chunk.append(text)

        if current_chunk:
            full_text = "\n".join(current_chunk)
            if len(full_text) > 30:
                vector = get_text_embedding(f"{current_title} {full_text}")
                KnowledgeChunk.objects.create(
                    title=current_title,
                    content=full_text,
                    category='pms_workflow',
                    source_doc="SRS-PMS_Retrod",
                    embedding=vector,
                    embedding_json=vector
                )
                srs_count += 1

        logger.info("IngestionService: Successfully ingested %d chunks from '%s'", srs_count, file_path)
        return srs_count

    @classmethod
    def ingest_routes(cls, routes_data: list = None) -> int:
        """Ingests application route definitions into KnowledgeChunk model."""
        routes = routes_data or DEFAULT_ROUTES_DATA
        KnowledgeChunk.objects.filter(source_doc="Website_Routes").delete()
        route_count = 0

        for item in routes:
            full_url = f"{BASE_URL}{item['route']}"
            title = f"Route: {item['feature']} ({item['route']})"
            content = (
                f"Page Name: {item['feature']}\n"
                f"Direct Page URL: {full_url}\n"
                f"Relative Route: {item['route']}\n"
                f"Required Permission: {item['perm']}\n"
                f"Description: {item['desc']}"
            )

            vector = get_text_embedding(f"{title} {content}")
            KnowledgeChunk.objects.create(
                title=title,
                content=content,
                category="website_navigation",
                source_doc="Website_Routes",
                embedding=vector,
                embedding_json=vector
            )
            route_count += 1

        logger.info("IngestionService: Successfully ingested %d Website Navigation Routes.", route_count)
        return route_count
