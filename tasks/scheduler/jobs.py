
# tasks/scheduler/jobs.py
import logging
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Q
from tasks.models import Task, TaskNotification
# reuse existing email logic if available or implement new
from django.core.mail import send_mail
from django.conf import settings
from .registry import register_task

logger = logging.getLogger(__name__)

@register_task("check_deadline_reminders")
def check_deadline_reminders():
    """
    Task to check for approaching deadlines (24h and 3 Days) and send emails.
    Respects user's timezone if set.
    """
    from tasks.services import send_deadline_email
    
    print("DEBUG: check_deadline_reminders STARTED", flush=True)
    now = timezone.now()
    
    # Pre-calculate UTC windows
    # 1. 24 Hours Reminder (Looking for deadline = now + 24h)
    #    Window: [now + 23h, now + 25h]
    start_24h = now + timedelta(hours=23)
    end_24h = now + timedelta(hours=25)
    
    # 2. 3 Days Reminder (Looking for deadline = now + 3d)
    #    Window: [now + 2d 23h, now + 3d 1h]
    start_3d = now + timedelta(days=2, hours=23)
    end_3d = now + timedelta(days=3, hours=1)

    print(f"DEBUG: Checking 24h window: {start_24h} to {end_24h}", flush=True)
    
    # Fetch active tasks with deadlines pending notification
    # We need user.timezone, so select_related('user')
    tasks = Task.objects.filter(
        status='ACTIVE',
        deadline_date__isnull=False
    ).select_related('user')
    
    # Filter in Python because deadline needs timezone conversion
    count_24h = 0
    count_3d = 0
    
    print(f"DEBUG: Scanning {tasks.count()} active tasks...", flush=True)

    for task in tasks:
        try:
            # Skip if both notified
            if task.notified_24h and task.notified_3d:
                continue
                
            # Get User Timezone
            user_tz_str = getattr(task.user, 'timezone', 'UTC')
            try:
                import pytz
                user_tz = pytz.timezone(user_tz_str)
            except Exception:
                user_tz = timezone.utc
                
            # Construct Awareness Deadline
            dt = task.deadline_date
            tm = task.deadline_time if task.deadline_time else datetime.min.time()
            naive_deadline = datetime.combine(dt, tm)
            
            # Make it aware in USER'S timezone
            if timezone.is_naive(naive_deadline):
                if hasattr(user_tz, 'localize'):
                    deadline = user_tz.localize(naive_deadline)
                else:
                    try:
                        deadline = timezone.make_aware(naive_deadline, timezone=user_tz)
                    except ValueError:
                         # Handle ambiguous times etc (e.g. DST transition)
                         deadline = naive_deadline.replace(tzinfo=user_tz)
            else:
                deadline = naive_deadline
                
            # Convert to UTC for comparison with 'now' windows
            # Use datetime.timezone.utc which works with astimezone
            from datetime import timezone as dt_timezone
            deadline_utc = deadline.astimezone(dt_timezone.utc)
            
            # Check 24h
            if not task.notified_24h:
                if start_24h <= deadline_utc <= end_24h:
                    print(f"DEBUG: Task {task.id} (User TZ: {user_tz_str}) MATCHES 24h window. Sending email...", flush=True)
                    if send_deadline_email(task, '24h'):
                        task.notified_24h = True
                        task.save()
                        count_24h += 1
                        print(f"DEBUG: Email 24h sent successfully.", flush=True)
                    else:
                        print(f"DEBUG: Email 24h FAILED (send_deadline_email returned False).", flush=True)

            # Check 3d
            if not task.notified_3d:
                if start_3d <= deadline_utc <= end_3d:
                    print(f"DEBUG: Task {task.id} (User TZ: {user_tz_str}) MATCHES 3d window. Sending email...", flush=True)
                    if send_deadline_email(task, '3d'):
                        task.notified_3d = True
                        task.save()
                        count_3d += 1
                        print(f"DEBUG: Email 3d sent successfully.", flush=True)
                    else:
                        print(f"DEBUG: Email 3d FAILED (send_deadline_email returned False).", flush=True)

            # Check 1h
            # Window: [now + 50m, now + 70m]
            start_1h = now + timedelta(minutes=50)
            end_1h = now + timedelta(minutes=70)

            if not getattr(task, 'notified_1h', False):
                if start_1h <= deadline_utc <= end_1h:
                    print(f"DEBUG: Task {task.id} (User TZ: {user_tz_str}) MATCHES 1h window. Sending email...", flush=True)
                    if send_deadline_email(task, '1h'):
                        task.notified_1h = True
                        task.save()
                        print(f"DEBUG: Email 1h sent successfully.", flush=True)
                    else:
                        print(f"DEBUG: Email 1h FAILED (send_deadline_email returned False).", flush=True)

            # Check Overdue 24h
            # Logic: If deadline passed 24 hours ago (deadline < now - 24h)
            # Window: [now - 25h, now - 23h] relative to deadline? 
            # Easier: target_overdue_time = deadline + 24h. Check if now is around target_overdue_time.
            # Window: [now - 1h, now + 1h] of (deadline + 24h)
            # Let's say we want to strict match like the others.
            # Deadline should be between (now - 25h) and (now - 23h)
            
            overdue_start_24h = now - timedelta(hours=25)
            overdue_end_24h = now - timedelta(hours=23)
            
            if not getattr(task, 'notified_overdue_24h', False):
                if overdue_start_24h <= deadline_utc <= overdue_end_24h:
                     print(f"DEBUG: Task {task.id} Match OVERDUE 24h window. sending...", flush=True)
                     if send_deadline_email(task, 'overdue_24h'):
                         task.notified_overdue_24h = True
                         task.save()
                         print("DEBUG: Overdue Email Sent.", flush=True)

        except Exception as e:
            print(f"DEBUG: Error processing task {task.id}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            continue
                
    print(f"DEBUG: Sent {count_24h} 24h reminders and {count_3d} 3d reminders.", flush=True)
    print("DEBUG: check_deadline_reminders FINISHED", flush=True)
