from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from .models import TaskNotification
import logging

logger = logging.getLogger(__name__)



def send_deadline_email(task, n_type):
    """
    Sends the HTML email for a specific notification type (3d or 24h).
    """
    try:
        subject_map = {
            '3d': f"Reminder: 3 Days Left for {task.project_name}",
            '3d': f"Reminder: 3 Days Left for {task.project_name}",
            '24h': f"URGENT: 24 Hours Left for {task.project_name}",
            '1h': f"URGENT: 1 Hour Left for {task.project_name}",
            'overdue_24h': f"OVERDUE: {task.project_name} is 24 Hours Late"
        }
        
        email_subject = subject_map.get(n_type, f"Reminder: Deadline Approaching for {task.project_name}")
        
        # Calculate context
        now = timezone.now()
        # Re-calculate time remaining for accurate display
        # (Though technically we know it's approx 3d or 24h)
        # Re-calculate time remaining based on User's Timezone
        # (Inputs like "12:00 PM" are assumed to be in the user's local time)
        from datetime import datetime, time, timedelta
        import pytz
        
        deadline_time = task.deadline_time if task.deadline_time else time(23, 59, 59)
        deadline_naive = datetime.combine(task.deadline_date, deadline_time)
        
        try:
            # Use user's timezone if valid, default to 'Asia/Kolkata' only if not set/invalid
            tz_name = task.user.timezone if task.user.timezone else 'Asia/Kolkata'
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.UTC

        if timezone.is_naive(deadline_naive):
            if hasattr(user_tz, 'localize'):
                deadline_dt = user_tz.localize(deadline_naive)
            else:
                deadline_dt = timezone.make_aware(deadline_naive, timezone=user_tz)
        else:
            deadline_dt = deadline_naive
            
        # Normalize to UTC for safe arithmetic
        deadline_utc = deadline_dt.astimezone(pytz.UTC)
        
        # 2. Hard-Stop: If deadline passed, DO NOT send (UNLESS it is an overdue type).
        if now >= deadline_utc and 'overdue' not in n_type:
            logger.warning(f"Aborting email for task {task.id}: Deadline {deadline_utc} already passed.")
            return False

        time_remaining = deadline_utc - now
        
        days = time_remaining.days
        hours = time_remaining.seconds // 3600
        minutes = (time_remaining.seconds % 3600) // 60
        
        if days == 0:
            time_remaining_str = f"{hours} hours, {minutes} minutes"
        elif days == 1:
            time_remaining_str = f"1 Day, {hours} hours, {minutes} minutes"
        else:
            time_remaining_str = f"{days} days, {hours} hours, {minutes} minutes"

        context = {
            'task': task,
            'time_remaining': time_remaining_str,
            'user': task.user
        }

        html_message = render_to_string('emails/deadline_notification.html', context)
        plain_message = ""
        from_email = settings.DEFAULT_FROM_EMAIL
        
        email_msg = EmailMultiAlternatives(
            subject=email_subject,
            body=plain_message,
            from_email=from_email,
            to=[task.user.email]
        )
        email_msg.attach_alternative(html_message, "text/html")
        email_msg.send(fail_silently=False)
        
        logger.info(f"Sent {n_type} notification for task {task.id} to {task.user.email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send {n_type} email for task {task.id}: {e}")
        return False


def process_due_notifications():
    """
    Checks for due notifications and sends emails.
    Intended to be called by middleware or management command.
    """
    from .models import TaskNotification
    from django.utils import timezone
    import pytz
    from datetime import datetime, time

    logger.info("Checking for due notifications...")
    
    try:
        now = timezone.now()
        
        # Query active, unsent notifications that are due
        due_notifications = TaskNotification.objects.select_related('task', 'task__user').filter(
            sent=False, 
            notify_at__lte=now,
            task__status='ACTIVE'
        )
        
        count = due_notifications.count()
        if count == 0:
            return 0

        logger.info(f"Found {count} notifications to process.")
        success_count = 0

        for notification in due_notifications:
            try:
                # Double check if already sent (race condition safety)
                notification.refresh_from_db()
                if notification.sent:
                    continue

                # --- SAFETY CHECK: Hard Stop if deadline passed ---
                task = notification.task
                d_time = task.deadline_time or time(23, 59, 59)
                d_naive = datetime.combine(task.deadline_date, d_time)
                
                try:
                    tz_name = task.user.timezone if task.user.timezone else 'Asia/Kolkata'
                    user_tz = pytz.timezone(tz_name)
                except Exception:
                    user_tz = pytz.UTC
                    
                if timezone.is_naive(d_naive):
                    if hasattr(user_tz, 'localize'):
                        d_aware = user_tz.localize(d_naive)
                    else:
                        d_aware = timezone.make_aware(d_naive, timezone=user_tz)
                else:
                    d_aware = d_naive
                    
                # Compare in UTC
                d_utc = d_aware.astimezone(pytz.UTC)
                
                if now >= d_utc:
                    logger.warning(f"Skipping {task.id}: Deadline {d_utc} passed. Marking as handled.")
                    notification.sent = True
                    notification.save(update_fields=['sent'])
                    continue

                # Send Email
                if send_deadline_email(notification.task, notification.type):
                    notification.sent = True
                    notification.save(update_fields=['sent'])
                    success_count += 1
            
            except Exception as e:
                logger.error(f"Error processing notification {notification.id}: {e}")

        return success_count

    except Exception as e:
        logger.error(f"Critical error in process_due_notifications: {e}")
        return 0
