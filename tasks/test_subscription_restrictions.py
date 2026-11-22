from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework import status
from tasks.models import Task
from subscriptions.models import UserSubscription, SubscriptionPlan

User = get_user_model()

@override_settings(SECURE_SSL_REDIRECT=False)
class SubscriptionRestrictionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        
        # Create a task for testing actions
        self.task = Task.objects.create(
            user=self.user,
            project_name='Test Project',
            deadline_date=timezone.now().date(),
            status='ACTIVE'
        )

        # Create a subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name='Test Plan',
            price=10.00,
            duration_days=30,
            features='{"test": "feature"}'
        )

    def test_actions_allowed_with_active_subscription(self):
        """Test that actions are allowed when subscription is active"""
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=True
        )
        
        # Create
        response = self.client.post('/api/v1/tasks/', {
            'project_name': 'New Project Active',
            'deadline_date': timezone.now().date(),
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Complete
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/complete/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_actions_restricted_with_expired_subscription(self):
        """Test that actions are restricted when subscription is expired (past end_date)"""
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now().date() - timedelta(days=60),
            end_date=timezone.now().date() - timedelta(days=1), # Expired yesterday
            is_active=True # Even if technically marked active, date is past
        )

        # Create
        response = self.client.post('/api/v1/tasks/', {
            'project_name': 'New Project Expired',
            'deadline_date': timezone.now().date(),
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('expired', str(response.data.get('detail', '')))

        # Delete
        response = self.client.delete(f'/api/v1/tasks/{self.task.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Duplicate
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/duplicate/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Complete
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/complete/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Activate
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/activate/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Restore
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/restore/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Permanent Delete
        response = self.client.delete(f'/api/v1/tasks/{self.task.id}/permanent_delete/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # Toggle Pin
        response = self.client.post(f'/api/v1/tasks/{self.task.id}/toggle_pin/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_actions_restricted_with_inactive_subscription(self):
        """Test that actions are restricted when subscription is marked inactive"""
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            is_active=False # Explicitly inactive
        )

        # Create
        response = self.client.post('/api/v1/tasks/', {
            'project_name': 'New Project Inactive',
            'deadline_date': timezone.now().date(),
            'status': 'ACTIVE'
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewing_allowed_when_expired(self):
        """Test that viewing tasks is still allowed when expired"""
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now().date() - timedelta(days=60),
            end_date=timezone.now().date() - timedelta(days=1),
            is_active=True
        )

        response = self.client.get('/api/v1/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see the existing task
        data = response.data
        if hasattr(data, 'get'):
            results = data.get('results', data)
        else:
            results = data
        self.assertEqual(len(results), 1)
