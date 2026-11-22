from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.contrib.auth import login, logout
from django.shortcuts import redirect
from django.contrib.auth.hashers import make_password, check_password
from django.utils.dateparse import parse_datetime
import logging
import threading
from datetime import timedelta
from django.utils import timezone
from subscriptions.models import DiscountCode, UserSubscription, SubscriptionPlan, DiscountUsage, Invoice
from payments.services import sync_stripe_customer_address

from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer, UserProfileSerializer, 
    ForgotPasswordSerializer, ResetPasswordSerializer, LogoutSerializer, ChangePasswordSerializer
)
from .models import User

from .utils import send_html_otp_email, send_welcome_email, send_forgot_password_email, generate_otp, send_profile_update_email
from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView

logger = logging.getLogger(__name__)

class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
        if refresh_token:
            request.data['refresh'] = refresh_token
        
        remember_me = False
        try:
            if refresh_token:
                old_token = RefreshToken(refresh_token)
                if old_token.payload.get('remember_me'):
                    remember_me = True
        except Exception:
            pass

        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            access_token = response.data.get('access')
            if access_token:
                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE'], 
                    value=access_token,
                    expires=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'],
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )
            
            new_refresh_token_str = response.data.get('refresh')
            if new_refresh_token_str:
                refresh_expiry = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
                
                if remember_me:
                    try:
                        # Instantiate the new token to modify it
                        new_refresh = RefreshToken(new_refresh_token_str)
                        new_refresh['remember_me'] = True
                        
                        refresh_expiry = timedelta(days=30)
                        new_refresh.set_exp(lifetime=refresh_expiry)
                        
                        new_refresh_token_str = str(new_refresh)
                    except Exception as e:
                        logger.error(f"Error extending refresh token: {e}")

                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'],
                    value=new_refresh_token_str, # Use the potentially updated token string
                    expires=refresh_expiry,
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )
        return response

class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def perform_create(self, serializer):
        referral_code = serializer.validated_data.pop('referral_code', None)
        user = serializer.save()
        
        is_existing = getattr(user, '_is_existing_user', False)

        # Handle Referral Code - Only for NEW users
        if referral_code and not is_existing:
            try:
                discount = DiscountCode.objects.get(code=referral_code)
                if discount.is_valid():
                    if discount.is_trial or discount.discount_percent == 100:
                        # Auto-activate Trial Subscription
                        plan = SubscriptionPlan.objects.filter(name__icontains="Yearly").first()
                        if plan:
                            duration_days = discount.duration_months * 30
                            end_date = timezone.now().date() + timedelta(days=duration_days)
                            UserSubscription.objects.update_or_create(
                                user=user,
                                defaults={
                                    'plan': plan,
                                    'start_date': timezone.now().date(),
                                    'end_date': end_date,
                                    'is_active': True,
                                    'auto_renew': False,
                                    'stripe_payment_intent': f"SIGNUP-TRIAL-{discount.code}-{timezone.now().timestamp()}"
                                }
                            )
                            # Record Usage
                            discount.current_uses += 1
                            discount.save()
                            DiscountUsage.objects.create(user=user, discount_code=discount)
                            # Create Zero Invoice
                            Invoice.objects.create(
                                user=user,
                                stripe_id=f"TRIAL-SIGNUP-{discount.code}-{timezone.now().timestamp()}",
                                amount=0.00,
                                currency='usd',
                                status='trial_start',
                                expiry_date=end_date
                            )
                    else:
                        # STANDARD DISCOUNT (Start Free Trial or Recurring Discount)
                        # We save it to 'pending_discount_code' so it persists even if they close the checkout window
                        user.pending_discount_code = discount.code
                        user.save()

            except DiscountCode.DoesNotExist:
                pass # Invalid codes on signup are ignored or handled by frontend validation
            except Exception as e:
                logger.error(f"Error applying referral code on signup: {e}")
        else:
             # Ensure no lingering code exists if user didn't provide one
             if user.pending_discount_code:
                 user.pending_discount_code = None
                 user.save()

        # Generate and Save OTP
        otp = generate_otp()
        user.otp = make_password(otp)
        user.otp_attempts = 0 # Reset attempts
        user.otp_expiry = timezone.now() + timedelta(minutes=10)
        user.save()
        self.otp = otp  # Keep plain OTP for email sending
        self.user = user

    def create(self, request, *args, **kwargs):
        try:
            response = super().create(request, *args, **kwargs)
            
            # Send OTP via Email
            otp = getattr(self, 'otp', None)
            user = getattr(self, 'user', None)
            
            if otp and user:
                try:
                    # Use user.first_name directly to ensure it matches what was saved
                    email_thread = threading.Thread(
                        target=send_html_otp_email, 
                        args=(user.email, otp, user.first_name)
                    )
                    email_thread.run()  # synchronous: serverless freezes background threads
                except Exception as e:
                    import sys
                    print(f"CRITICAL ERROR Sending Email in View: {e}", file=sys.stderr)
                    logger.error(f"Error sending email: {e}")

            response.data['message'] = "User created. OTP sent to email."
            return response
        except Exception as e:
            import sys
            import traceback
            print("CRITICAL SIGNUP ERROR:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # 1. Check if email exists in DB
        exists = User.objects.filter(email__iexact=email).exists()
        if exists:
            return Response({'exists': True}, status=status.HTTP_200_OK)

        # 2. Check MX Records to verify domain validity
        try:
            import dns.resolver
            domain = email.split('@')[1]
            
            # Configure resolver to be robust
            resolver = dns.resolver.Resolver()
            resolver.lifetime = 3.0 # Timeout in seconds
            resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1'] # Use Google/Cloudflare to bypass ISP wildcards

            try:
                # Resolve MX records
                records = resolver.resolve(domain, 'MX')
                if not records:
                    raise Exception("No MX records found")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                 return Response({'error': 'Invalid email domain. No mail server found.'}, status=status.HTTP_400_BAD_REQUEST)
            except dns.exception.Timeout:
                 return Response({'error': 'Email domain validation timed out. Please try again or use a different email.'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                # Fallback for other DNS errors
                # logger.warning(f"DNS MX check failed for {domain}: {e}")
                pass # Fail open or closed? Let's stay consistent with config/views cleanup:
                # Actually, in config/views we failed CLOSED for generic errors.
                # Here we had 'pass' (Fail OPEN).
                # User complaint implies Fail OPEN is bad.
                # Let's switch to Fail CLOSED here too.
                return Response({'error': f'Invalid email domain ({str(e)}).'}, status=status.HTTP_400_BAD_REQUEST)

        except ImportError:
            logger.warning("dnspython not installed, skipping MX check")
            # If we enforce it in config/views, we should enforce it here too?
            # User said "i write wrong email still email send".
            # Probably better to return error if lib missing.
            return Response({'error': 'Server configuration error (missing DNS lib).'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except IndexError:
             return Response({'error': 'Invalid email format'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'exists': False}, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data)
            if serializer.is_valid():
                user = serializer.validated_data
                
                # --- TRUSTED DEVICE LOGIC ---
                # Check if this device is trusted (via signed cookie)
                is_trusted = False
                trust_token = request.COOKIES.get('device_trust_token')
                
                if trust_token:
                    try:
                        # Verify the signature and ownership
                        # We store "user_id:timestamp" signed
                        from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
                        signer = TimestampSigner()
                        # Max age 30 days = 2592000 seconds
                        value = signer.unsign(trust_token, max_age=2592000) 
                        trusted_user_id = value.split(':')[0]
                        if str(trusted_user_id) == str(user.id):
                            is_trusted = True
                    except (BadSignature, SignatureExpired):
                        is_trusted = False
                
                # Check "Remember Me" checkbox from request
                remember_me = request.data.get('remember_me', False)

                # If NOT trusted, we require OTP
                if not is_trusted:
                    # Generate OTP
                    from datetime import timedelta
                    
                    otp = generate_otp()
                    
                    # Store state in session (Login Pending)
                    request.session['pending_login_user_id'] = user.id
                    request.session['login_otp_hash'] = make_password(otp)
                    request.session['login_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()
                    request.session['pending_remember_me'] = remember_me # Store preference
                    
                    # Send OTP via Email (Async)
                    try:
                        email_thread = threading.Thread(
                            target=send_html_otp_email, 
                            args=(user.email, otp, user.first_name)
                        )
                        email_thread.run()  # synchronous: serverless freezes background threads
                    except Exception as e:
                        logger.error(f"Error sending email: {e}")
                        return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                    return Response({
                        'requires_otp': True,
                        'message': 'New device detected. OTP sent to your email.'
                    }, status=status.HTTP_200_OK)

                # --- IF TRUSTED: PROCEED TO LOGIN DIRECTLY ---
                refresh = RefreshToken.for_user(user)
                
                # Create Django Session for Admin Panel access
                login(request, user)
                
                response = Response({
                    'user': UserProfileSerializer(user).data
                }, status=status.HTTP_200_OK)

                # Standard Token Issuance
                access_expiry = settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
                refresh_expiry = settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']

                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE'], 
                    value=str(refresh.access_token),
                    expires=access_expiry,
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )
                
                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'], 
                    value=str(refresh),
                    expires=refresh_expiry,
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )

                # Refresh the trust token logic
                if remember_me:
                     from django.core.signing import TimestampSigner
                     signer = TimestampSigner()
                     value = f"{user.id}:{timezone.now().timestamp()}"
                     signed_token = signer.sign(value)
                     # Set Trust Cookie
                     response.set_cookie(
                        key='device_trust_token',
                        value=signed_token,
                        max_age=2592000, # 30 Days
                        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                        httponly=True, 
                        samesite='Lax' 
                     )

                return response
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': f"Login Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyLoginOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        otp = request.data.get('otp')
        
        user_id = request.session.get('pending_login_user_id')
        otp_hash = request.session.get('login_otp_hash')
        expiry_str = request.session.get('login_otp_expiry')
        remember_me = request.session.get('pending_remember_me')

        if not user_id or not otp_hash:
             return Response({'error': 'Session expired. Please sign in again.'}, status=status.HTTP_400_BAD_REQUEST)

        if not otp:
            return Response({'error': 'OTP is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        try:
             expiry = parse_datetime(expiry_str)
        except Exception:
            return Response({'error': 'Invalid session data'}, status=status.HTTP_400_BAD_REQUEST)
        
        if expiry and expiry > timezone.now():
            if check_password(otp, otp_hash):
                # Valid OTP
                try:
                    user = User.objects.get(id=user_id)
                except User.DoesNotExist:
                     return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

                # --- LOGIN SUCCESS ---
                
                # Cleanup Session
                del request.session['pending_login_user_id']
                del request.session['login_otp_hash']
                del request.session['login_otp_expiry']
                if 'pending_remember_me' in request.session:
                    del request.session['pending_remember_me']
                
                # Perform Login
                # Must set backend before login() when using manual user object
                user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, user)
                refresh = RefreshToken.for_user(user)

                response = Response({
                    'user': UserProfileSerializer(user).data,
                    'message': 'Login successful.'
                }, status=status.HTTP_200_OK)

                # Set Auth Cookies
                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE'], 
                    value=str(refresh.access_token),
                    expires=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'],
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )
                response.set_cookie(
                    key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'], 
                    value=str(refresh),
                    expires=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'],
                    secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                    httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                    samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                )

                # --- SET TRUST TOKEN IF REQUESTED ---
                if remember_me:
                     from django.core.signing import TimestampSigner
                     signer = TimestampSigner()
                     value = f"{user.id}:{timezone.now().timestamp()}"
                     signed_token = signer.sign(value)
                     
                     response.set_cookie(
                        key='device_trust_token',
                        value=signed_token,
                        max_age=2592000, # 30 Days
                        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                        httponly=True,
                        samesite='Lax' 
                     )

                return response
            else:
                 return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'error': 'OTP Expired'}, status=status.HTTP_400_BAD_REQUEST)

class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

class SendOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
            # Generate 6 digit OTP
            otp = generate_otp()
            user.otp = make_password(otp) # Hash OTP
            user.otp_attempts = 0 # Reset attempts
            # Set expiry to 10 mins from now
            from django.utils import timezone
            from datetime import timedelta
            user.otp_expiry = timezone.now() + timedelta(minutes=10)
            user.save()
            # Send OTP via Email (Async)
            try:
                email_thread = threading.Thread(
                    target=send_html_otp_email, 
                    args=(email, otp, user.first_name)
                )
                email_thread.run()  # synchronous: serverless freezes background threads
            except Exception as e:
                logger.error(f"Error initiating email thread: {e}")
                return Response({'error': 'Failed to initiate email sending'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({'message': 'OTP sent successfully'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')
        if not email or not otp:
            return Response({'error': 'Email and OTP are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
            
            # Rate Limiting
            if user.otp_attempts >= 5:
                return Response({'error': 'Too many failed attempts. Please request a new OTP.'}, status=status.HTTP_403_FORBIDDEN)

            from django.utils import timezone

            if user.otp_expiry and user.otp_expiry > timezone.now():
                if check_password(otp, user.otp):
                    # Valid OTP
                    user.otp = None # Clear OTP after success
                    user.otp_expiry = None
                    user.otp_attempts = 0
                    
                    # Check if first time verification
                    is_first_verification = not user.is_email_verified
                    
                    user.is_email_verified = True
                    user.save()
                    
                    # Send Welcome Email only on first verification
                    if is_first_verification:
                        try:
                            send_welcome_email(user.email, user.first_name)
                        except Exception as e:
                            logger.error(f"Error sending welcome email: {e}")

                    refresh = RefreshToken.for_user(user)
                    
                    # Create Django Session for Admin Panel access
                    if request.user.is_anonymous:
                         user.backend = 'django.contrib.auth.backends.ModelBackend'
                         login(request, user)

                    response = Response({
                        'user': UserProfileSerializer(user).data,
                        'message': 'OTP verified successfully. Login successful.',
                        'access': str(refresh.access_token),
                        'refresh': str(refresh)
                    }, status=status.HTTP_200_OK)

                    response.set_cookie(
                        key=settings.SIMPLE_JWT['AUTH_COOKIE'], 
                        value=str(refresh.access_token),
                        expires=settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'],
                        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                        samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                    )
                    response.set_cookie(
                        key=settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'], 
                        value=str(refresh),
                        expires=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'],
                        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                        httponly=settings.SIMPLE_JWT['AUTH_COOKIE_HTTP_ONLY'],
                        samesite=settings.SIMPLE_JWT['AUTH_COOKIE_SAMESITE']
                    )

                    # TRUSTED DEVICE: Automatically trust the device used for Signup/Verification
                    from django.core.signing import TimestampSigner
                    signer = TimestampSigner()
                    value = f"{user.id}:{timezone.now().timestamp()}"
                    signed_token = signer.sign(value)
                    
                    response.set_cookie(
                        key='device_trust_token',
                        value=signed_token,
                        max_age=2592000, # 30 Days
                        secure=settings.SIMPLE_JWT['AUTH_COOKIE_SECURE'],
                        httponly=True,
                        samesite='Lax' 
                    )

                    return response
                else:
                    # Invalid OTP
                    user.otp_attempts += 1
                    user.save()
                    return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                 return Response({'error': 'OTP Expired'}, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class CheckOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')
        if not email or not otp:
            return Response({'error': 'Email and OTP are required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
            
            # Rate Limiting
            if user.otp_attempts >= 5:
                 return Response({'error': 'Too many failed attempts. Please request a new OTP.'}, status=status.HTTP_403_FORBIDDEN)

            from django.utils import timezone
            
            if user.otp_expiry and user.otp_expiry > timezone.now():
                if check_password(otp, user.otp):
                    # Valid OTP, do NOT clear it yet (it's needed for reset)
                    # We also don't reset attempts here until final consumption, or maybe we should? 
                    # Let's NOT reset attempts here to prevent probing.
                    return Response({'message': 'OTP is valid.'}, status=status.HTTP_200_OK)
                else:
                    user.otp_attempts += 1
                    user.save()
                    return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({'error': 'OTP Expired'}, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email__iexact=email)
                import random
                from django.utils import timezone
                from datetime import timedelta
                
                otp = generate_otp()
                user.otp = make_password(otp)
                user.otp_attempts = 0 # Reset
                user.otp_expiry = timezone.now() + timedelta(minutes=10)
                user.save()
                # Send OTP via Email (Async)
                try:
                    email_thread = threading.Thread(
                        target=send_forgot_password_email,
                        args=(email, otp, user.first_name)
                    )
                    email_thread.run()  # synchronous: serverless freezes background threads
                except Exception as e:
                    logger.error(f"Error sending email: {e}")
                    return Response({'error': 'Failed to send email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

                return Response({'message': 'OTP sent to email'}, status=status.HTTP_200_OK)
            except User.DoesNotExist:
                 return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            otp = serializer.validated_data['otp']
            new_password = serializer.validated_data['new_password']
            try:
                user = User.objects.get(email__iexact=email)
                
                if user.otp_attempts >= 5:
                    return Response({'error': 'Too many failed attempts. Please request a new OTP.'}, status=status.HTTP_403_FORBIDDEN)

                from django.utils import timezone
                if user.otp_expiry and user.otp_expiry > timezone.now():
                    if check_password(otp, user.otp):
                        user.set_password(new_password)
                        user.otp = None
                        user.otp_expiry = None
                        user.otp_attempts = 0
                        user.save()
                        return Response({'message': 'Password reset successfully'}, status=status.HTTP_200_OK)
                    else:
                        user.otp_attempts += 1
                        user.save()
                        return Response({'error': 'Invalid OTP'}, status=status.HTTP_400_BAD_REQUEST)
                return Response({'error': 'OTP Expired'}, status=status.HTTP_400_BAD_REQUEST)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # refresh_token = serializer.validated_data["refresh"] # Not needed from body if in cookie
                refresh_token = request.COOKIES.get(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
                if refresh_token:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                
                # Logout from Django Session as well
                logout(request)
                
                response = Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)
                response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
                response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
                return response
            except TokenError:
                 # Even if token error, we should clear cookies
                response = Response({'message': 'Logged out (invalid token)'}, status=status.HTTP_200_OK)
                response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE'])
                response.delete_cookie(settings.SIMPLE_JWT['AUTH_COOKIE_REFRESH'])
                return response
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CancelSignupView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email__iexact=email)
            if not user.is_email_verified:
                user.delete()
                # logger.debug(f"Deleted unverified user: {email}")
                return Response({'message': 'Signup cancelled. User deleted.'}, status=status.HTTP_200_OK)
            return Response({'error': 'User is already verified'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'message': 'User already deleted or does not exist'}, status=status.HTTP_200_OK)

class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        try:
            user = request.user
            
            # Check for active subscription
            active_sub = UserSubscription.objects.filter(user=user, is_active=True).first()
            if active_sub:
                return Response(
                    {'error': 'Please cancel your active subscription before deleting your account.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.delete()
            response = Response({'message': 'Account deleted successfully'}, status=status.HTTP_200_OK)
            response.delete_cookie('access_token')
            response.delete_cookie('refresh_token')
            return response
        except Exception as e:
            logger.error(f"Error deleting account for user {request.user.email}: {str(e)}")
            return Response({'error': f"Failed to delete account: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

class InitiateEmailChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_email = request.data.get('new_email')
        if not new_email:
            return Response({'error': 'New email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if email is already taken
        if User.objects.filter(email__iexact=new_email).exists():
            return Response({'error': 'Email is already in use.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        
        # Generate OTP
        from django.utils import timezone
        from datetime import timedelta
        otp = generate_otp()
        
        request.session['pending_new_email'] = new_email
        # Store HASHED OTP in session
        request.session['email_change_otp_hash'] = make_password(otp)
        request.session['email_change_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        
        # We do NOT save to user model
        # user.otp = otp 
        # user.save() 

        # Send OTP via Email to the NEW address (Async)
        try:
            email_thread = threading.Thread(
                target=send_html_otp_email, 
                args=(new_email, otp, user.first_name)
            )
            email_thread.run()  # synchronous: serverless freezes background threads
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'OTP sent to new email'}, status=status.HTTP_200_OK)

class VerifyEmailChangeOTPView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        otp = request.data.get('otp')
        new_email = request.session.get('pending_new_email')
        otp_hash = request.session.get('email_change_otp_hash')
        expiry_str = request.session.get('email_change_otp_expiry')
        
        if not new_email or not otp_hash:
             return Response({'error': 'Session expired or invalid request. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)

        if not otp:
            return Response({'error': 'OTP is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone
        from datetime import datetime
        
        try:
            expiry = parse_datetime(expiry_str)
        except Exception:
             return Response({'error': 'Invalid session data.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if expiry and expiry > timezone.now():
            if check_password(otp, otp_hash):
                user = request.user
                user.email = new_email
                user.username = new_email # Assuming username is email
                user.save()
                
                # Clear session
                del request.session['pending_new_email']
                del request.session['email_change_otp_hash']
                del request.session['email_change_otp_expiry']
                
                return Response({'message': 'Email updated successfully'}, status=status.HTTP_200_OK)
        
        return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)


class ResendEmailChangeOTPView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_email = request.session.get('pending_new_email')
        if not new_email:
            return Response({'error': 'No pending email change found. Please restart the process.'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        from django.utils import timezone
        from datetime import timedelta
        
        otp = generate_otp()
        
        # Update session
        request.session['email_change_otp_hash'] = make_password(otp)
        request.session['email_change_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        
        # Send OTP (Async)
        try:
            email_thread = threading.Thread(
                target=send_html_otp_email, 
                args=(new_email, otp, user.first_name)
            )
            email_thread.run()  # synchronous: serverless freezes background threads
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'OTP resent successfully'}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if user.check_password(serializer.validated_data['old_password']):
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
            return Response({'error': 'Incorrect old password.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class InitiateProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        
        # Check for active subscription
        is_premium = False
        if user.is_staff or user.is_superuser:
             is_premium = True
        else:
            try:
                subscription = user.subscription
                from django.utils import timezone
                if subscription.is_active and subscription.end_date >= timezone.now().date():
                    is_premium = True
            except:
                pass
        
        if not is_premium:
             return Response({'error': 'You must have an active subscription to edit your profile.'}, status=status.HTTP_403_FORBIDDEN)

        # Deserialize data
        serializer = UserProfileSerializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            # Generate OTP
            from django.utils import timezone
            from datetime import timedelta
            otp = generate_otp()
            
            # Store pending data and OTP in session
            request.session['pending_profile_update'] = serializer.validated_data
            request.session['profile_update_otp_hash'] = make_password(otp)
            request.session['profile_update_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()
            
            # Send OTP via Email to the user's CURRENT email (Async)
            try:
                email_thread = threading.Thread(
                    target=send_profile_update_email,
                    args=(user.email, otp, user.first_name)
                )
                email_thread.run()  # synchronous: serverless freezes background threads
            except Exception as e:
                logger.error(f"Error sending email: {e}")
                return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({'message': 'OTP sent to email'}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            otp = request.data.get('otp')
            pending_data = request.session.get('pending_profile_update')
            otp_hash = request.session.get('profile_update_otp_hash')
            expiry_str = request.session.get('profile_update_otp_expiry')
            
            if not pending_data or not otp_hash:
                 return Response({'error': 'Session expired or invalid request. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)

            if not otp:
                return Response({'error': 'OTP is required'}, status=status.HTTP_400_BAD_REQUEST)

            from django.utils import timezone
            
            try:
                 expiry = parse_datetime(expiry_str)
            except Exception:
                return Response({'error': 'Invalid session data'}, status=status.HTTP_400_BAD_REQUEST)
            
            if expiry and expiry > timezone.now():
                if check_password(otp, otp_hash):
                    user = request.user
                    
                    # Apply changes
                    for key, value in pending_data.items():
                        if hasattr(user, key):
                            setattr(user, key, value)
                    
                    user.save()
                    
                    # Sync Address to Stripe (Async ideally, but sync for now)
                    try:
                        sync_stripe_customer_address(user)
                    except Exception as e:
                        logger.error(f"Failed to sync Stripe address: {e}")
                    
                    # Clear session
                    if 'pending_profile_update' in request.session: del request.session['pending_profile_update']
                    if 'profile_update_otp_hash' in request.session: del request.session['profile_update_otp_hash']
                    if 'profile_update_otp_expiry' in request.session: del request.session['profile_update_otp_expiry']
                    
                    return Response({'message': 'Profile updated successfully'}, status=status.HTTP_200_OK)
            
            return Response({'error': 'Invalid or expired OTP'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response({'error': f"Internal Server Error: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ResendProfileUpdateOTPView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        pending_data = request.session.get('pending_profile_update')
        if not pending_data:
            return Response({'error': 'No pending profile update found. Please restart the process.'}, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        from django.utils import timezone
        from datetime import timedelta
        
        otp = generate_otp()
        
        # Update session
        request.session['profile_update_otp_hash'] = make_password(otp)
        request.session['profile_update_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()
        
        # Send OTP (Async)
        try:
            email_thread = threading.Thread(
                target=send_profile_update_email,
                args=(user.email, otp, user.first_name)
            )
            email_thread.run()  # synchronous: serverless freezes background threads
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return Response({'error': 'Failed to send verification email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'OTP resent successfully'}, status=status.HTTP_200_OK)


def instant_logout(request):
    logout(request)
    response = redirect('index')
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')
    return response

class SetTimezoneView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tz_name = request.data.get('timezone')
        if not tz_name:
            return Response({'error': 'Timezone is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            import pytz
            # Validate timezone
            pytz.timezone(tz_name)
            
            user = request.user
            # Only update if changed to avoid unnecessary writes
            if user.timezone != tz_name:
                user.timezone = tz_name
                user.save(update_fields=['timezone'])
            
            return Response({'message': 'Timezone updated'}, status=status.HTTP_200_OK)
        except pytz.UnknownTimeZoneError:
             return Response({'error': 'Invalid timezone'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def login_page_view(request):
    from django.shortcuts import render
    context = {}
    if 'device_trust_token' in request.COOKIES:
        context['remember_me_checked'] = True
    return render(request, 'SignIn.html', context)
