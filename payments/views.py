from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.conf import settings
from django.shortcuts import redirect
import stripe
from subscriptions.models import SubscriptionPlan, UserSubscription, DiscountCode, Invoice, DiscountUsage
from django.utils import timezone
from django.utils import timezone
from datetime import timedelta
import re # Import re for sanitization

stripe.api_key = settings.STRIPE_SECRET_KEY

class CreateCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_id = request.data.get('plan_id')
        discount_code_str = request.data.get('discount_code')
        
        domain = f"{request.scheme}://{request.get_host()}"
        
        try:
            from .services import create_stripe_checkout_session
            
            result = create_stripe_checkout_session(
                user=request.user,
                plan_id=plan_id,
                discount_code=discount_code_str,
                domain=domain
            )
            
            return Response(result)

        except ValidationError as e:
            # Extract clean message from DRF ValidationError
            msg = e.detail
            if isinstance(msg, list) and msg:
                msg = msg[0]
            if hasattr(msg, 'string'):
                msg = msg.string
            return Response({"error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import logging
            logger = logging.getLogger("subscriptions") # Using existing logger config
            logger.error(f"CreateCheckoutSessionView failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ValidateDiscountCodeView(APIView):
    permission_classes = [AllowAny]
    from accounts.authentication import CookieJWTAuthentication
    authentication_classes = [CookieJWTAuthentication]

    def post(self, request):
        code = request.data.get('code')
        if not code:
            return Response({"valid": False, "error": "Code required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            discount = DiscountCode.objects.get(code__iexact=code.strip())
            
            # Check if user has already used THIS code
            if request.user.is_authenticated:
                from subscriptions.models import DiscountUsage
                if DiscountUsage.objects.filter(user=request.user, discount_code=discount).exists():
                     return Response({"valid": False, "error": "The coupon code has already been redeemed"})

            if discount.is_valid():
                return Response({
                    "valid": True,
                    "code": discount.code,
                    "type": "trial" if discount.is_trial else "discount",
                    "discount_percent": discount.discount_percent,
                    "duration_months": discount.duration_months
                })
            else:
                return Response({"valid": False, "error": "Code expired or invalid limit."})
        except DiscountCode.DoesNotExist:
            return Response({"valid": False, "error": "Invalid code."})

class WebhookView(APIView):
    permission_classes = [AllowAny] 

    def post(self, request):
        # LOGGING HEADER
        import logging
        logger = logging.getLogger("subscriptions")

        
        logger.info(f"--- WEBHOOK RECEIVED ---")
        
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        
        if not sig_header:
             logger.error("No Signature Header found.")
             print("debug: no sig header")
        
        event = None
        endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

        try:
            logger.info(f"--- WEBHOOK RECEIVED ---")
            logger.info(f"Configured Secret (Masked): {endpoint_secret[:5]}...{endpoint_secret[-5:]} (Len: {len(endpoint_secret)})")
            logger.info(f"Received Signature: {sig_header[:20]}...")
            
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
            logger.info(f"Event Constructed Successfully: {event['type']}")
        except ValueError as e:
            # Invalid payload
            logger.error(f"Invalid Payload: {e}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f"Signature Verification Failed: {e}")
            print(f"debug: sig fail {e}")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unknown Error constructing event: {e}")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Handle the checkout.session.completed event
        if event['type'] == 'checkout.session.completed':
            logger.info("Processing checkout.session.completed")
            session = event['data']['object']
            
            # Idempotency Check
            # Idempotency Check
            payment_intent = session.get("payment_intent")
            if payment_intent and UserSubscription.objects.filter(stripe_payment_intent=payment_intent).exists():
                print(f"--- Duplicate Webhook Event: {payment_intent} but checking for missing Invoice ---")
                logger.info(f"Duplicate Event: {payment_intent} - Checking Invoice")
                
                # RECOVERY: Ensure Invoice exists even if Subscription was already created
                try:
                    user_id = session.get('metadata', {}).get('user_id')
                    from accounts.models import User
                    
                    # Only force create if no invoice object is attached to session (meaning mode='payment' without invoice)
                    if user_id and not session.get('invoice') and not Invoice.objects.filter(stripe_id=session['id']).exists():
                         user = User.objects.get(id=user_id)
                         Invoice.objects.create(
                            user=user,
                            stripe_id=session['id'],
                            amount=session.get('amount_total', 0) / 100.0,
                            currency=session.get('currency', 'usd'),
                            status=session.get('payment_status', 'paid'),
                            invoice_pdf=None
                        )
                         logger.info(f"Recovered missing Invoice for {user_id}")
                except Exception as e:
                    logger.error(f"Invoice Recovery Failed: {e}")

                return Response(status=status.HTTP_200_OK)

            user_id = session.get('metadata', {}).get('user_id')
            plan_id = session.get('metadata', {}).get('plan_id')
            logger.info(f"Meta: User={user_id}, Plan={plan_id}")

            # Activate Subscription Logic
            try:
                from .services import activate_subscription_from_stripe_session
                success = activate_subscription_from_stripe_session(session)
                
                if success:
                    logger.info(f"Subscription Activated via Webhook for User {user_id}")
                    print(f"--- Stripe Payment Successful for User {user_id}. Subscription Activated. ---")
                else:
                    logger.error(f"Failed to activate subscription via Webhook for User {user_id}")

            except Exception as e:
                print(f"--- Error activating subscription for User {user_id}: {e} ---")
                logger.error(f"Activation Error: {e}")
                return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Handle invoice.payment_succeeded
        elif event['type'] == 'invoice.payment_succeeded':
            logger.info("Processing invoice.payment_succeeded")
            invoice = event['data']['object']
            stripe_id = invoice.get('id')
            
            # Check if exists to UPDATE
            inv_record = Invoice.objects.filter(stripe_id=stripe_id).first()
            
            if inv_record:
                # Update info (especially PDF which might be missing from Session phase)
                inv_record.status = invoice.get('status', 'paid')
                inv_record.invoice_pdf = invoice.get('invoice_pdf')
                inv_record.save()
                logger.info(f"Updated Invoice {stripe_id} with PDF link")
            else:
                # Fallback Creation (if Session webhook failed or didn't fire?)
                try:
                    # Try to find user via Customer Email
                    customer_email = invoice.get('customer_email')
                    from accounts.models import User
                    user = User.objects.filter(email=customer_email).first()
                    
                    if user:
                        Invoice.objects.create(
                            user=user,
                            stripe_id=stripe_id,
                            amount=invoice.get('amount_paid', 0) / 100.0,
                            currency=invoice.get('currency', 'usd'),
                            status=invoice.get('status', 'unknown'),
                            invoice_pdf=invoice.get('invoice_pdf')
                        )
                        print(f"--- Invoice {stripe_id} stored for {user.email} (Fallback) ---")
                        logger.info(f"Invoice stored for {user.email} (Fallback)")
                    else:
                        logger.warning(f"User not found for email {customer_email} - Invoice skipped")
                except Exception as e:
                    print(f"--- Error storing invoice {stripe_id}: {e} ---")
                    logger.error(f"Invoice Error: {e}")
        
        else:
            logger.info(f"Unhandled Event Type: {event['type']}")

        return Response(status=status.HTTP_200_OK)

class PaymentSuccessView(APIView):
    permission_classes = [AllowAny]
    from accounts.authentication import CookieJWTAuthentication
    from rest_framework.authentication import SessionAuthentication
    authentication_classes = [CookieJWTAuthentication, SessionAuthentication]

    def get(self, request):
        session_id = request.GET.get('session_id')
        
        # If no session_id, check if user is already valid (e.g. Trial or previous payment)
        if not session_id:
            if request.user.is_authenticated:
                # Check for active subscription or trial
                from subscriptions.models import UserSubscription
                if UserSubscription.objects.filter(user=request.user, is_active=True).exists():
                     from django.shortcuts import render
                     return render(request, 'Welcome.html')
            
            return redirect('dashboard')
            
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == 'paid':
                # Synchronously Activate
                from .services import activate_subscription_from_stripe_session
                activate_subscription_from_stripe_session(session)
                
                # Retrieve user to auto-login if possible? 
                # Usually user is already logged in cookie-wise.
                # If not, we can't easily force login without credentials.
                
                # Render Welcome Page
                from django.shortcuts import render
                return render(request, 'Welcome.html')
            else:
                return redirect('/#pricing')
        except Exception as e:
            print(f"Payment Success Error: {e}")
            return redirect('dashboard')
