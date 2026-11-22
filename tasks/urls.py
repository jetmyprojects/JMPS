from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet, TaskFileViewSet, DashboardStatsView

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'task-files', TaskFileViewSet, basename='taskfile')

urlpatterns = [
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('', include(router.urls)),
]
