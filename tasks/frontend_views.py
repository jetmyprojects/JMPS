from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from payments.services import create_stripe_checkout_session
from tasks.views import TaskViewSet
from subscriptions.models import UserSubscription
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

@method_decorator(never_cache, name='dispatch')
class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        
        # Check Subscription Status
        is_active = self._check_subscription(user)
        
        if not is_active:
            # Redirect to Stripe Checkout with auto-applied logic
            domain = f"{request.scheme}://{request.get_host()}"
            try:
                # We don't pass discount_code here, relying on pending_discount_code in service
                result = create_stripe_checkout_session(
                    user=user,
                    domain=domain
                )
                
                # Check if it was a trial activation (returns success dict, no URL usually, but service returns URL=None)
                if result.get('trial_activated'):
                     # If trial activated immediately, redirect to Dashboard (reload)
                     return redirect('dashboard')
                
                checkout_url = result.get('url')
                if checkout_url:
                    return redirect(checkout_url)
                
            except Exception as e:
                # If error, maybe redirect to a specific error page or generic signup?
                # For now, just render an error or fallback to pricing
                print(f"Checkout Redirect Error: {e}")
                return redirect('/#pricing')

        return render(request, 'Dashboard.html')

    def _check_subscription(self, user):
        """
        Duplicate of TaskViewSet._check_subscription_status to avoid importing ViewSet constraints.
        """
        if user.is_staff or user.is_superuser:
            return True

        try:
            # Logic Update: Allow access to anyone who has EVER had a subscription record
            # regardless of current status or expiry.
            UserSubscription.objects.get(user=user)
            return True
        except UserSubscription.DoesNotExist:
            return False

@method_decorator(never_cache, name='dispatch')
class NewTaskView(LoginRequiredMixin, TemplateView):
    template_name = 'NewTask.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass server time in ISO format (UTC)
        # Pass server time in ISO format (UTC)
        context['server_now'] = timezone.now().isoformat()
        
        # Calculate default deadline based on User Profile Timezone
        user = self.request.user
        now = timezone.now()
        target_tz = timezone.get_current_timezone() # Default fallback

        if user.is_authenticated and hasattr(user, 'timezone') and user.timezone:
            import pytz
            try:
                target_tz = pytz.timezone(user.timezone)
            except pytz.UnknownTimeZoneError:
                pass
        
        local_now = now.astimezone(target_tz)
        
        # Format for HTML inputs
        context['initial_deadline_date'] = local_now.strftime('%Y-%m-%d')
        context['initial_deadline_time'] = local_now.strftime('%H:%M')
        
        return context
