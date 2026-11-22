from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from tasks.models import Task
from django.conf import settings
import sys

class Command(BaseCommand):
    help = 'Send a test email to debug delivery issues'

    def handle(self, *args, **options):
        task_id = 228
        try:
            task = Task.objects.get(id=task_id)
            email = task.user.email
            self.stdout.write(f"Found Task {task_id}. User email: {email}")
        except Task.DoesNotExist:
            self.stdout.write(f"Task {task_id} not found. using default.")
            email = 'contact@jetmyprojects.com'

        self.stdout.write(f"Attempting to send email to {email}...")
        self.stdout.write(f"Backend: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
        self.stdout.write(f"User: {settings.EMAIL_HOST_USER}")
        
        try:
            send_mail(
                subject='Test Email from JetMyProjects Debugger',
                message='This is a test email to verify SMTP configuration.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            self.stdout.write("Email sent successfully (accepted by server).")
        except Exception as e:
            self.stdout.write(f"FAILED to send email: {e}")
            import traceback
            traceback.print_exc()
