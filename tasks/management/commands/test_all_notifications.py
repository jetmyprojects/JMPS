from django.core.management.base import BaseCommand
from django.utils import timezone
from tasks.models import Task
from tasks.scheduler.jobs import check_deadline_reminders
from accounts.models import User
from datetime import timedelta

class Command(BaseCommand):
    help = 'Test all deadline notifications (1h, 24h, 3d)'

    def handle(self, *args, **options):
        self.stdout.write("Setting up comprehensive test...")
        
        # 1. Setup User
        user, _ = User.objects.get_or_create(username='test_notif_user', email='test_notif@example.com')
        
        # 2. Setup Tasks
        now = timezone.now()
        
        # Task 1: 1 Hour (Deadline in 60 mins)
        t1 = Task.objects.create(
            user=user, project_name="T_1H",
            deadline_date=(now + timedelta(minutes=60)).date(),
            deadline_time=(now + timedelta(minutes=60)).time(),
            status='ACTIVE'
        )

        # Task 2: 24 Hours (Deadline in 24h)
        # Window [23h, 25h], so 24h is perfect
        t2 = Task.objects.create(
            user=user, project_name="T_24H",
            deadline_date=(now + timedelta(hours=24)).date(),
            deadline_time=(now + timedelta(hours=24)).time(),
            status='ACTIVE'
        )

        # Task 3: 3 Days (Deadline in 3d)
        # Window [2d 23h, 3d 1h], so 3d is perfect
        t3 = Task.objects.create(
            user=user, project_name="T_3D",
            deadline_date=(now + timedelta(days=3)).date(),
            deadline_time=(now + timedelta(days=3)).time(),
            status='ACTIVE'
        )

        self.stdout.write(f"Created tasks: {t1.id} (1h), {t2.id} (24h), {t3.id} (3d)")

        # 3. Run Scanner
        self.stdout.write("Running check_deadline_reminders...")
        check_deadline_reminders()

        # 4. Verify
        t1.refresh_from_db()
        t2.refresh_from_db()
        t3.refresh_from_db()

        errors = 0
        
        with open('test_results.txt', 'w') as f:
            if t1.notified_1h:
                f.write("1H Notification Sent\n")
            else:
                f.write("1H Notification FAILED\n")
                errors += 1

            if t2.notified_24h:
                f.write("24H Notification Sent\n")
            else:
                f.write("24H Notification FAILED\n")
                errors += 1

            if t3.notified_3d:
                f.write("3D Notification Sent\n")
            else:
                f.write("3D Notification FAILED\n")
                errors += 1
            
            if errors == 0:
                f.write("ALL TESTS PASSED\n")
            else:
                f.write(f"{errors} TESTS FAILED\n")
