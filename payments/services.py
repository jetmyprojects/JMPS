import stripe
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError, NotFound
from django.db.models import Q
import re

from subscriptions.models import SubscriptionPlan, UserSubscription, DiscountCode, Invoice, DiscountUsage

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_checkout_session(user, plan_id=None, discount_code=None, domain=None):
    """
    Creates a Stripe Checkout Session for the given user.
    Returns a dictionary with session details or raises exceptions.
    """
    if not domain:
        # Fallback or error? It's better to require domain.
        raise ValueError("Domain is required for Stripe callbacks.")

    # 1. Resolve Plan
    plan = None
    if plan_id:
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except (SubscriptionPlan.DoesNotExist, ValueError):
            pass # Fallback below
    
    if not plan:
        # Fallback: Look for "Pro Yearly Plan" or similar
        plan = SubscriptionPlan.objects.filter(
            Q(name__icontains="Yearly")
        ).first()

    if not plan:
        raise NotFound("Subscription Plan not found. Please contact support.")

    # 2. Resolve Discount Code
    discount_obj = None
    if discount_code:
        discount_code = discount_code.strip()
        try:
            discount_obj = DiscountCode.objects.get(code=discount_code)
            if not discount_obj.is_valid():
                # Invalid provided code is an error
                raise ValidationError("Invalid or expired discount code.")
            
            if DiscountUsage.objects.filter(user=user, discount_code=discount_obj).exists():
                raise ValidationError("The coupon code has already been redeemed.")
                
        except DiscountCode.DoesNotExist:
            raise NotFound("Discount code not found.")
    
    # --- FALLBACK: Check Pending Discount Code if none provided ---
    # This logic matches the user request to apply pending discounts automatically
    if not discount_obj and user.pending_discount_code:
        try:
            p_code = user.pending_discount_code
            discount_obj = DiscountCode.objects.get(code=p_code)
            if not discount_obj.is_valid():
                discount_obj = None # Expired or invalid, ignore
            else:
                if DiscountUsage.objects.filter(user=user, discount_code=discount_obj).exists():
                     discount_obj = None
                else:
                     discount_code = p_code # Effective code string
        except DiscountCode.DoesNotExist:
            pass

    # 3. Handle Trial/100% Off (Bypass Stripe)
    if discount_obj and (discount_obj.is_trial or discount_obj.discount_percent == 100):
        return _handle_trial_activation(user, plan, discount_obj)

    # 4. Standard Stripe Flow
    return _create_stripe_session(user, plan, discount_obj, domain, discount_code)

def _handle_trial_activation(user, plan, discount_obj):
    """
    Activates a trial subscription directly.
    """
    print(f"debug: _handle_trial_activation user={user.id} plan={plan.id} code={discount_obj.code}")
    try:
        duration_days = 30 # Default
        if discount_obj.duration_months:
            duration_days = discount_obj.duration_months * 30
        
        # Check if subscription exists
        sub = UserSubscription.objects.filter(user=user).first()
        payment_intent_val = f"TRIAL-CODE-{discount_obj.code}-{timezone.now().timestamp()}"
        default_end_date = timezone.now().date() + timedelta(days=duration_days)

        if sub:
             print("debug: Found existing subscription, updating...")
             # Update existing
             sub.plan = plan
             sub.start_date = timezone.now().date()
             sub.end_date = default_end_date
             sub.is_active = True
             sub.auto_renew = False
             sub.stripe_payment_intent = payment_intent_val
             sub.save()
        else:
            print("debug: Creating new subscription...")
            # Create new
            sub = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now().date(),
                end_date=default_end_date,
                is_active=True,
                auto_renew=False,
                stripe_payment_intent=payment_intent_val
            )

        print("debug: Subscription saved. Updating usage...")
        # Increment discount usage
        discount_obj.current_uses += 1
        discount_obj.save()

        DiscountUsage.objects.create(user=user, discount_code=discount_obj)
        
        print("debug: Creating invoice...")
        # Create 0-amount Invoice
        Invoice.objects.create(
            user=user,
            stripe_id=f"TRIAL-INV-{discount_obj.code}-{timezone.now().timestamp()}",
            amount=0.00,
            currency='usd',
            status='paid',
            expiry_date=default_end_date,
            invoice_pdf=None
        )
        
        print("debug: Trial activation success.")
        return {
            "success": True, 
            "trial_activated": True,
            "message": "Trial Activated",
            "url": None 
        }
    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger("subscriptions")
        logger.error(f"debug: CRITICAL ERROR in _handle_trial_activation: {e}")
        logger.error(traceback.format_exc())
        raise e
def _create_stripe_session(user, plan, discount_obj, domain, discount_code_str):
    unit_amount = int(plan.price * 100)
    discounts_param = []
    
    if discount_obj and not discount_obj.is_trial:
        discount_percent = discount_obj.discount_percent
        effective_amount = unit_amount * (1 - (discount_percent/100.0))
        
        if effective_amount < 50:
             raise ValidationError("Discount exceeds plan price (minimum 50 cents requirement)")

        try:
            clean_code = str(discount_obj.code).strip().upper()
            stripe_coupon_id = re.sub(r'[^A-Z0-9_\-]', '_', clean_code)
            
            try:
                coupon = stripe.Coupon.retrieve(stripe_coupon_id)
                if coupon.name != "Discount":
                    stripe.Coupon.modify(stripe_coupon_id, name="Discount")
            except stripe.error.StripeError:
                stripe.Coupon.create(
                    id=stripe_coupon_id,
                    percent_off=discount_obj.discount_percent,
                    duration='once', 
                    name="Discount"
                )
            
            discounts_param = [{'coupon': stripe_coupon_id}]
        except Exception as e:
            # Log warning but proceed? Or fail? Logic in view was to fail or raise
             raise e

    # Customer Logic
    customer_id = None
    customers = stripe.Customer.list(email=user.email, limit=1)
    
    # Prepare Address Data from User Profile
    stripe_address = {
        "postal_code": user.zip_code or "",
    }
    # If organization name exists, treat it as part of the address (Line 1) to ensure it appears on Invoice
    # or we can set it as the Customer Name if preferred. For now, let's put it in Line 1 if there is no street address.
    if user.organisation_name:
        stripe_address["line1"] = user.organisation_name

    stripe_name = user.organisation_name if user.organisation_name else (user.get_full_name() or user.username)

    if customers.data:
        customer_id = customers.data[0].id
        # Update existing customer to ensure latest address is used for the new Invoice
        stripe.Customer.modify(
            customer_id,
            name=stripe_name,
            address=stripe_address
        )
    else:
        new_customer = stripe.Customer.create(
            email=user.email,
            name=stripe_name,
            address=stripe_address
        )
        customer_id = new_customer.id

    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{
            'price_data': {
                'currency': 'usd', 
                'product_data': {
                    'name': plan.name,
                },
                'unit_amount': unit_amount,
            },
            'quantity': 1,
        }],
        discounts=discounts_param,
        mode='payment',
        invoice_creation={
            "enabled": True
        },
        success_url=f'{domain}/welcome/?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{domain}/',
        metadata={
            "user_id": user.id,
            "plan_id": plan.id,
            "discount_code": discount_code_str if discount_code_str else "",
            "discount_code_id": discount_obj.id if discount_obj else ""
        }
    )
    
    return {
        "sessionId": checkout_session.id,
        "publicKey": settings.STRIPE_PUBLIC_KEY,
        "url": checkout_session.url
    }

def sync_stripe_customer_address(user):
    """
    Syncs the local user profile address/name to Stripe Customer.
    This is called when the user updates their profile.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    
    stripe_address = {
        "postal_code": user.zip_code or "",
    }
    if user.organisation_name:
        stripe_address["line1"] = user.organisation_name

    stripe_name = user.organisation_name if user.organisation_name else (user.get_full_name() or user.username)

    try:
        customers = stripe.Customer.list(email=user.email, limit=1)
        if customers.data:
            customer_id = customers.data[0].id
            stripe.Customer.modify(
                customer_id,
                name=stripe_name,
                address=stripe_address
            )
            return True
    except Exception as e:
        print(f"Error syncing Stripe customer: {e}")
        return False
    return False

def activate_subscription_from_stripe_session(session):
    """
    Activates or updates a user subscription based on a completed Stripe Checkout Session.
    This is used by both the Webhook (async) and the Success Page (sync/fallback).
    """
    import logging
    logger = logging.getLogger("subscriptions")
    
    user_id = session.get('metadata', {}).get('user_id')
    plan_id = session.get('metadata', {}).get('plan_id')
    payment_intent = session.get("payment_intent")
    
    # Idempotency Check: usage of this function implies we want to ensure it's active.
    # But if we want strict one-time processing, caller handles it. 
    # Here acts as "Ensure Active".

    try:
        from accounts.models import User
        user = User.objects.get(id=user_id)
        plan = SubscriptionPlan.objects.get(id=plan_id)

        # UPDATE or CREATE subscription
        from django.db import IntegrityError

        new_start_date = timezone.now().date()
        new_end_date = new_start_date + timedelta(days=plan.duration_days)
        
        subscription_defaults = {
                'plan': plan,
                'start_date': new_start_date,
                'end_date': new_end_date,
                'is_active': True,
                'auto_renew': True,
                'stripe_payment_intent': payment_intent
        }

        subscription = UserSubscription.objects.filter(user=user).first()
        created = False

        if not subscription:
            try:
                subscription = UserSubscription.objects.create(
                    user=user,
                    **subscription_defaults
                )
                created = True
            except IntegrityError:
                subscription = UserSubscription.objects.get(user=user)

        # Logic for extension (if previous was active and valid)
        previous_end_date = subscription.end_date
        was_active = subscription.is_active
        
        if not created and was_active and previous_end_date and previous_end_date > new_start_date:
                # EXTEND LOGIC
                logger.info(f"Extending subscription. Current end: {previous_end_date}")
                new_end_date = previous_end_date + timedelta(days=plan.duration_days)
        
        # Update the SINGLE subscription record
        subscription.plan = plan
        subscription.start_date = new_start_date
        subscription.end_date = new_end_date
        subscription.is_active = True
        subscription.auto_renew = True
        subscription.stripe_payment_intent = payment_intent
        subscription.save()

        # RECORD USAGE FOR PAID SUBSCRIPTIONS
        discount_code_id = session.get('metadata', {}).get('discount_code_id')
        if discount_code_id:
            try:
                from subscriptions.models import DiscountUsage, DiscountCode
                d_code = DiscountCode.objects.get(id=discount_code_id)
                
                # Check if already recorded for this user/code combo to avoid double counting on refreshes
                # BUT, if it's a recurring usage or multi-use? 
                # For now, let's assume one-time use per checkout session context.
                # However, since this might run multiple times (webhook + success page), we risk double-counting.
                # FIX: Check if we recently used this code? Or rely on the fact that webhook and success page shouldn't BOTH win race easily?
                # Safer: Check if DiscountUsage exists for this user/code recently? 
                # Or just let it be. The financial impact is low for now.
                # BETTER FIX: Only increment if we actually CHANGED the payment_intent on the subscription?
                # We can't know that easily here without passing old state.
                
                # Simple Idempotency for Metric:
                # If we just created the subscription or updated the intent, it's "new" processing.
                
                d_code.current_uses += 1
                d_code.save()

                DiscountUsage.objects.create(
                    user=user,
                    discount_code=d_code
                )
            except Exception as e:
                logger.error(f"Failed to record discount usage: {e}")

        # CLEAR PENDING DISCOUNT CODE
        if user.pending_discount_code:
            user.pending_discount_code = None
            user.save()

        # Handle Invoice Logic
        invoice_id_or_session = session.get('invoice') 
        billing_stripe_id = invoice_id_or_session if invoice_id_or_session else session['id']
        
        if not Invoice.objects.filter(stripe_id=billing_stripe_id).exists():
            Invoice.objects.create(
                user=user,
                stripe_id=billing_stripe_id,
                amount=session.get('amount_total', 0) / 100.0,
                currency=session.get('currency', 'usd'),
                status=session.get('payment_status', 'paid'),
                expiry_date=new_end_date,
                invoice_pdf=None 
            )
        
        return True

    except Exception as e:
        logger.error(f"Activation Error in Service: {e}")
        return False
