from django.urls import path
from django.views.generic import TemplateView
from .views import instant_logout, login_page_view
from django.views.decorators.cache import never_cache
from payments.views import PaymentSuccessView

urlpatterns = [
    path('dashboard/logout/', instant_logout, name='fe_logout'),
    path('signup/', TemplateView.as_view(template_name='SignUp.html'), name='fe_signup'),
    path('signup/otp/', TemplateView.as_view(template_name='SignUpPasscode.html'), name='fe_signup_otp'),
    path('signup/profile/', TemplateView.as_view(template_name='SignUpUserInfo.html'), name='fe_signup_profile'),
    path('login/', login_page_view, name='fe_login'),
    path('forgot-password/', TemplateView.as_view(template_name='ForgotPassword_Email.html'), name='fe_forgot_password'),
    path('forgot-password/otp/', TemplateView.as_view(template_name='ForgotPassword_Passcode.html'), name='fe_forgot_password_otp'),
    path('forgot-password/new/', TemplateView.as_view(template_name='ForgotPassword_NewPassword.html'), name='fe_forgot_password_new'),
    path('forgot-password/done/', TemplateView.as_view(template_name='ForgotPassword_Confirmation.html'), name='fe_forgot_password_done'),
    path('dashboard/profile/', never_cache(TemplateView.as_view(template_name='Profile.html')), name='fe_profile'),
    path('dashboard/profile/edit/', TemplateView.as_view(template_name='ProfileEdit.html'), name='fe_profile_edit'),
    path('projects/tasks/calendar/', TemplateView.as_view(template_name='Calendar.html'), name='fe_calendar'),
    path('dashboard/profile/verify-email/', TemplateView.as_view(template_name='Dashboard_ProfilePasscode.html'), name='fe_profile_verify_email'),
    path('dashboard/profile/verify-update/', TemplateView.as_view(template_name='Dashboard_ProfileUpdatePasscode.html'), name='fe_profile_verify_update'),
    # path('dashboard/usage/', TemplateView.as_view(template_name='Usage.html'), name='space_used'),
    path('dashboard/sign-out/', TemplateView.as_view(template_name='SignOutConfirm.html'), name='fe_signout_confirm'),
    path('accounts/access-expired/', TemplateView.as_view(template_name='FreeAccessExpired.html'), name='fe_access_expired'),
    path('welcome/', PaymentSuccessView.as_view(), name='welcome'),
]
