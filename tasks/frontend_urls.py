from django.urls import path
from django.views.generic import TemplateView
from .frontend_views import DashboardView, NewTaskView
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('projects/tasks/new/', NewTaskView.as_view(), name='task-create'),
    path('projects/tasks/active/', never_cache(login_required(TemplateView.as_view(template_name='Tasks.html'))), name='task-list-active'),
    path('projects/tasks/draft/', never_cache(login_required(TemplateView.as_view(template_name='Tasks.html'))), name='task-list-draft'),
    path('projects/tasks/completed/', never_cache(login_required(TemplateView.as_view(template_name='Tasks.html'))), name='task-list-completed'),
    path('projects/tasks/deleted/', never_cache(login_required(TemplateView.as_view(template_name='Tasks.html'))), name='task-list-deleted'),
    path('projects/tasks/uncompleted/', never_cache(login_required(TemplateView.as_view(template_name='Tasks.html'))), name='task-list-uncompleted'),
    path('projects/tasks/<int:pk>/', never_cache(login_required(TemplateView.as_view(template_name='TaskDetails.html'))), name='task-detail'),
    path('projects/tasks/<int:pk>/edit/', never_cache(login_required(TemplateView.as_view(template_name='EditTask.html'))), name='task-edit'),
    path('projects/tasks/calendar/', never_cache(login_required(TemplateView.as_view(template_name='Calendar.html'))), name='task-calendar'),
]
