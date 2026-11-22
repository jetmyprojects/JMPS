from django.urls import path
from .views import (
    PlanListView,
    CurrentPlanView,
    SubscribeView,
    RenewView,
    CancelSubscriptionView,
    UpdateCardView,
    ActivateSubscriptionView,
    InvoiceListView,
    InvoiceDownloadView
)

urlpatterns = [
    # Plans
    path('plans/', PlanListView.as_view(), name='plan-list'),
    
    # Billing / Subscription management
    path('plan/', CurrentPlanView.as_view(), name='current-plan'),
    path('invoices/', InvoiceListView.as_view(), name='invoice-list'),
    path('subscribe/', SubscribeView.as_view(), name='subscribe'),
    path('renew/', RenewView.as_view(), name='renew'),
    path('cancel/', CancelSubscriptionView.as_view(), name='cancel'),
    path('update-card/', UpdateCardView.as_view(), name='update-card'),
    path('debug-activate/', ActivateSubscriptionView.as_view(), name='debug-activate'),
    path('invoices/<int:pk>/download/', InvoiceDownloadView.as_view(), name='invoice-download'),
]
