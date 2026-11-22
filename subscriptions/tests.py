from django.test import TestCase
from unittest.mock import patch, MagicMock
from payments.views import CreateCheckoutSessionView
from subscriptions.models import SubscriptionPlan, DiscountCode
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate
import stripe

User = get_user_model()

class InvoiceDiscountTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.plan = SubscriptionPlan.objects.create(name="Pro Plan", price=100.00, duration_days=365)
        self.discount = DiscountCode.objects.create(code="TESTOFF", discount_percent=20)
        self.factory = APIRequestFactory()
        self.view = CreateCheckoutSessionView.as_view()

    @patch('stripe.checkout.Session.create')
    @patch('stripe.Coupon.retrieve')
    @patch('stripe.Coupon.modify')
    @patch('stripe.Coupon.create')
    @patch('stripe.Customer.list') 
    @patch('stripe.Customer.create')
    def test_checkout_session_uses_coupon(self, mock_cust_create, mock_cust_list, mock_coupon_create, mock_coupon_modify, mock_coupon_retrieve, mock_session_create):
        # Setup mocks
        mock_cust_list.return_value.data = [MagicMock(id="cus_test")]
        
        # Scenario 1: Coupon exists in Stripe
        mock_coupon_retrieve.return_value = MagicMock(id="TESTOFF")
        
        request = self.factory.post('/payments/create-checkout-session/', {
            'plan_id': self.plan.id,
            'discount_code': 'TESTOFF'
        })
        force_authenticate(request, user=self.user)
        
        response = self.view(request)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify Session Create called with correct parameters
        args, kwargs = mock_session_create.call_args
        
        # Check Unit Amount is FULL PRICE (100.00 -> 10000 cents)
        line_items = kwargs.get('line_items')
        self.assertEqual(line_items[0]['price_data']['unit_amount'], 10000)
        
        # Check Discounts parameter is present and correct
        discounts = kwargs.get('discounts')
        self.assertEqual(discounts, [{'coupon': 'TESTOFF'}])
        
        # Scenario 2: Coupon does NOT exist in Stripe (Should Create)
        mock_coupon_retrieve.side_effect = stripe.error.InvalidRequestError("Missing", "param")
        mock_coupon_create.return_value = MagicMock(id="TESTOFF")
        
        request = self.factory.post('/payments/create-checkout-session/', {
            'plan_id': self.plan.id,
            'discount_code': 'TESTOFF'
        })
        force_authenticate(request, user=self.user)
        self.view(request)
        
        mock_coupon_create.assert_called_with(
            id='TESTOFF',
            percent_off=20,
            duration='once',
            name='Discount'
        )

        # Scenario 3: Coupon exists but has wrong name (Should Modify)
        # Reset mocks
        mock_coupon_retrieve.side_effect = None
        mock_coupon_retrieve.return_value = MagicMock(id="TESTOFF", name="Old Name")
        mock_coupon_modify.reset_mock()
        
        request = self.factory.post('/payments/create-checkout-session/', {
            'plan_id': self.plan.id,
            'discount_code': 'TESTOFF'
        })
        force_authenticate(request, user=self.user)
        self.view(request)
        
        # Verify Modify called to rename to 'Discount'
        mock_coupon_modify.assert_called_with('TESTOFF', name='Discount')
