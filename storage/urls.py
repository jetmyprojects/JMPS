from django.urls import path
from .views import StorageUsageView, StorageLimitView

urlpatterns = [
    path('usage/', StorageUsageView.as_view(), name='storage-usage'),
    path('limit/', StorageLimitView.as_view(), name='storage-limit'),
]
