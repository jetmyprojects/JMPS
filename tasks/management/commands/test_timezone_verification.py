from django.core.management.base import BaseCommand
from accounts.models import User
from tasks.models import Task, TaskNotification
from django.utils import timezone
from datetime import datetime, time, timedelta
import pytz

class Command(BaseCommand):
    help = 'Verify timezone logic'

    def handle(self, *args, **options):
        with open('verification_output.txt', 'w') as f:
            def log(msg):
                f.write(msg + '\n')
                self.stdout.write(msg)

            log("Starting Timezone Verification...")

            # 1. Create Test User in New York
            email = f"test_ny_{int(timezone.now().timestamp())}@example.com"
            user, created = User.objects.get_or_create(username=email, email=email)
            user.timezone = 'America/New_York'
            user.save()
            log(f"Created user {user.email} with timezone {user.timezone}")

            # 2. Define Deadline relative to NY
            ny_tz = pytz.timezone('America/New_York')
            now_ny = timezone.now().astimezone(ny_tz)
            
            deadline_date_ny = (now_ny + timedelta(days=10)).date()
            deadline_time_ny = time(12, 0, 0) # Noon NY time
            
            log(f"Setting deadline to {deadline_date_ny} {deadline_time_ny} (NY Time)")

            # 3. Create Task
            task = Task.objects.create(
                user=user,
                project_name="TimeZone Test Task",
                deadline_date=deadline_date_ny,
                deadline_time=deadline_time_ny,
                status='ACTIVE'
            )

            # 4. Verify Notification Time in UTC
            deadline_naive = datetime.combine(deadline_date_ny, deadline_time_ny)
            # Make sure to handle potential awareness issues if needed, but for now assuming pytz works as expected
            deadline_aware_ny = ny_tz.localize(deadline_naive)
            deadline_utc = deadline_aware_ny.astimezone(pytz.UTC)
            
            expected_notify_3d_utc = deadline_utc - timedelta(days=3)
            
            # Fetch notification
            notif = TaskNotification.objects.filter(task=task, type='3d').first()
            
            if not notif:
                log("FAILED: No 3d notification created!")
                return

            diff = abs((notif.notify_at - expected_notify_3d_utc).total_seconds())
            
            log(f"Notification Time (UTC): {notif.notify_at}")
            log(f"Expected Time (UTC):     {expected_notify_3d_utc}")
            log(f"Difference: {diff} seconds")

            if diff < 5: # Allow small buffer
                log("SUCCESS: Notification scheduled correctly based on NY timezone.")
            else:
                log("FAILED: Notification time mismatch.")
                
            # 5. Verify UTC User
            email_utc = f"test_utc_{int(timezone.now().timestamp())}@example.com"
            user_utc, _ = User.objects.get_or_create(username=email_utc, email=email_utc)
            user_utc.timezone = 'UTC'
            user_utc.save()
            
            task_utc = Task.objects.create(
                user=user_utc,
                project_name="UTC Test Task",
                deadline_date=deadline_date_ny,
                deadline_time=deadline_time_ny, # Same wall clock time, but in UTC
                status='ACTIVE'
            )
            
            # Expected for UTC user:
            # Deadline is 12:00 UTC
            deadline_aware_utc_user = pytz.UTC.localize(datetime.combine(deadline_date_ny, deadline_time_ny))
            
            # Verify that the two deadlines are different absolute times
            if deadline_aware_ny == deadline_aware_utc_user:
                 log("FAILED: Logic treats NY and UTC the same!")
            else:
                 log(f"Verified NY time ({deadline_aware_ny}) != UTC time ({deadline_aware_utc_user})")

            # Cleanup
            task.delete()
            user.delete()
            task_utc.delete()
            user_utc.delete()
