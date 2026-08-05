from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from apps.core.tenants.models import Tenant, Property
from apps.core.accounts.services import AuthService

User = get_user_model()

class AuthenticationTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            subdomain='test',
            status='active',
            country='India',
            currency='INR',
            timezone='Asia/Kolkata'
        )
        self.property = Property.objects.create(
            tenant=self.tenant,
            name='Test Hotel',
            property_type='HOTEL',
            address_line_1='Street',
            city='Delhi',
            state='Delhi',
            country='India',
            postal_code='110001',
            contact_email='hotel@test.com',
            contact_phone='+9111223344',
            currency='INR',
            timezone='Asia/Kolkata'
        )
        self.user = User.objects.create_user(
            email='user@test.com',
            password='Password123',
            tenant=self.tenant,
            name='Test User',
            username='testuser'
        )

    def test_password_auth_success(self):
        user, msg = AuthService.authenticate_password(self.tenant, 'user@test.com', 'Password123')
        self.assertIsNotNone(user)
        self.assertEqual(user.email, self.user.email)
        self.assertEqual(msg, 'Success')
        self.assertEqual(user.failed_login_attempts, 0)

    def test_password_auth_failure_lockout(self):
        # 4 failed attempts
        for _ in range(4):
            user, msg = AuthService.authenticate_password(self.tenant, 'user@test.com', 'WrongPassword')
            self.assertNull = self.assertIsNone(user)
            self.assertEqual(msg, 'Invalid credentials.')
            
        # Re-fetch user to check counter
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 4)
        self.assertIsNone(self.user.lockout_expires_at)

        # 5th attempt locks account
        user, msg = AuthService.authenticate_password(self.tenant, 'user@test.com', 'WrongPassword')
        self.assertIsNone(user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 5)
        self.assertIsNotNone(self.user.lockout_expires_at)

        # Locked out attempt rejects immediately
        user, msg = AuthService.authenticate_password(self.tenant, 'user@test.com', 'Password123')
        self.assertIsNone(user)
        self.assertTrue('locked' in msg)

    def test_otp_request_and_verify(self):
        success, msg = AuthService.request_otp(self.tenant, 'user@test.com')
        self.assertTrue(success)
        
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.otp_code)
        self.assertIsNotNone(self.user.otp_expires_at)

        # Verify correct OTP
        user, verify_msg = AuthService.verify_otp(self.tenant, 'user@test.com', self.user.otp_code)
        self.assertIsNotNone(user)
        self.assertEqual(verify_msg, 'Success')

        # Check OTP fields are cleared
        self.user.refresh_from_db()
        self.assertIsNone(self.user.otp_code)
        self.assertIsNone(self.user.otp_expires_at)

    def test_otp_expiry(self):
        success, msg = AuthService.request_otp(self.tenant, 'user@test.com')
        self.assertTrue(success)
        
        # Manually expire the code
        self.user.refresh_from_db()
        self.user.otp_expires_at = timezone.now() - timezone.timedelta(minutes=1)
        self.user.save()

        user, verify_msg = AuthService.verify_otp(self.tenant, 'user@test.com', self.user.otp_code)
        self.assertIsNone(user)
        self.assertEqual(verify_msg, 'OTP code has expired.')


class PasswordManagementAPITests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            subdomain='test',
            status='active',
            country='India',
            currency='INR',
            timezone='Asia/Kolkata'
        )
        self.user = User.objects.create_user(
            email='user@test.com',
            password='OldPassword123',
            tenant=self.tenant,
            name='Test User',
            username='testuser'
        )
        self.client.credentials(HTTP_X_TENANT_SUBDOMAIN='test')

    def test_change_password_success(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'OldPassword123',
            'new_password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPassword123!'))

    def test_change_password_incorrect_old(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'WrongOldPassword',
            'new_password': 'NewPassword123!'
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Incorrect current password', response.data['error'])

    def test_forgot_and_reset_password_email_flow(self):
        self.user.failed_login_attempts = 0
        self.user.locked_until = None
        self.user.save()
        # Forgot password email
        response = self.client.post('/api/auth/forgot-password/', {
            'email': 'user@test.com',
            'reset_method': 'email'
        }, format='json')
        self.assertEqual(response.status_code, 200)
        token = response.data['token']
        self.assertIsNotNone(token)

        # Reset password
        reset_response = self.client.post('/api/auth/reset-password/', {
            'email': 'user@test.com',
            'token': token,
            'new_password': 'ResetPassword123!'
        }, format='json')
        self.assertEqual(reset_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('ResetPassword123!'))

    def test_forgot_and_reset_password_otp_flow(self):
        self.user.failed_login_attempts = 0
        self.user.locked_until = None
        self.user.save()
        # Forgot password OTP
        response = self.client.post('/api/auth/forgot-password/', {
            'email': 'user@test.com',
            'reset_method': 'otp'
        }, format='json')
        self.assertEqual(response.status_code, 200)
        otp = response.data['otp_code']
        self.assertIsNotNone(otp)

        # Reset password
        reset_response = self.client.post('/api/auth/reset-password/', {
            'email': 'user@test.com',
            'token': otp,
            'new_password': 'OTPResetPassword123!'
        }, format='json')
        self.assertEqual(reset_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OTPResetPassword123!'))

