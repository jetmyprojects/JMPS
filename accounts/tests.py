from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
import jwt

User = get_user_model()

class RememberMeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='test@example.com',
            email='test@example.com',
            password='password123',
            first_name='Test',
            last_name='User'
        )
        self.login_url = reverse('login')
        self.refresh_url = reverse('token_refresh')

    def test_login_without_remember_me(self):
        """
        Test that logging in without remember_me sets a standard refresh token
        and no remember_me claim.
        """
        data = {
            'email': 'test@example.com',
            'password': 'password123',
            'remember_me': False
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check Cookie
        refresh_cookie = response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        self.assertIsNotNone(refresh_cookie)
        
        # Check Token Payload
        refresh_token = refresh_cookie.value
        payload = jwt.decode(refresh_token, options={"verify_signature": False})
        self.assertIsNone(payload.get('remember_me'), "remember_me claim should be missing or None")

    def test_login_with_remember_me(self):
        """
        Test that logging in with remember_me=True sets the custom claim
        and a longer expiry.
        """
        data = {
            'email': 'test@example.com',
            'password': 'password123',
            'remember_me': True
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Check Cookie
        refresh_cookie = response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        self.assertIsNotNone(refresh_cookie)
        
        # Assert Cookie Expiry (approximate check)
        # Django test client cookies are SimpleCookie objects. 
        # 'expires' might be empty in the object but 'max-age' might be set, or we check the token exp.
        
        # Check Token Payload
        refresh_token = refresh_cookie.value
        payload = jwt.decode(refresh_token, options={"verify_signature": False})
        self.assertTrue(payload.get('remember_me'), "remember_me claim should be True")
        
        # Check Expiry within Token
        exp = payload['exp']
        expected_min_exp = timezone.now().timestamp() + timedelta(days=29).total_seconds()
        self.assertGreater(exp, expected_min_exp, "Token expiry should be > 29 days")

    def test_refresh_persists_remember_me(self):
        """
        Test that refreshing a token with remember_me=True results in a NEW token
        that also has remember_me=True and renewed 30 day expiry.
        """
        # 1. Login with Remember Me
        data = {
            'email': 'test@example.com',
            'password': 'password123',
            'remember_me': True
        }
        login_response = self.client.post(self.login_url, data)
        original_refresh_cookie = login_response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        original_refresh_token = original_refresh_cookie.value

        # 2. Call Refresh Endpoint
        # The view expects the refresh token in the cookie
        self.client.cookies[settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH']] = original_refresh_token
        
        refresh_response = self.client.post(self.refresh_url)
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        
        # 3. Verify New Token
        new_refresh_cookie = refresh_response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        self.assertIsNotNone(new_refresh_cookie)
        new_refresh_token = new_refresh_cookie.value
        
        # Ensure token rotated (security best practice)
        self.assertNotEqual(original_refresh_token, new_refresh_token)
        
        # Verify persistence of claim
        payload = jwt.decode(new_refresh_token, options={"verify_signature": False})
        self.assertTrue(payload.get('remember_me'), "remember_me claim should persist after refresh")
        
        # Verify renewed expiry
        exp = payload['exp']
        expected_min_exp = timezone.now().timestamp() + timedelta(days=29).total_seconds()
        self.assertGreater(exp, expected_min_exp, "New token expiry should be reset to > 29 days")

    def test_refresh_without_remember_me_does_not_escalate(self):
        """
        Test that refreshing a standard token does NOT add remember_me or extend expiry.
        """
        # 1. Login WITHOUT Remember Me
        data = {
            'email': 'test@example.com',
            'password': 'password123',
            'remember_me': False
        }
        login_response = self.client.post(self.login_url, data)
        original_refresh_cookie = login_response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        original_refresh_token = original_refresh_cookie.value

        # 2. Call Refresh Endpoint
        self.client.cookies[settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH']] = original_refresh_token
        
        refresh_response = self.client.post(self.refresh_url)
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        
        # 3. Verify New Token
        new_refresh_cookie = refresh_response.cookies.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        new_refresh_token = new_refresh_cookie.value
        
        # Verify NO claim
        payload = jwt.decode(new_refresh_token, options={"verify_signature": False})
        self.assertIsNone(payload.get('remember_me'))
        
        # Verify standard expiry (default is 1 day)
        exp = payload['exp']
        # 2 days in seconds = 172800. If it's > 2 days, something is wrong.
        # Should be roughly 1 day from now.
        max_expected_exp = timezone.now().timestamp() + timedelta(days=2).total_seconds()
        self.assertLess(exp, max_expected_exp, "Token expiry should NOT be 30 days")
