# from django.db.models.signals import post_save
# from django.dispatch import receiver
# from .models import Task, TaskNotification
# from django.utils import timezone
# from datetime import timedelta, datetime, time
# import logging

# logger = logging.getLogger(__name__)

# @receiver(post_save, sender=Task)
# def schedule_task_notifications(sender, instance, created, **kwargs):
#     """
#     Schedule email notifications (3d, 24h) when a task is created or updated.
#     Replaces old pending notifications to handle deadline changes.
#     """
#     try:
#         # 1. Clear existing unsent notifications for this task
#         #    If deadline changed, old schedules are invalid.
#         TaskNotification.objects.filter(task=instance, sent=False).delete()

#         # 2. Only schedule for ACTIVE tasks with a set deadline
#         if instance.status != 'ACTIVE' or not instance.deadline_date:
#             return

#         now = timezone.now()
        
#         # Combine date and time
#         deadline_time = instance.deadline_time if instance.deadline_time else time(23, 59, 59)
#         deadline_dt = datetime.combine(instance.deadline_date, deadline_time)
        
#         if timezone.is_naive(deadline_dt):
#             deadline_dt = timezone.make_aware(deadline_dt)

#         # 3. Calculate Notification Times
#         # Add a buffer of 6 hours to ensure users in offsets (like +5:30) get it 
#         # "at the beginning" of the day/window rather than waiting for exact UTC match.
#         buffer = timedelta(hours=6)
#         notify_times = [
#             ('3d', deadline_dt - timedelta(days=3) - buffer),
#             ('24h', deadline_dt - timedelta(hours=24) - buffer)
#         ]

#         new_notifications = []
#         for n_type, n_time in notify_times:
#             # 1. Future Notification: Standard Scheduling
#             if n_time > now:
#                 new_notifications.append(
#                     TaskNotification(
#                         task=instance,
#                         notify_at=n_time,
#                         type=n_type,
#                         sent=False
#                     )
#                 )
#             # 2. Catch-Up Logic: (Fix for "created within window")
#             # If the calculated time (with buffer) is in the past, 
#             # BUT we represent a "3 Day" warning, we should only send it if it's still somewhat relevant.
#             # Updated Rule: Only send "3 Days Left" if there are at least 2 Days (48h) remaining.
#             # If less than 48h, it's too late for a "3 Day" warning to make sense -> Skip it.
#             elif n_type == '3d' and (deadline_dt - now) > timedelta(hours=73):
#                 # If we are inside the 3d window but still have > 48 hours, send the 3d reminder now.
#                  new_notifications.append(
#                     TaskNotification(
#                         task=instance,
#                         notify_at=now,
#                         type=n_type,
#                         sent=False
#                     )
#                 )
#             # Catch-Up Logic for 24h:
#             # If created within 24h window (e.g. 23 hours left)
#             elif n_type == '24h' and (deadline_dt - now) > timedelta(hours=1):
#                  new_notifications.append(
#                     TaskNotification(
#                         task=instance,
#                         notify_at=now,
#                         type=n_type,
#                         sent=False
#                     )
#                 )

#         if new_notifications:
#             TaskNotification.objects.bulk_create(new_notifications)
#             logger.info(f"Scheduled {len(new_notifications)} notifications for task {instance.id}")

#     except Exception as e:
#         logger.error(f"Error scheduling notifications for task {instance.id}: {e}")


from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta, datetime, time
from .models import Task, TaskNotification
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Task)
def schedule_task_notifications(sender, instance, created, **kwargs):
    try:
        # Remove old pending notifications
        TaskNotification.objects.filter(task=instance, sent=False).delete()

        # Only active tasks with deadline
        if instance.status != 'ACTIVE' or not instance.deadline_date:
            return

        now = timezone.now()

        deadline_time = instance.deadline_time or time(23, 59, 59)
        deadline_dt = datetime.combine(instance.deadline_date, deadline_time)

        import pytz
        
        # Determine User Timezone
        try:
            tz_name = instance.user.timezone if instance.user.timezone else 'Asia/Kolkata'
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.UTC

        if timezone.is_naive(deadline_dt):
            # Explicitly localize using pytz to avoid LMT (+5:53) issues
            try:
                deadline_dt = user_tz.localize(deadline_dt)
            except AttributeError:
                 # Fallback if user_tz isn't a pytz object (unlikely here)
                deadline_dt = timezone.make_aware(deadline_dt, timezone=user_tz)
        
        # Convert to UTC for calculation
        deadline_dt = deadline_dt.astimezone(pytz.UTC)

        # No notifications after deadline
        if now >= deadline_dt:
            return

        notifications = []

        # 3-day reminder
        notify_3d = deadline_dt - timedelta(days=3)
        if notify_3d > now:
            notifications.append(
                TaskNotification(
                    task=instance,
                    notify_at=notify_3d,
                    type='3d',
                    sent=False
                )
            )

        # 24-hour reminder
        notify_24h = deadline_dt - timedelta(hours=24)
        if notify_24h > now:
            notifications.append(
                TaskNotification(
                    task=instance,
                    notify_at=notify_24h,
                    type='24h',
                    sent=False
                )
            )

        # 1-hour reminder
        notify_1h = deadline_dt - timedelta(hours=1)
        if notify_1h > now:
            notifications.append(
                TaskNotification(
                    task=instance,
                    notify_at=notify_1h,
                    type='1h',
                    sent=False
                )
            )

        if notifications:
            TaskNotification.objects.bulk_create(notifications)
            logger.info(
                f"Scheduled {len(notifications)} notifications for task {instance.id}"
            )
            return

        # --- Catch-Up Logic ---
        # If we missed the exact window (e.g. created at 2d 23h), but it's still useful.
        
        # Catch-up 3d: If > 48h remaining (but missed 72h mark)
        if (deadline_dt - now) > timedelta(hours=48):
             # Check if we should have sent it but didn't (calculated time < now)
             if notify_3d <= now:
                 notifications.append(
                    TaskNotification(
                        task=instance,
                        notify_at=now,
                        type='3d',
                        sent=False
                    )
                 )
        
        # Catch-up 24h: If > 1h remaining (but missed 24h mark) - rare but possible
        elif (deadline_dt - now) > timedelta(hours=1):
             if notify_24h <= now:
                 notifications.append(
                    TaskNotification(
                        task=instance,
                        notify_at=now,
                        type='24h',
                        sent=False
                    )
                 )

        # Catch-up 1h: If > 10m remaining (but missed 1h mark)
        elif (deadline_dt - now) > timedelta(minutes=10):
             if notify_1h <= now:
                 notifications.append(
                    TaskNotification(
                        task=instance,
                        notify_at=now,
                        type='1h',
                        sent=False
                    )
                 )

        if notifications:
            TaskNotification.objects.bulk_create(notifications)
            logger.info(f"Scheduled (Catch-Up) {len(notifications)} notifications for task {instance.id}")

    except Exception as e:
        logger.error(
            f"Error scheduling notifications for task {instance.id}: {e}"
        )

@receiver(post_migrate)
def create_default_tasks(sender, **kwargs):
    if sender.name == 'tasks':
        try:
            from tasks.models import ScheduledTask
            # Seed the database with the core task if it doesn't exist
            if not ScheduledTask.objects.filter(name="check_deadline_reminders").exists():
                try:
                    ScheduledTask.objects.create(
                        name="check_deadline_reminders",
                        next_run_at=timezone.now(),
                        interval_seconds=3600, # Run hourly
                        is_running=False
                    )
                    print("Scheduler: Created default 'check_deadline_reminders' task.")
                except Exception:
                    pass # Ignore creation errors
        except Exception:
            pass # Ignore DB errors
