from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription, Invoice, DiscountCode, DiscountUsage

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration_days', 'storage_limit_mb')
    search_fields = ('name',)

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_date', 'end_date', 'is_active', 'auto_renew')
    list_filter = ('is_active', 'auto_renew', 'plan')
    search_fields = ('user__email', 'stripe_payment_intent')
    date_hierarchy = 'start_date'

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('stripe_id', 'user', 'amount', 'status', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('stripe_id', 'user__email')
    date_hierarchy = 'created_at'

@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'is_trial', 'valid_until', 'current_uses', 'max_uses')
    list_filter = ('is_trial',)
    search_fields = ('code',)

@admin.register(DiscountUsage)
class DiscountUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'discount_code', 'used_at')
    search_fields = ('user__email', 'discount_code__code')
    date_hierarchy = 'used_at'
