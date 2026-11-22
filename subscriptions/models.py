from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(default=30)
    features = models.TextField(help_text="JSON or comma-separated list of features")
    storage_limit_mb = models.IntegerField(default=1024, help_text="Storage limit in MB")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ${self.price}"

class UserSubscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=True)
    stripe_payment_intent = models.CharField(max_length=255, blank=True, null=True, unique=True, help_text="Stripe Payment Intent ID for idempotency")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan.name if self.plan else 'No Plan'}"

    def save(self, *args, **kwargs):
        if not self.end_date and self.plan:
            self.end_date = self.start_date + timedelta(days=self.plan.duration_days)

        super().save(*args, **kwargs)

class Invoice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invoices')
    stripe_id = models.CharField(max_length=255, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='usd')
    status = models.CharField(max_length=50)
    expiry_date = models.DateField(null=True, blank=True)
    invoice_pdf = models.URLField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.stripe_id} - {self.status}"


class DiscountCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percent = models.IntegerField(default=0, help_text="Percentage discount (0-100)")
    is_trial = models.BooleanField(default=False, help_text="If True, provides free access for duration_months without payment")
    duration_months = models.IntegerField(default=1, help_text="Duration of the discount or trial in months")
    valid_from = models.DateField(default=timezone.now, help_text="Code valid starting from this date")
    valid_until = models.DateField(null=True, blank=True, help_text="Code valid until this date")
    max_uses = models.IntegerField(default=100)
    current_uses = models.IntegerField(default=0)

    def is_valid(self):
        now = timezone.now().date()
        if self.valid_from > now: return False
        if self.valid_until and self.valid_until < now: return False
        if self.current_uses >= self.max_uses: return False
        return True

    def __str__(self):
        return f"{self.code} - {self.discount_percent}% (Trial: {self.is_trial})"

class DiscountUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discount_uses')
    discount_code = models.ForeignKey(DiscountCode, on_delete=models.CASCADE, related_name='uses')
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']

    def __str__(self):
        return f"{self.user.email} used {self.discount_code.code} on {self.used_at}"
