from django.db import models

class ContactInquiry(models.Model):
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('REPLIED', 'Replied'),
        ('ARCHIVED', 'Archived'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    company = models.CharField(max_length=255)
    team_size = models.CharField(max_length=50)
    country = models.CharField(max_length=100)
    industry = models.CharField(max_length=100, blank=True, null=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NEW')
    created_at = models.DateTimeField(auto_now_add=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.company}"

    
