from django.urls import path
from .views import (
    AdminUserListView, AdminSendOTPView, AdminCreateUserView, AdminUpdateUserView, 
    AdminBlockUserView, AdminUnblockUserView, AdminDeleteUserView, AdminTaskList, 
    AdminResetPasswordView, AdminUserDetailView, AdminBillingView, AdminStatsView, 
    DeleteTaskView, AdminLoginView
)

urlpatterns = [
    path('users/', AdminUserListView.as_view(), name='admin-users-list'),
    path('user/create/', AdminCreateUserView.as_view(), name='admin-user-create'),
    path('user/send-otp/', AdminSendOTPView.as_view(), name='admin-send-otp'),
    path('user/<int:pk>/details/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('user/<int:id>/update/', AdminUpdateUserView.as_view(), name='admin-user-update'),
    path('user/<int:id>/block/', AdminBlockUserView.as_view(), name='admin-user-block'),
    path('user/<int:id>/unblock/', AdminUnblockUserView.as_view(), name='admin-user-unblock'),
    path('user/<int:id>/delete/', AdminDeleteUserView.as_view(), name='admin-user-delete'),
    path('user/<int:id>/reset-password/', AdminResetPasswordView.as_view(), name='admin-user-reset-password'),
    path('tasks/', AdminTaskList.as_view(), name='admin-tasks-list'),
    path('task/<int:id>/delete/', DeleteTaskView.as_view(), name='admin-task-delete'),
    path('billing/', AdminBillingView.as_view(), name='admin-billing'),
    path('stats/', AdminStatsView.as_view(), name='admin-stats'),
    path('auth/login/', AdminLoginView.as_view(), name='admin-login'),
]
