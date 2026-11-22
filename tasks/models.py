from django.db import models
from accounts.models import User

class Task(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('DRAFT', 'Draft'),
        ('COMPLETED', 'Completed'),
        ('DELETED', 'Deleted'),
        ('UNCOMPLETED', 'Uncompleted'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks')
    project_name = models.CharField(max_length=255) 
    deadline_date = models.DateField(null=True, blank=True)
    deadline_time = models.TimeField(null=True, blank=True)
    project_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    previous_status = models.CharField(max_length=20, choices=STATUS_CHOICES, blank=True, null=True)
    userId = models.IntegerField(default=1)
    
    # Notification flags
    notified_3d = models.BooleanField(default=False)
    notified_24h = models.BooleanField(default=False)
    notified_overdue_24h = models.BooleanField(default=False)
    notified_1h = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'userId')

    def save(self, *args, **kwargs):
        if not self.pk: # Only on creation
            max_id = Task.objects.filter(user=self.user).aggregate(models.Max('userId'))['userId__max']
            self.userId = (max_id or 0) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project_name} ({self.status})"

from django.core.validators import FileExtensionValidator

class TaskFile(models.Model):
    task = models.ForeignKey(Task, related_name='files', on_delete=models.CASCADE)
    file = models.FileField(
        upload_to='task_files/',
        validators=[FileExtensionValidator(['pdf', 'png', 'jpg', 'jpeg', 'docx', 'pptx'])]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"File for {self.task.project_name}"

class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action}"

class TaskNotification(models.Model):
    NOTIFICATION_TYPES = [
        ('3d', '3 Days Before'),
        ('24h', '24 Hours Before'),
        ('1h', '1 Hour Before'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='notifications')
    notify_at = models.DateTimeField(db_index=True)
    type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES)
    sent = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} for {self.task.project_name} at {self.notify_at}"

class ScheduledTask(models.Model):
    name = models.CharField(max_length=255, unique=True)
    next_run_at = models.DateTimeField(db_index=True)
    interval_seconds = models.IntegerField(default=3600)  # Default 1 hour
    is_running = models.BooleanField(default=False)
    last_run_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} (Next: {self.next_run_at})"
