from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import UserSubscription

class FreeAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        
        # If not authenticated via legacy session, try JWT for API paths
        if not user.is_authenticated and request.path.startswith('/api/'):
            from rest_framework_simplejwt.authentication import JWTAuthentication
            try:
                auth_result = JWTAuthentication().authenticate(request)
                if auth_result:
                    user, _ = auth_result
                    request.user = user # Attach to request for downstream use
            except Exception:
                pass # Invalid token or none

        if user.is_authenticated:
            path = request.path
            
            # Exempt paths:
            # - Static/Media (handled by upstream usually, but good practice)
            # - Admin
            # - Logout (Frontend & API)
            # - Pricing/Billing pages (so they can upgrade)
            # - Billing/Payment APIs
            # - The Expired Page itself
            
            if (path.startswith('/static/') or 
                path.startswith('/media/') or 
                path.startswith('/admin/') or 
                
                # Logout
                path.startswith('/dashboard/sign-out/') or
                path.startswith('/api/v1/accounts/auth/logout/') or
                path.startswith('/accounts/auth/logout/') or # Just in case
                
                # Profile (Allow cancelled users to access profile)
                path.startswith('/dashboard/profile/') or
                
                # Account Deletion
                path.startswith('/api/v1/accounts/user/delete/') or

                # Pricing & Billing Frontend
                path.startswith('/dashboard/pricing/') or
                path.startswith('/dashboard/billing/') or
                
                # Billing & Payment APIs
                path.startswith('/api/v1/billing/') or
                path.startswith('/api/v1/payments/') or
                
                # The Destination
                path == '/accounts/access-expired/' or
                path.startswith('/accounts/access-expired/')):
                
                return self.get_response(request)

            # Check Subscription
            # We check if they have ANY active subscription/plan that isn't null.
            # Assuming 'Free' plan might be a Subscription object or just lack thereof.
            # The prompt implies "Free user access only for 24hr", meaning if they haven't paid.
            
            has_active_sub = UserSubscription.objects.filter(
                user=request.user, 
                is_active=True
            ).exclude(plan=None).exists()
            
            # Note: Depending on logic, a "Free Plan" might exist in DB. 
            # If "Free Plan" users are also restricted, we might need to check plan details.
            # But usually "Free User" means no paid subscription.
            # Let's assume if they have a UserSubscription with a Plan, they are "Paid" or at least "Subscribed".
            # If the user model has a free tier by default without a UserSubscription entry, this works.
            # If they have a UserSubscription entry for "Free Tier", we might need to check plan price > 0.
            
            # Let's refine: Check if they have a subscription with price > 0 OR if the model implies paid.
            # subscriptions/models.py: SubscriptionPlan has 'price'.
            
            is_paid_user = False
            active_sub = UserSubscription.objects.select_related('plan').filter(
                user=request.user, 
                is_active=True
            ).first()
            
            if active_sub and active_sub.plan and active_sub.plan.price > 0:
                is_paid_user = True
            
            # Exempt Staff/Admins from expiration
            if request.user.is_staff or request.user.is_superuser:
                is_paid_user = True

            # CHECK FOR EXPIRED TRIALS / SUBSCRIPTIONS
            # If user had a subscription but it is now inactive or expired, we should treat them as expired.
            # Especially for "Free Trial" codes.
            
            # Find the most recent subscription (active or not)
            latest_sub = UserSubscription.objects.filter(user=request.user).order_by('-end_date').first()
            
            if latest_sub:
                # Check if this was a trial
                is_trial = latest_sub.stripe_payment_intent and 'TRIAL' in str(latest_sub.stripe_payment_intent).upper()
                 
                # Check if expired
                is_expired = False
                if latest_sub.end_date and latest_sub.end_date < timezone.now().date():
                    is_expired = True
                if not latest_sub.is_active: 
                    is_expired = True
                     
                if is_trial and is_expired and not is_paid_user:
                    # User requested to allow access even if trial expired
                    pass 
                
            if not is_paid_user and not latest_sub:
                # Check 24h limit
                join_date = request.user.date_joined
                now = timezone.now()
                
                if (now - join_date) > timedelta(hours=24):
                    # Expired Logic:
                    # BLOCK ALL ACCESS (Read-Only allows them to see dashboard, we want to force upgrade)
                    
                    if request.path.startswith('/api/'):
                        from django.http import JsonResponse
                        return JsonResponse(
                            {"detail": "Trial expired. Please upgrade to continue."}, 
                            status=403
                        )
                    
                    # For page loads, redirect to pricing
                    return redirect('/')

        return self.get_response(request)
