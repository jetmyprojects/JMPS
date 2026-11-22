from django.urls import path
from .views import CreateCheckoutSessionView, WebhookView, ValidateDiscountCodeView

urlpatterns = [
    path('create-session/', CreateCheckoutSessionView.as_view(), name='create-session'),
    path('webhook/', WebhookView.as_view(), name='webhook'),
    path('validate-discount/', ValidateDiscountCodeView.as_view(), name='validate-discount'),
]
