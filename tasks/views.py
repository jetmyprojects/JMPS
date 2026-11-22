from rest_framework import viewsets, status, mixins, views
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from accounts.authentication import CookieJWTAuthentication
from .models import Task, TaskFile, ActivityLog
from .serializers import TaskSerializer, TaskFileSerializer
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 6
    page_size_query_param = 'page_size'
    max_page_size = 100

class DashboardStatsView(views.APIView):
    authentication_classes = [CookieJWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        today = now.date()
        week_ago = now - timedelta(days=7)

        # 1. Active Projects Count
        active_count = Task.objects.filter(user=user, status='ACTIVE').count()

        # 2. Added this week
        added_this_week = Task.objects.filter(user=user, created_at__gte=week_ago).count()

        # 3. Upcoming Deadlines (Active tasks with deadline >= today AND < 7 days away)
        # We filter here so the Count on the card matches the "Critical/Upcoming" definition
        next_week = today + timedelta(days=7)
        upcoming_tasks = Task.objects.filter(
            user=user, 
            status='ACTIVE', 
            deadline_date__gte=today,
            deadline_date__lt=next_week
        ).order_by('deadline_date', 'deadline_time')
        
        upcoming_count = upcoming_tasks.count()
        
        # Next Deadline Details
        next_deadline_task = upcoming_tasks.first()
        next_deadline_info = None
        if next_deadline_task:
            days_left = (next_deadline_task.deadline_date - today).days
            next_deadline_info = {
                'date': next_deadline_task.deadline_date,
                'days_left': days_left
            }

        # 4. Critical/Upcoming Tasks List (Top 5)
        # upcoming_tasks is already filtered to < 7 days
        critical_tasks = upcoming_tasks[:5]
        
        # Serialize critical tasks manually or use serializer
        critical_tasks_data = []
        for task in critical_tasks:
            days_left = (task.deadline_date - today).days
            urgency = 'Stable'
            badge_class = 'bg-info text-white'
            
            if days_left < 3:
                urgency = 'Critical'
                badge_class = 'bg-danger'
            elif days_left < 7:
                urgency = 'Upcoming'
                badge_class = 'bg-warning text-dark'
                
            critical_tasks_data.append({
                'project_name': task.project_name,
                'deadline_date': task.deadline_date,
                'urgency': urgency,
                'badge_class': badge_class
            })

        # 4.5 Pinned Projects
        pinned_tasks = Task.objects.filter(user=user, is_pinned=True, status='ACTIVE')
        pinned_tasks_data = TaskSerializer(pinned_tasks, many=True).data

        # 4.6 Recent Activity
        recent_activity = ActivityLog.objects.filter(user=user)[:5]
        activity_data = [{'action': log.action, 'timestamp': log.timestamp} for log in recent_activity]

        # 5. Storage Calculation
        from storage.utils import get_user_storage, get_storage_breakdown
        total_bytes = get_user_storage(user)
        breakdown_bytes = get_storage_breakdown(user)
        
        storage_used_mb = round(total_bytes / (1024 * 1024), 2)
        
        # Convert breakdown to MB
        breakdown_mb = {
            'active': round(breakdown_bytes.get('ACTIVE', 0) / (1024 * 1024), 2),
            'draft': round(breakdown_bytes.get('DRAFT', 0) / (1024 * 1024), 2),
            'completed': round(breakdown_bytes.get('COMPLETED', 0) / (1024 * 1024), 2),
            'deleted': round(breakdown_bytes.get('DELETED', 0) / (1024 * 1024), 2),
            'uncompleted': round(breakdown_bytes.get('UNCOMPLETED', 0) / (1024 * 1024), 2),
        }
        
        # Get storage limit from subscription
        # Get storage limit and plan details from subscription
        storage_limit_mb = 1024 # Default 1GB for Free Plan
        plan_name = "Free Plan"
        plan_renewal = None
        
        try:
            # Need to import UserSubscription locally or at top
            from subscriptions.models import UserSubscription
            
            # Helper for admin override display
            if user.is_staff or user.is_superuser:
                 plan_name = "Admin Access"
                 storage_limit_mb = 100 * 1024 # 100GB
                 plan_renewal = None # No expiry
            else:
                 sub = UserSubscription.objects.select_related('plan').filter(user=user, is_active=True).first()
                 if sub:
                     if sub.plan:
                         storage_limit_mb = sub.plan.storage_limit_mb
                         plan_name = sub.plan.name
                     if sub.end_date:
                         plan_renewal = sub.end_date
        except Exception:
            pass
            
        storage_total_gb = round(storage_limit_mb / 1024, 2)
        storage_percent = 0
        if storage_limit_mb > 0:
            storage_percent = round((storage_used_mb / storage_limit_mb) * 100)

        data = {
            'user_name': user.first_name if user.first_name else user.username,
            'active_count': active_count,
            'added_this_week': added_this_week,
            'upcoming_count': upcoming_count,
            'next_deadline': next_deadline_info,
            'critical_tasks': critical_tasks_data,
            'pinned_tasks': pinned_tasks_data,
            'recent_activity': activity_data,
            'storage_used_mb': storage_used_mb, 
            'storage_limit_mb': storage_limit_mb,
            'storage_total_gb': storage_total_gb,
            'storage_percent': storage_percent,
            'breakdown_mb': breakdown_mb,
            'plan_name': plan_name,
            'plan_renewal': plan_renewal
        }
        
        return Response(data)

class TaskFileViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = TaskFile.objects.all()
    serializer_class = TaskFileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return TaskFile.objects.filter(task__user=self.request.user)

class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    lookup_field = 'id'

    lookup_field = 'id'

    def _check_subscription_status(self, user):
        """
        Check if the user has an active subscription.
        Returns True if active, False if expired.
        """
        # Exempt Admins/Staff
        if user.is_staff or user.is_superuser:
            return True

        from subscriptions.models import UserSubscription
        try:
            sub = UserSubscription.objects.get(user=user)
            # Check if active status is True AND end_date is not in the past
            today = timezone.now().date()
            if not sub.is_active:
                return False
            if sub.end_date < today:
                return False
            return True
        except UserSubscription.DoesNotExist:
            # STRICT MODE: No subscription record means NO ACCESS.
            # User must have either a Paid Plan or an Active Trial.
            return False

    def _check_expiry(self):
        # Auto-expire tasks
        from django.utils import timezone
        import pytz
        
        # Get current time in the User's timezone
        now = timezone.now()
        target_tz = timezone.get_current_timezone() # Default
        
        user = self.request.user
        if user.is_authenticated and hasattr(user, 'timezone') and user.timezone:
            try:
                target_tz = pytz.timezone(user.timezone)
            except pytz.UnknownTimeZoneError:
                pass
        
        now_local = now.astimezone(target_tz)
        today = now_local.date()
        current_time = now_local.time()
        
        # 1. Past dates (strictly less than today)
        Task.objects.filter(
            user=self.request.user, 
            status='ACTIVE', 
            deadline_date__lt=today
        ).update(status='UNCOMPLETED')
        
        # 2. Today but past time (if time is set)
        # Note: We filter for deadline_date=today AND deadline_time < current_time
        # Use range or exact match? Exact match on date is fine.
        Task.objects.filter(
            user=self.request.user,
            status='ACTIVE',
            deadline_date=today,
            deadline_time__lt=current_time
        ).update(status='UNCOMPLETED')

    def get_queryset(self):
        self._check_expiry()
        # By default, exclude deleted tasks from the main list unless explicitly asked
        queryset = Task.objects.filter(user=self.request.user)
        
        # Actions that need to access DELETED items
        allowed_actions_for_deleted = ['restore', 'permanent_delete', 'deleted', 'retrieve']
        
        if self.action not in allowed_actions_for_deleted:
             queryset = queryset.exclude(status='DELETED')
        return queryset

    def perform_create(self, serializer):
        if not self._check_subscription_status(self.request.user):
            raise PermissionDenied("Your subscription has expired. You cannot create new projects.")
        task = serializer.save(user=self.request.user)
        ActivityLog.objects.create(user=self.request.user, action=f"Created project '{task.project_name}'")

    def perform_update(self, serializer):
         if not self._check_subscription_status(self.request.user):
            raise PermissionDenied("Your subscription has expired. You cannot update projects.")
         task = serializer.save()
         # Optional: Log update? 
         # ActivityLog.objects.create(user=self.request.user, action=f"Updated project '{task.project_name}'")

    def destroy(self, request, *args, **kwargs):
        # Allow deletion even if expired -> CHANGED: Enforce subscription
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot delete projects.'}, status=status.HTTP_403_FORBIDDEN)

        # Soft Delete
        task = self.get_object()
        task.previous_status = task.status
        task.status = 'DELETED'
        task.save()
        ActivityLog.objects.create(user=request.user, action=f"Deleted project '{task.project_name}' from {task.previous_status}")
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- STATUS FILTERS ---

    @action(detail=False, methods=['get'])
    def active(self, request):
        self._check_expiry()
        tasks = Task.objects.filter(user=request.user, status='ACTIVE').order_by('deadline_date', 'deadline_time', '-created_at')
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def draft(self, request):
        tasks = Task.objects.filter(user=request.user, status='DRAFT').order_by('-created_at')
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def completed(self, request):
        tasks = Task.objects.filter(user=request.user, status='COMPLETED').order_by('-created_at')
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def deleted(self, request):
        tasks = Task.objects.filter(user=request.user, status='DELETED').order_by('-created_at')
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def uncompleted(self, request):
        self._check_expiry()
        tasks = Task.objects.filter(user=request.user, status='UNCOMPLETED').order_by('-created_at')
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tasks, many=True)
        return Response(serializer.data)

    # --- STATE TRANSITIONS ---

    @action(detail=True, methods=['post'])
    def complete(self, request, *args, **kwargs):
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot complete projects.'}, status=status.HTTP_403_FORBIDDEN)
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        if not user_id_val:
             return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            task = Task.objects.get(id=int(user_id_val), user=request.user)
            task.status = 'COMPLETED'
            task.save()
            ActivityLog.objects.create(user=request.user, action=f"Completed project '{task.project_name}'")
            return Response({'status': 'task marked as completed'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def activate(self, request, *args, **kwargs):
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot activate projects.'}, status=status.HTTP_403_FORBIDDEN)
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        if not user_id_val:
             return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            task = Task.objects.get(id=int(user_id_val), user=request.user)
            task.status = 'ACTIVE'
            task.save()
            ActivityLog.objects.create(user=request.user, action=f"Activated project '{task.project_name}'")
            return Response({'status': 'task active'})
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def restore(self, request, *args, **kwargs):
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot restore projects.'}, status=status.HTTP_403_FORBIDDEN)
        logger.debug(f"restore called. kwargs={kwargs}, user={request.user}")
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        logger.debug(f"user_id_val raw={user_id_val}")
        
        if not user_id_val:
            return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            user_id_val = int(user_id_val)
            logger.debug(f"user_id_val int={user_id_val}")
            
            # Use filter().first() to avoid strictly crashing, or strict get() to debug
            task = Task.objects.get(id=user_id_val, user=request.user)
            logger.debug(f"Task found: {task}")
            
            task.status = 'DRAFT'
            task.save()
            return Response({'status': 'task restored to draft'})
        except Exception as e:
            logger.error(f"Restore failed with error: {e}")
            import traceback
            traceback.print_exc()
            return Response({'detail': f"Restore Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'])
    def permanent_delete(self, request, *args, **kwargs):
        # Allow deletion even if expired -> CHANGED
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot permanently delete projects.'}, status=status.HTTP_403_FORBIDDEN)

        logger.debug(f"permanent_delete called. kwargs={kwargs}, user={request.user}")
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        
        if not user_id_val:
            return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id_val = int(user_id_val)
            task = Task.objects.get(id=user_id_val, user=request.user)
            logger.debug(f"Deleting task {task}")
            task.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Delete failed with error: {e}")
            return Response({'detail': f"Delete Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def duplicate(self, request, *args, **kwargs):
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot duplicate projects.'}, status=status.HTTP_403_FORBIDDEN)
        logger.debug(f"duplicate called. kwargs={kwargs}, user={request.user}")
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        
        if not user_id_val:
            return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user_id_val = int(user_id_val)
            task = Task.objects.get(id=user_id_val, user=request.user)
            
            # Create a new task with the same data
            new_task = Task.objects.create(
                user=request.user,
                project_name=f"Duplicate_{task.project_name}",
                deadline_date=task.deadline_date,
                deadline_time=task.deadline_time,
                project_notes=task.project_notes,
                status='DRAFT' 
            )
            
            # Copy associated files
            for task_file in task.files.all():
                if task_file.file:
                    TaskFile.objects.create(
                        task=new_task,
                        file=task_file.file
                    )
            
            serializer = self.get_serializer(new_task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Duplicate failed with error: {e}")
            import traceback
            traceback.print_exc()
            return Response({'detail': f"Duplicate Failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def toggle_pin(self, request, *args, **kwargs):
        if not self._check_subscription_status(request.user):
             return Response({'detail': 'Your subscription has expired. You cannot pin projects.'}, status=status.HTTP_403_FORBIDDEN)
        user_id_val = kwargs.get('id') or kwargs.get('pk')
        if not user_id_val:
             return Response({'detail': 'ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            task = Task.objects.get(id=int(user_id_val), user=request.user)
            task.is_pinned = not task.is_pinned
            task.save()
            return Response({'status': 'pin toggled', 'is_pinned': task.is_pinned})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
