from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from rest_framework import status
from django.contrib.auth import get_user_model
from tasks.models import Task
from subscriptions.models import UserSubscription, DiscountCode, DiscountUsage

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from .models import ContactInquiry

def is_admin(user):
    return user.is_authenticated and user.is_staff

from rest_framework.permissions import BasePermission

class IsSecureAdminUser(BasePermission):
    """
    Allows access only to admin users who have logged in via the Admin Panel
    (verified via 'admin_access' claim in JWT or session flag).
    """
    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            return False
        
        # Check JWT Claim
        if request.auth and hasattr(request.auth, 'get'):
            if request.auth.get('admin_access'):
                return True
        
        # Check Session (for non-API views or if JWT claim missing but session exists)
        if request.session.get('is_admin_login'):
             return True
             
        return False

from functools import wraps

def secure_admin_required(view_func):
    """
    Decorator for views that checks that the user is logged in via admin panel.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # 1. Check if user is authenticated
        if not request.user.is_authenticated:
             return redirect('admin_login_page')
             
        # 2. Check if user is staff and has admin session flag
        if request.user.is_staff and request.session.get('is_admin_login'):
            return view_func(request, *args, **kwargs)
            
        # 3. Invalid admin session - logout and redirect
        from django.contrib.auth import logout
        logout(request) 
        return redirect('admin_login_page')
    return _wrapped_view

from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, login

class AdminLoginView(APIView):
    permission_classes = [] # Allow Any

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None and user.is_staff:
            # Generate JWT with custom claim
            refresh = RefreshToken.for_user(user)
            refresh['admin_access'] = True # Add claim to refresh token
            
            access = refresh.access_token
            access['admin_access'] = True # Add claim to access token
            
            # Login to Session logic for template views
            login(request, user)
            request.session['is_admin_login'] = True
            
            return Response({
                'refresh': str(refresh),
                'access': str(access),
                'user_email': user.email
            }, status=status.HTTP_200_OK)
            
        return Response({'error': 'Invalid credentials or not an admin.'}, status=status.HTTP_401_UNAUTHORIZED)




@secure_admin_required
def contact_inquiries_list(request):
    inquiries_list = ContactInquiry.objects.all().order_by('-created_at')
    
    from django.core.paginator import Paginator
    paginator = Paginator(inquiries_list, 10) # 10 per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'AdminContactInquiries.html', {'inquiries': page_obj})

@secure_admin_required
def contact_inquiry_detail(request, inquiry_id):
    inquiry = get_object_or_404(ContactInquiry, id=inquiry_id)
    return render(request, 'AdminContactInquiryDetail.html', {'inquiry': inquiry})

@secure_admin_required
def contact_inquiry_reply(request, inquiry_id):
    if request.method == 'POST':
        inquiry = get_object_or_404(ContactInquiry, id=inquiry_id)
        reply_message = request.POST.get('message')
        
        if reply_message:
            context = {
                'first_name': inquiry.first_name,
                'last_name': inquiry.last_name,
                'email': inquiry.email,
                'phone': inquiry.phone,
                'company': inquiry.company,
                'team_size': inquiry.team_size,
                'country': inquiry.country,
                'industry': inquiry.industry,
                'reply_message': reply_message,
                'original_message': inquiry.message,
            }
            
            # Prepare Logo URL
            domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
            context['logo_url'] = f"{domain}/static/ImageLogox.png"
            
            html_content = render_to_string('emails/EmailContactUs.html', context)
            text_content = f"Hello {inquiry.first_name},\n\n{reply_message}\n\nBest regards,\nThe JetMyProjects Team"
            
            msg = EmailMultiAlternatives(
                subject=f'Re: Inquiry from {inquiry.first_name} {inquiry.last_name}',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[inquiry.email]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            
            inquiry.status = 'REPLIED'
            inquiry.replied_at = timezone.now()
            inquiry.save()
            
            return redirect('admin_contact_inquiries')
            
    return redirect('admin_contact_inquiries')

def admin_logout(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect('admin_login_page')
    
from .serializers import AdminUserSerializer, AdminTaskSerializer, AdminBillingSerializer, AdminCreateUserSerializer, AdminUpdateUserSerializer, AdminResetPasswordSerializer
from accounts.utils import send_html_otp_email
from django.core import signing

User = get_user_model()

@secure_admin_required
def admin_discount_codes(request):
    codes_list = DiscountCode.objects.all().order_by('-id')
    
    from django.core.paginator import Paginator
    paginator = Paginator(codes_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'AdminDiscountCodes.html', {'discount_codes': page_obj})

@secure_admin_required
def create_discount_code(request):
    if request.method == 'POST':
        code = request.POST.get('code')
        discount_percent = request.POST.get('discount_percent')
        duration_months = request.POST.get('duration_months')
        max_uses = request.POST.get('max_uses')
        valid_until = request.POST.get('valid_until')
        valid_from = request.POST.get('valid_from')
        code_type = request.POST.get('type')
        
        # Sanitize Integers
        if not discount_percent: discount_percent = 0
        if not duration_months: duration_months = 1
        if not max_uses: max_uses = 100
        
        is_trial = (code_type == 'trial')
        if is_trial:
            discount_percent = 100
            
        try:
            DiscountCode.objects.create(
                code=code,
                discount_percent=discount_percent,
                is_trial=is_trial,
                duration_months=duration_months,
                max_uses=max_uses,
                valid_from=valid_from if valid_from else timezone.now(),
                valid_until=valid_until if valid_until else None
            )
            return redirect('admin_discount_codes')
        except Exception as e:
            # Simple error handling -> could use messages framework for better UX
            print(f"Error creating code: {e}")
            return redirect('admin_discount_codes')
            
    return redirect('admin_discount_codes')

@secure_admin_required
def update_discount_code(request, code_id):
    if request.method == 'POST':
        code_obj = get_object_or_404(DiscountCode, id=code_id)
        
        # Get data
        code_name = request.POST.get('code')
        discount_percent = request.POST.get('discount_percent')
        duration_months = request.POST.get('duration_months')
        max_uses = request.POST.get('max_uses')
        valid_until = request.POST.get('valid_until')
        valid_from = request.POST.get('valid_from')
        code_type = request.POST.get('type')
        
        # Sanitize Integers
        if not discount_percent: discount_percent = 0
        if not duration_months: duration_months = 1
        if not max_uses: max_uses = 100
        
        is_trial = (code_type == 'trial')
        if is_trial:
            discount_percent = 100
        
        try:
            # Update fields
            code_obj.code = code_name
            code_obj.discount_percent = discount_percent
            code_obj.is_trial = is_trial
            code_obj.duration_months = duration_months
            code_obj.max_uses = max_uses
            code_obj.valid_from = valid_from if valid_from else timezone.now()
            code_obj.valid_until = valid_until if valid_until else None
            
            code_obj.save()
            return redirect('admin_discount_codes')
        except Exception as e:
            print(f"Error updating code: {e}")
            return redirect('admin_discount_codes')

    return redirect('admin_discount_codes')

@secure_admin_required
def delete_discount_code(request, code_id):
    if request.method == 'POST':
        from django.http import JsonResponse
        try:
            code = get_object_or_404(DiscountCode, id=code_id)
            code.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return redirect('admin_discount_codes')

@secure_admin_required
def get_discount_usage(request, code_id):
    from django.http import JsonResponse
    try:
        discount = DiscountCode.objects.get(id=code_id)
        usages = DiscountUsage.objects.filter(discount_code=discount).select_related('user').order_by('-used_at')
        
        data = []
        for usage in usages:
            data.append({
                'user_email': usage.user.email,
                'user_name': f"{usage.user.first_name} {usage.user.last_name}",
                'date': usage.used_at.strftime("%Y-%m-%d %H:%M:%S")
            })
            
        return JsonResponse({'code': discount.code, 'usages': data}, status=200)
    except DiscountCode.DoesNotExist:
        return JsonResponse({'error': 'Discount code not found'}, status=404)

class AdminSendOTPView(APIView):
    permission_classes = [IsSecureAdminUser]

    def post(self, request):
        email = request.data.get('email')
        first_name = request.data.get('first_name')
        
        if not email:
            return Response({'available': False, 'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        is_taken = User.objects.filter(email=email).exists()
        if is_taken:
             return Response({'available': False, 'error': 'Email already taken'})

        # Generate OTP
        import random
        otp = str(random.randint(100000, 999999))
        
        # Send Email
        try:
            send_html_otp_email(email, otp, first_name)
        except Exception as e:
            print(f"Error sending verification email: {e}")
            return Response({'available': True, 'sent': False, 'error': 'Failed to send OTP email.'})

        # Create Signed Token (valid for 10 minutes)
        # We sign the email and the otp. 
        # When creating user, we verify the submitted OTP matches what we signed for that email.
        token = signing.dumps({'email': email, 'otp': otp})
        
        return Response({'available': True, 'sent': True, 'token': token})

from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class AdminUserListView(APIView):
    permission_classes = [IsSecureAdminUser]

    def get(self, request):
        search_query = request.query_params.get('search', '')
        users = User.objects.all().order_by('-date_joined')
        
        if search_query:
            from django.db.models import Q
            users = users.filter(
                Q(email__icontains=search_query) | 
                Q(first_name__icontains=search_query) | 
                Q(last_name__icontains=search_query)
            )
            
        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(users, request)
        serializer = AdminUserSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

class AdminUserDetailView(APIView):
    permission_classes = [IsSecureAdminUser]

    def get(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        # 1. Total Projects
        from tasks.models import Task, TaskFile
        total_projects = Task.objects.filter(user=user).exclude(status='DELETED').count()

        # 2. Space Used
        total_bytes = 0
        user_files = TaskFile.objects.filter(task__user=user)
        for tf in user_files:
            try:
                if tf.file:
                    total_bytes += tf.file.size
            except Exception:
                pass # File might be missing
        space_used_mb = round(total_bytes / (1024 * 1024), 2)
        
        # 3. Billing Status
        billing_plan = "Free Tier"
        billing_status = "Active" # Default for free
        
        try:
            from subscriptions.models import UserSubscription
            sub = UserSubscription.objects.select_related('plan').filter(user=user, is_active=True).first()
            if sub:
                if sub.plan:
                    billing_plan = sub.plan.name
                
                # Check expiry
                from django.utils import timezone
                if sub.end_date and sub.end_date < timezone.now().date():
                    billing_status = "Expired"
                else:
                    billing_status = "Active"
        except ImportError:
            pass

        data = {
            'id': user.id,
            'email': user.email,
            'full_name': f"{user.first_name} {user.last_name}".strip(),
            'total_projects': total_projects,
            'space_used': f"{space_used_mb} MB",
            'billing_plan': billing_plan,
            'billing_status': billing_status,
            'joined_at': user.date_joined
        }
        return Response(data)

class AdminTaskList(APIView):
    permission_classes = [IsSecureAdminUser]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        search_query = request.query_params.get('search', '')
        
        tasks = Task.objects.all().order_by('-created_at')
        
        if user_id:
            tasks = tasks.filter(user_id=user_id)
            
        if search_query:
            tasks = tasks.filter(project_name__icontains=search_query)
            
        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(tasks, request)
        serializer = AdminTaskSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

class AdminBillingView(APIView):
    permission_classes = [IsSecureAdminUser]

    def get(self, request):
        subs = UserSubscription.objects.all().order_by('-end_date')
        
        paginator = StandardResultsSetPagination()
        result_page = paginator.paginate_queryset(subs, request)
        serializer = AdminBillingSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)

class AdminBlockUserView(APIView):
    permission_classes = [IsSecureAdminUser]

    def put(self, request, id):
        user = get_object_or_404(User, id=id)
        user.is_active = False # Block user
        user.save()
        return Response({"detail": f"User {user.email} has been blocked."})

class AdminUnblockUserView(APIView):
    permission_classes = [IsSecureAdminUser]

    def put(self, request, id):
        user = get_object_or_404(User, id=id)
        user.is_active = True
        user.save()
        return Response({"detail": f"User {user.email} has been unblocked."})

class AdminDeleteUserView(APIView):
    permission_classes = [IsSecureAdminUser]

    def delete(self, request, id):
        user = get_object_or_404(User, id=id)
        email = user.email
        user.delete()
        return Response({"detail": f"User {email} has been deleted."})

class AdminCreateUserView(APIView):
    permission_classes = [IsSecureAdminUser]

    def post(self, request):
        serializer = AdminCreateUserSerializer(data=request.data)
        if serializer.is_valid():
            # Validate OTP Token
            token = request.data.get('otp_token')
            submitted_otp = request.data.get('otp')
            email = request.data.get('email')
            
            if not token or not submitted_otp:
                 return Response({'error': 'OTP verification required. Please Click "Send OTP".'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                data = signing.loads(token, max_age=600) # 10 minutes
                if data['email'] != email:
                    return Response({'error': 'Email mismatch. Please resend OTP.'}, status=status.HTTP_400_BAD_REQUEST)
                if data['otp'] != submitted_otp:
                    return Response({'error': 'Invalid OTP. Please check the code sent to email.'}, status=status.HTTP_400_BAD_REQUEST)
            except signing.SignatureExpired:
                return Response({'error': 'OTP Expired. Please resend.'}, status=status.HTTP_400_BAD_REQUEST)
            except signing.BadSignature:
                return Response({'error': 'Invalid OTP Token. Please resend.'}, status=status.HTTP_400_BAD_REQUEST)

            # OTP Validated. Create User.
            user = serializer.save()
            
            # Save the OTP to the user model as well since it's verified (optional but good for record/consistency)
            user.otp = submitted_otp
            # Set expiry (already verified, but let's set it to now or logic default)
            from django.utils import timezone
            from datetime import timedelta
            user.otp_expiry = timezone.now() + timedelta(minutes=10)
            user.is_email_verified = True # Mark as verified since OTP was validated
            user.save()
            
            # No need to send email again or generate new OTP
            
            return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminUpdateUserView(APIView):
    permission_classes = [IsSecureAdminUser]

    def put(self, request, id):
        user = get_object_or_404(User, id=id)
        serializer = AdminUpdateUserSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(AdminUserSerializer(user).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminResetPasswordView(APIView):
    permission_classes = [IsSecureAdminUser]

    def post(self, request, id):
        user = get_object_or_404(User, id=id)
        serializer = AdminResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"detail": f"Password for {user.email} has been reset."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class DeleteTaskView(APIView):
    permission_classes = [IsSecureAdminUser]

    def delete(self, request, id):
        task = get_object_or_404(Task, id=id)
        task.delete()
        return Response({"detail": "Task deleted successfully."})

class AdminStatsView(APIView):
    permission_classes = [IsSecureAdminUser]

    def get(self, request):
        # Counts
        user_count = User.objects.count()
        task_count = Task.objects.count()
        active_subs = UserSubscription.objects.filter(is_active=True).count()

        # Recent Activity
        recent_users = User.objects.order_by('-date_joined')[:5]
        recent_tasks = Task.objects.order_by('-created_at')[:5]

        # Calculate Total Space Used
        from tasks.models import TaskFile
        total_bytes = 0
        all_files = TaskFile.objects.all()
        for tf in all_files:
            try:
                if tf.file:
                    total_bytes += tf.file.size
            except Exception:
                pass
        
        space_used_mb = round(total_bytes / (1024 * 1024), 2)
        if space_used_mb > 1024:
             space_used_display = f"{round(space_used_mb / 1024, 2)} GB"
        else:
             space_used_display = f"{space_used_mb} MB"

        return Response({
            "counts": {
                "users": user_count,
                "tasks": task_count,
                "subs": active_subs,
                "space_used": space_used_display
            },
            "recent_users": AdminUserSerializer(recent_users, many=True).data,
            "recent_tasks": AdminTaskSerializer(recent_tasks, many=True).data
        })

