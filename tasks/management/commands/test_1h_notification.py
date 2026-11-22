from django.core.management.base import BaseCommand
from django.utils import timezone
from tasks.models import Task, TaskNotification
from tasks.scheduler.jobs import check_deadline_reminders
from accounts.models import User
from datetime import timedelta, datetime
import time

class Command(BaseCommand):
    help = 'Test 1-hour notification'

    def handle(self, *args, **options):
        self.stdout.write("Setting up test...")
        
        # 1. Setup User and Task
        user, _ = User.objects.get_or_create(username='test_1h_user', email='test_1h@example.com')
        # Set timezone if needed, else UTC default
        
        # 2. Create Task with deadline in 60 minutes
        # Window is [now+50m, now+70m], so 60m is perfect.
        now = timezone.now()
        deadline = now + timedelta(minutes=60)
        
        task = Task.objects.create(
            user=user,
            project_name="Test 1h Notification Project",
            deadline_date=deadline.date(),
            deadline_time=deadline.time(),
            status='ACTIVE'
        )
        
        self.stdout.write(f"Created task {task.id} with deadline {deadline}")

        # 3. Verify no notification yet
        if task.notified_1h:
             self.stderr.write("ERROR: notified_1h should be False initially")
             return

        # 4. Run Scanner
        self.stdout.write("Running check_deadline_reminders...")
        check_deadline_reminders()

        # 5. Refresh and Check
        task.refresh_from_db()
        if task.notified_1h:
            self.stdout.write(self.style.SUCCESS("SUCCESS: notified_1h is now True!"))
        else:
            self.stderr.write(self.style.ERROR("FAILURE: notified_1h is still False!"))
            
        # Clean up
        task.delete()
        # user.delete() # Keep user for potential re-runs
