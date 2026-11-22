from django.core.management.base import BaseCommand
from tasks.models import TaskNotification
from tasks.services import send_deadline_email
from django.utils import timezone
import logging

# Configure logger for cron output capture if needed, 
# though usually cron redirects stdout/stderr.
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process pending deadline notifications (Cron Entry Point)'

    def handle(self, *args, **options):
        self.stdout.write(f"[{timezone.now()}] Starting deadline notification check...")
        
        try:
            now = timezone.now()
            
            # Query active, unsent notifications that are due
            # We filter by task__status='ACTIVE' to ensure we don't notify for deleted/completed tasks
            due_notifications = TaskNotification.objects.select_related('task', 'task__user').filter(
                sent=False, 
                notify_at__lte=now,
                task__status='ACTIVE'
            )
            
            count = due_notifications.count()
            if count == 0:
                self.stdout.write("No pending notifications found.")
                return

            self.stdout.write(f"Found {count} notifications to process.")

            success_count = 0
            fail_count = 0

            for notification in due_notifications:
                try:
                    self.stdout.write(f"Processing {notification}...")
                    
                    # Idempotency check: Double check logically before sending (though DB filter handles it)
                    if notification.sent:
                        continue
                    
                    # --- SAFETY CHECK: Hard Stop if deadline passed ---
                    # Calculate deadline exactly like in services.py to ensure consistency
                    # This prevents "retry loops" for expired tasks.
                    from datetime import datetime, time
                    import pytz
                    
                    task = notification.task
                    d_time = task.deadline_time or time(23, 59, 59)
                    d_naive = datetime.combine(task.deadline_date, d_time)
                    
                    try:
                        # Use user's timezone or fallback
                        tz_name = task.user.timezone if task.user.timezone else 'Asia/Kolkata'
                        user_tz = pytz.timezone(tz_name)
                    except Exception:
                        user_tz = pytz.UTC
                        
                    if timezone.is_naive(d_naive):
                        d_aware = timezone.make_aware(d_naive, timezone=user_tz)
                    else:
                        d_aware = d_naive
                        
                    # Compare in UTC
                    d_utc = d_aware.astimezone(pytz.UTC)
                    
                    if now >= d_utc:
                        self.stdout.write(self.style.WARNING(f" -> SKIPPING {task.id}: Deadline {d_utc} passed. Marking as handled."))
                        notification.sent = True
                        notification.save(update_fields=['sent'])
                        continue
                    # --------------------------------------------------

                    # Send Email
                    # We reuse the robust service function
                    sent = send_deadline_email(notification.task, notification.type)
                    
                    if sent:
                        notification.sent = True
                        notification.save(update_fields=['sent'])
                        self.stdout.write(self.style.SUCCESS(f" -> Sent email to {notification.task.user.email}"))
                        success_count += 1
                    else:
                        self.stdout.write(self.style.WARNING(f" -> Failed to send email for {notification.task.id}"))
                        fail_count += 1

                except Exception as inner_e:
                    self.stderr.write(self.style.ERROR(f" -> Error processing notification {notification.id}: {inner_e}"))
                    fail_count += 1

            self.stdout.write(self.style.SUCCESS(
                f"[{timezone.now()}] Completed. Success: {success_count}, Failed: {fail_count}"
            ))

        except Exception as e:
            # Catch-all to ensure Cron doesn't crash silently
            self.stderr.write(self.style.ERROR(f"CRITICAL ERROR in cron job: {e}"))
            # In a real production system, you might trigger an alert here (Sentry/PagerDuty)
