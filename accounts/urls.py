from django.urls import path
from .views import (
    SignupView, LoginView, ProfileView, SendOTPView, VerifyOTPView, 
    ForgotPasswordView, ResetPasswordView, LogoutView, CancelSignupView, 
    CheckOTPView, DeleteAccountView, InitiateEmailChangeView, 
    VerifyEmailChangeOTPView, ResendEmailChangeOTPView, CheckEmailView,
    ChangePasswordView, InitiateProfileUpdateView, VerifyProfileUpdateView, ResendProfileUpdateOTPView,
    CookieTokenRefreshView, SetTimezoneView, VerifyLoginOTPView
)
# from rest_framework_simplejwt.views import TokenRefreshView # Removed
from django.views.generic import TemplateView

urlpatterns = [
    path('auth/signup/', SignupView.as_view(), name='signup'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/verify-login-otp/', VerifyLoginOTPView.as_view(), name='login_verify_otp'),
    path('auth/token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('auth/check-email/', CheckEmailView.as_view(), name='check-email'),
    path('auth/check-otp/', CheckOTPView.as_view(), name='check-otp'),
    path('auth/forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('auth/reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('auth/cancel-signup/', CancelSignupView.as_view(), name='cancel_signup'),
    path('user/profile/', ProfileView.as_view(), name='profile'),
    path('user/delete/', DeleteAccountView.as_view(), name='delete_account'),
    path('email-change/initiate/', InitiateEmailChangeView.as_view(), name='initiate_email_change'),
    path('email-change/verify/', VerifyEmailChangeOTPView.as_view(), name='verify_email_change_otp'),
    path('email-change/resend/', ResendEmailChangeOTPView.as_view(), name='resend_email_change_otp'),
    path('profile/update/initiate/', InitiateProfileUpdateView.as_view(), name='initiate_profile_update'),
    path('profile/update/verify/', VerifyProfileUpdateView.as_view(), name='verify_profile_update_otp'),
    path('profile/update/resend/', ResendProfileUpdateOTPView.as_view(), name='resend_profile_update_otp'),
    path('user/set-timezone/', SetTimezoneView.as_view(), name='set_timezone'),
]
