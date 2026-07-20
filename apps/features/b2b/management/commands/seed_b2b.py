from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.core.tenants.models import Tenant
from apps.features.b2b.models import B2BPartner

class Command(BaseCommand):
    help = 'Seeds B2B Partners and Travel Agents data matching the frontend UI.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding B2B partners data...")

        # 1. Resolve Tenant
        tenant = Tenant.objects.filter(status='active').first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No active tenant found to seed B2B Partners."))
            return

        # 2. Define the mock partners
        partners_data = [
            {
                "agent_id": "AGT-99281",
                "name": "Global Escapes Travel",
                "contact_person": "Sarah Jenkins",
                "email": "contact@globalescapes.com",
                "phone": "+91 98765 43210",
                "location": "Gurgaon, India",
                "status": "Pending KYC",
                "commission_rate": 0,
                "credit_limit": Decimal("0.00"),
                "incorporation_document": "inc_cert_99281.pdf",
                "owner_id_document": "owner_id_99281.pdf",
                "cheque_document": "cheque_99281.pdf"
            },
            {
                "agent_id": "AGT-33421",
                "name": "Wanderlust Travels",
                "contact_person": "Rahul Sharma",
                "email": "rahul@wanderlust.in",
                "phone": "+91 91234 56789",
                "location": "Mumbai, India",
                "status": "Approved",
                "commission_rate": 15,
                "credit_limit": Decimal("200000.00"),
                "incorporation_document": "inc_cert_33421.pdf",
                "owner_id_document": "owner_id_33421.pdf",
                "cheque_document": "cheque_33421.pdf"
            },
            {
                "agent_id": "AGT-11002",
                "name": "Nomad Adventures",
                "contact_person": "Priya Desai",
                "email": "priya@nomad.com",
                "phone": "+91 99887 77665",
                "location": "Bangalore, India",
                "status": "Rejected",
                "commission_rate": 0,
                "credit_limit": Decimal("0.00"),
                "incorporation_document": "inc_cert_11002.pdf",
                "owner_id_document": "owner_id_11002.pdf",
                "cheque_document": None
            }
        ]

        # 3. Create or update partners
        for data in partners_data:
            agent_id = data.pop("agent_id")
            partner, created = B2BPartner.objects.update_or_create(
                tenant=tenant,
                agent_id=agent_id,
                defaults=data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created B2B Partner: {partner.name} ({agent_id})"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated B2B Partner: {partner.name} ({agent_id})"))

        self.stdout.write(self.style.SUCCESS("B2B Partners data seeding complete!"))
