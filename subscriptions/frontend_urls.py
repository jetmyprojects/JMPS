from django.urls import path
from django.views.generic import TemplateView


urlpatterns = [
    path('dashboard/usage/', TemplateView.as_view(template_name='SpaceUsed.html'), name='space_used'),

    # Billing & Payments
    path('dashboard/billing/history/', TemplateView.as_view(template_name='Dashboard_PaymentHistory.html'), name='payment_history'),
    path('dashboard/billing/cancel/', TemplateView.as_view(template_name='Dashboard_PaymentCancelSubscription.html'), name='payment_cancel'),
    path('dashboard/billing/cancel/confirm/', TemplateView.as_view(template_name='Dashboard_PaymentCancelConfirm.html'), name='payment_cancel_confirm'),

    # Payment Edit
    path('dashboard/billing/edit/', TemplateView.as_view(template_name='Dashboard_PaymentEditInfo.html'), name='payment_edit'),
]
