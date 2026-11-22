from django.core.management.base import BaseCommand
from tasks.models import Task
from tasks.signals import schedule_task_notifications

class Command(BaseCommand):
    help = 'Backfill TaskNotification records for existing active tasks'

    def handle(self, *args, **options):
        active_tasks = Task.objects.filter(status='ACTIVE')
        count = 0
        for task in active_tasks:
            # We can leverage the existing signal logic function directly
            # simulating a 'save' event by passing the task instance
            schedule_task_notifications(sender=Task, instance=task, created=False)
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f'Successfully backfilled notifications for {count} tasks.'))
