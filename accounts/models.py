from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=255, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.IntegerField(default=0)
    organisation_name = models.CharField(max_length=255, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    pending_discount_code = models.CharField(max_length=50, blank=True, null=True, help_text="Store discount code for future checkout if abandoned")
    timezone = models.CharField(max_length=50, default='UTC', help_text="User's timezone (e.g. 'Asia/Kolkata')")

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email
