from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.core.accounts.models import AppUser
from apps.core.tenants.models import Tenant
from apps.features.b2b.models import B2BPartner

class B2BPartnerAPITests(APITestCase):

    @classmethod
    def setUpTestData(cls):
        # 1. Setup Tenant
        cls.tenant = Tenant.objects.create(
            name="Beta Grand", subdomain="betagrand", status="active",
            country="IN", currency="INR", timezone="Asia/Kolkata"
        )
        # 2. Setup Superuser
        cls.superuser = AppUser.objects.create_superuser(
            username="adminuser", email="admin@beta.com", password="password", tenant=cls.tenant
        )
        # 3. Setup standard User
        cls.staff_user = AppUser.objects.create_user(
            username="staffuser", email="staff@beta.com", password="password", tenant=cls.tenant
        )

    def setUp(self):
        # Authenticate staff user by default
        self.client.force_authenticate(user=self.staff_user)

    def test_b2b_partner_model_generation(self):
        # Test model creation and auto-agent_id generation
        partner = B2BPartner.objects.create(
            tenant=self.tenant,
            name="Travel Agent A",
            contact_person="John Doe",
            email="john@agent.com",
            phone="+91 99999 88888",
            location="Delhi, India",
            status="Pending KYC"
        )
        self.assertIsNotNone(partner.agent_id)
        self.assertTrue(partner.agent_id.startswith("AGT-"))
        self.assertEqual(len(partner.agent_id), 9)  # AGT- + 5 digits = 9 chars

    def test_b2b_partner_crud(self):
        # Create a partner
        partner = B2BPartner.objects.create(
            tenant=self.tenant,
            name="Travel Agent B",
            contact_person="Jane Doe",
            email="jane@agent.com",
            phone="+91 99999 77777",
            location="Mumbai, India",
            status="Pending KYC",
            incorporation_document="inc_cert_b.pdf"
        )

        # GET list
        # We pass HTTP_X_TENANT_SUBDOMAIN='betagrand' to resolve tenant subdomain
        url_list = reverse('b2bpartner-list')
        response = self.client.get(url_list, HTTP_X_TENANT_SUBDOMAIN='betagrand')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        partner_data = response.data[0]
        self.assertEqual(partner_data['name'], "Travel Agent B")
        self.assertEqual(partner_data['contact'], "Jane Doe")
        # FileField serialized URL should end with filename
        self.assertTrue(partner_data['documents']['incorporation'].endswith("inc_cert_b.pdf"))

        # GET detail using lookup_field agent_id
        url_detail = reverse('b2bpartner-detail', kwargs={'agent_id': partner.agent_id})
        response = self.client.get(url_detail, HTTP_X_TENANT_SUBDOMAIN='betagrand')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], partner.agent_id)

        # PUT update (approve agent with commercials)
        update_data = {
            "name": "Travel Agent B Updated",
            "contact": "Jane Doe Updated",
            "email": "jane@agent.com",
            "phone": "+91 99999 77777",
            "location": "Mumbai, India",
            "status": "Approved",
            "commission": 15,
            "creditLimit": 150000.00,
            "documents": {
                "incorporation": "inc_cert_b_updated.pdf",
                "ownerId": "owner_id_b.pdf",
                "cheque": "cheque_b.pdf"
            }
        }
        response = self.client.put(url_detail, update_data, format='json', HTTP_X_TENANT_SUBDOMAIN='betagrand')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify db update
        partner.refresh_from_db()
        self.assertEqual(partner.status, "Approved")
        self.assertEqual(partner.commission_rate, 15)
        self.assertEqual(partner.credit_limit, Decimal("150000.00"))
        self.assertTrue(partner.incorporation_document.name.endswith("inc_cert_b_updated.pdf"))
        self.assertTrue(partner.owner_id_document.name.endswith("owner_id_b.pdf"))
        self.assertTrue(partner.cheque_document.name.endswith("cheque_b.pdf"))

    def test_multipart_file_upload(self):
        inc_file = SimpleUploadedFile("inc.pdf", b"incorporation content", content_type="application/pdf")
        owner_file = SimpleUploadedFile("owner.png", b"owner id content", content_type="image/png")
        cheque_file = SimpleUploadedFile("cheque.pdf", b"cheque content", content_type="application/pdf")

        # Flat fields multipart upload format
        post_data = {
            "name": "Satish Meher",
            "contact": "mytrip agent",
            "email": "satish@mytrip.com",
            "phone": "9987766765",
            "location": "Bhubaneswar",
            "status": "Pending KYC",
            "commission": 22,
            "creditLimit": 100000.00,
            "incorporation": inc_file,
            "ownerId": owner_file,
            "cheque": cheque_file
        }

        url_list = reverse('b2bpartner-list')
        response = self.client.post(url_list, post_data, format='multipart', HTTP_X_TENANT_SUBDOMAIN='betagrand')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify nested documents in response contain full file URL paths
        docs = response.data['documents']
        self.assertTrue('inc' in docs['incorporation'] and docs['incorporation'].endswith('.pdf'))
        self.assertTrue('owner' in docs['ownerId'] and docs['ownerId'].endswith('.png'))
        self.assertTrue('cheque' in docs['cheque'] and docs['cheque'].endswith('.pdf'))

    def test_external_url_inputs(self):
        # Post data with external Google Drive links
        post_data = {
            "name": "Satish Meher URL Test",
            "contact": "url agent",
            "email": "url@mytrip.com",
            "phone": "9987766760",
            "location": "Bhubaneswar",
            "status": "Pending KYC",
            "commission": 10,
            "creditLimit": 50000.00,
            "documents": {
                "incorporation": "https://drive.google.com/file/d/1inc_drive_link/view",
                "ownerId": "https://drive.google.com/file/d/1owner_drive_link/view",
                "cheque": "https://drive.google.com/file/d/1cheque_drive_link/view"
            }
        }

        url_list = reverse('b2bpartner-list')
        response = self.client.post(url_list, post_data, format='json', HTTP_X_TENANT_SUBDOMAIN='betagrand')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verify nested documents in response contain exactly the Drive URLs passed
        docs = response.data['documents']
        self.assertEqual(docs['incorporation'], "https://drive.google.com/file/d/1inc_drive_link/view")
        self.assertEqual(docs['ownerId'], "https://drive.google.com/file/d/1owner_drive_link/view")
        self.assertEqual(docs['cheque'], "https://drive.google.com/file/d/1cheque_drive_link/view")
