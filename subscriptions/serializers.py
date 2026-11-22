from rest_framework import serializers
from .models import SubscriptionPlan, UserSubscription
from datetime import timedelta
from django.utils import timezone

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'

class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    days_left = serializers.SerializerMethodField()
    is_trial = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = ['id', 'plan', 'plan_details', 'start_date', 'end_date', 'is_active', 'auto_renew', 'days_left', 'is_trial']

    def get_days_left(self, obj):
        if not obj.is_active:
            return 0
        today = timezone.now().date()
        if obj.end_date < today:
            return 0
        return (obj.end_date - today).days

    def get_is_trial(self, obj):
        return bool(obj.stripe_payment_intent and 'TRIAL' in obj.stripe_payment_intent)

class SubscribeSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(required=True)

class UpdateCardSerializer(serializers.Serializer):
    payment_method_id = serializers.CharField(required=True)

class InvoiceSerializer(serializers.ModelSerializer):
    invoice_pdf = serializers.SerializerMethodField()

    class Meta:
        from .models import Invoice
        model = Invoice
        fields = ['id', 'stripe_id', 'amount', 'currency', 'status', 'expiry_date', 'invoice_pdf', 'created_at']

    def get_invoice_pdf(self, obj):
        if obj.invoice_pdf:
            return obj.invoice_pdf
        # Fallback to local view
        from django.urls import reverse
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(reverse('invoice-download', args=[obj.id]))
        return f"/api/v1/billing/invoices/{obj.id}/download/"
