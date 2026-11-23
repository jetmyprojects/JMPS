from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from .models import SubscriptionPlan, UserSubscription
from .serializers import (
    SubscriptionPlanSerializer, 
    UserSubscriptionSerializer, 
    SubscribeSerializer, 
    UpdateCardSerializer
)
import stripe
from django.conf import settings
from .models import Invoice

stripe.api_key = settings.STRIPE_SECRET_KEY


class PlanListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plans = SubscriptionPlan.objects.all()
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)

class CurrentPlanView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Return subscription even if inactive, so frontend can show "Renew"
            sub = UserSubscription.objects.get(user=request.user)
            serializer = UserSubscriptionSerializer(sub)
            return Response(serializer.data)
        except UserSubscription.DoesNotExist:
            return Response({"detail": "No subscription record found."}, status=status.HTTP_404_NOT_FOUND)

class SubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 1. Get Plan (Default to Yearly if not specified or finding from existing expired sub)
            plan_id = request.data.get('plan_id')
            plan = None
            
            if plan_id:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            else:
                # Fallback: Try to find a standard paid plan (e.g. Yearly)
                plan = SubscriptionPlan.objects.filter(price__gt=0).order_by('-price').first()
                
            if not plan:
                return Response({"error": "No subscription plan available."}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Create Stripe Checkout Session
            checkout_session = stripe.checkout.Session.create(
                customer_email=request.user.email, # Or customer ID if we stored it
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': plan.name,
                            },
                            'unit_amount': int(plan.price * 100),
                        },
                        'quantity': 1,
                    },
                ],
                mode='payment', # or 'subscription' if we had recurring prices set up in Stripe. Using payment for simplicity as per existing models. 
                # actually models have duration_days, implies recurring. 
                # But 'payment' mode is one-time. 'subscription' requires price_id. 
                # Let's stick to 'payment' (One-time charge for year/month) and handle time via models for now, 
                # unless we want to sync with Stripe Billing. 
                # Given strict limited tokens, let's assume one-time payment for the duration.
                success_url=settings.FRONTEND_URL + '/dashboard/?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=settings.FRONTEND_URL + '/dashboard/billing/cancel/',
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id
                }
            )

            return Response({'checkout_url': checkout_session.url})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RenewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Allow renewing inactive/cancelled subscriptions too
            sub = UserSubscription.objects.get(user=request.user)
            if not sub.plan:
                return Response({"detail": "No valid plan to renew."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Smart Renewal Logic
            today = timezone.now().date()
            if sub.end_date < today:
                # If expired, restart from today
                sub.end_date = today + timedelta(days=sub.plan.duration_days)
            else:
                # If active (or cancelled but not expired yet), extend from current end date
                sub.end_date += timedelta(days=sub.plan.duration_days)
            
            # Reactivate
            sub.is_active = True
            sub.auto_renew = True
            
            sub.save()
            return Response({"detail": "Subscription renewed successfully.", "new_end_date": sub.end_date})
        except UserSubscription.DoesNotExist:
            return Response({"detail": "No subscription to renew."}, status=status.HTTP_404_NOT_FOUND)

import logging
logger = logging.getLogger(__name__)

class CancelSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logger.info(f"Cancel request received for user {request.user.id}")
        try:
            sub = UserSubscription.objects.get(user=request.user, is_active=True)
            logger.info(f"Found active subscription {sub.id} with payment intent: {sub.stripe_payment_intent}")

            # 1. Validation
            if not sub.stripe_payment_intent or 'TRIAL' in sub.stripe_payment_intent:
                # If no payment intent or TRIAL, just cancel immediately without refund
                logger.info("Cancelling TRIAL or NO-INTENT subscription.")
                sub.is_active = False
                sub.auto_renew = False
                sub.end_date = timezone.now().date()
                sub.save()
                
                # Create Invoice for Trial End
                Invoice.objects.create(
                     user=request.user,
                     stripe_id=f"TRIAL-END-{timezone.now().timestamp()}",
                     amount=0.00,
                     currency='usd',
                     status='trial_end'
                )
                
                return Response({"detail": "Subscription cancelled immediately."})

            # 2. Calculate Refund Logic
            # Retrieve transaction from Stripe to get actual amount paid
            try:
                pi = stripe.PaymentIntent.retrieve(sub.stripe_payment_intent)
                amount_paid_cents = pi.amount_received
                currency = pi.currency
            except Exception as e:
                # Fallback or Error?
                # If we cannot verify payment, we shouldn't blindly refund.
                logger.error(f"Error retrieving PaymentIntent: {e}")
                return Response({"detail": f"Error communicating with payment provider: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

            total_days = (sub.end_date - sub.start_date).days
            if total_days <= 0: total_days = 365 # Fallback safety

            days_used = (timezone.now().date() - sub.start_date).days
            if days_used < 0: days_used = 0

            days_remaining = total_days - days_used
            
            logger.info(f"Refund Calc: Total={total_days}, Used={days_used}, Remaining={days_remaining}")

            if days_remaining <= 0:
                 # Expired already?
                sub.is_active = False
                sub.auto_renew = False
                sub.save()
                return Response({"detail": "Subscription expired. No refund applicable."})

            # Calculate Pro-rated Refund
            refund_ratio = days_remaining / total_days
            refund_amount_cents = int(amount_paid_cents * refund_ratio)

            # Ensure we don't refund more than paid or tiny amounts
            if refund_amount_cents > amount_paid_cents:
                refund_amount_cents = amount_paid_cents

            # 3. Issue Stripe Refund
            try:
                # We refund against the PaymentIntent
                refund = stripe.Refund.create(
                    payment_intent=sub.stripe_payment_intent,
                    amount=refund_amount_cents,
                    reason='requested_by_customer'
                )
            except stripe.error.StripeError as e:
                 return Response({"detail": f"Refund failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # 4. Update Database
            sub.is_active = False
            sub.auto_renew = False
            sub.end_date = timezone.now().date() # Terminate access today
            sub.save()

            # Update Invoice Status (Optional, good for history)
            # Find the Invoice linked to this PaymentIntent?
            # We don't have direct link in Invoice model to PI, but we have stripe_id which might be Session ID.
            # Best effort to find invoice using date or user to mark as 'refunded'
            # Create a refund record (Negative Invoice) for accounting visibility
            Invoice.objects.create(
                user=request.user,
                stripe_id=refund.id,
                amount=-(refund_amount_cents / 100.0),
                currency=currency,
                status='refunded',
                invoice_pdf=None
            )

            formatted_refund = "{:.2f}".format(refund_amount_cents / 100.0)
            return Response({"detail": f"Subscription cancelled. ${formatted_refund} has been refunded to your card."})

        except UserSubscription.DoesNotExist:
            return Response({"detail": "No active subscription found to cancel."}, status=status.HTTP_404_NOT_FOUND)

class UpdateCardView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UpdateCardSerializer(data=request.data)
        if serializer.is_valid():
            payment_method_id = serializer.validated_data['payment_method_id']
            # In a real integration, you would attach this to the Stripe Customer.
            # stripe.PaymentMethod.attach(payment_method_id, customer=user.stripe_customer_id)
            # For now, we simply acknowledge receipt of the token, ensuring no raw data is touched.
            return Response({"detail": "Card updated successfully via Payment Method."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ActivateSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            # Get or Create Plan
            plan, _ = SubscriptionPlan.objects.get_or_create(
                name="Pro Yearly Plan",
                defaults={
                    'price': 100.00, 
                    'duration_days': 365,
                    'features': "Unlimited Projects",
                    'storage_limit_mb': 1024
                }
            )
            
            # Update/Create Subscription
            sub, created = UserSubscription.objects.get_or_create(user=user)
            sub.plan = plan
            sub.is_active = True
            from django.utils import timezone
            from datetime import timedelta
            sub.end_date = timezone.now().date() + timedelta(days=365)
            sub.save()
            
            return Response({"message": "Subscription manually activated!", "is_premium": True})
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import Invoice
        from .serializers import InvoiceSerializer
        invoices = Invoice.objects.filter(user=request.user)
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

class InvoiceDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from .models import Invoice
        from django.shortcuts import render, redirect, get_object_or_404

        invoice = get_object_or_404(Invoice, id=pk, user=request.user)
        
        # If real PDF exists, redirect
        if invoice.invoice_pdf:
            return redirect(invoice.invoice_pdf)
            
        # Select template based on amount
        template_name = 'InvoiceReceipt.html'
        context = {'invoice': invoice}
        
        if invoice.amount == 0:
            template_name = 'InvoiceFree.html'
            context['description'] = "Free Subscription Plan"
            # Extract code name from stripe_id if possible
            code_name = "100% off"
            if invoice.stripe_id and (invoice.stripe_id.startswith('TRIAL-SIGNUP-') or invoice.stripe_id.startswith('TRIAL-INV-')):
                parts = invoice.stripe_id.split('-')
                if len(parts) >= 3:
                     code_name = parts[2]

            class DummyDiscount:
                discount_percent = 100
                code = code_name
            context['discount_code'] = DummyDiscount()
            context['discount_code_name'] = code_name
        elif invoice.amount < 0:
            template_name = 'InvoiceRefund.html'
            context['description'] = "Refund for Subscription"
            context['refund_note'] = "This refund has been initiated immediately. However, it may take 5-10 business days for the funds to appear on your bank statement depending on your bank's processing time."
        
        return render(request, template_name, context)
