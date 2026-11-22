from django.urls import path
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from .views import (
    contact_inquiries_list, contact_inquiry_detail, contact_inquiry_reply, admin_logout,
    admin_discount_codes, create_discount_code, update_discount_code, delete_discount_code, secure_admin_required
)
from .views import get_discount_usage

urlpatterns = [
    path('admin-login/', TemplateView.as_view(template_name='AdminLogin.html'), name='admin_login_page'),
    path('admin-dashboard/', secure_admin_required(TemplateView.as_view(template_name='AdminDashboard.html')), name='admin_dashboard'),
    path('admin-dashboard/users/', secure_admin_required(TemplateView.as_view(template_name='AdminUsers.html')), name='admin_users'),
    path('admin-dashboard/users/create/', secure_admin_required(TemplateView.as_view(template_name='AdminCreateUser.html')), name='admin_users_create'),
    path('admin-dashboard/tasks/', secure_admin_required(TemplateView.as_view(template_name='AdminTasks.html')), name='admin_tasks'),
    path('admin-dashboard/billing/', secure_admin_required(TemplateView.as_view(template_name='AdminBilling.html')), name='admin_billing'),
    path('admin-dashboard/inquiries/', contact_inquiries_list, name='admin_contact_inquiries'),
    path('admin-dashboard/inquiries/<int:inquiry_id>/', contact_inquiry_detail, name='admin_contact_inquiry_detail'),
    path('admin-dashboard/inquiries/<int:inquiry_id>/reply/', contact_inquiry_reply, name='admin_contact_inquiry_reply'),
    path('admin-dashboard/logout/', admin_logout, name='admin_logout'),
    path('admin-dashboard/discount-codes/', admin_discount_codes, name='admin_discount_codes'),
    path('admin-dashboard/discount-codes/create/', create_discount_code, name='create_discount_code'),
    path('admin-dashboard/discount-codes/<int:code_id>/update/', update_discount_code, name='update_discount_code'),
    path('admin-dashboard/discount-codes/<int:code_id>/delete/', delete_discount_code, name='delete_discount_code'),
    path('admin-dashboard/discount-codes/<int:code_id>/usage/', get_discount_usage, name='get_discount_usage'),
]
