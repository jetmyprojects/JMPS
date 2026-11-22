from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
import threading
import secrets
import logging
import os
from email.mime.image import MIMEImage
from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)



def generate_otp():
    """
    Generates a cryptographically secure 6-digit OTP.
    Range: 100000 to 999999.
    """
    return str(secrets.randbelow(900000) + 100000)

class EmailThread(threading.Thread):
    def __init__(self, subject, html_content, recipient_list, from_email=None):
        self.subject = subject
        self.recipient_list = recipient_list
        self.html_content = html_content
        self.from_email = from_email or settings.DEFAULT_FROM_EMAIL
        threading.Thread.__init__(self)

    def run(self):
        try:
            msg = EmailMultiAlternatives(
                subject=self.subject,
                body='',  # Plain text body
                from_email=self.from_email,
                to=self.recipient_list
            )
            msg.attach_alternative(self.html_content, "text/html")
            


            msg.send(fail_silently=False)
            logger.info(f"Email sent to {self.recipient_list}")
        except Exception as e:
            logger.error(f"Error sending email to {self.recipient_list}: {e}")

def send_html_otp_email(to_email, otp, first_name=None):
    """
    Sends an OTP email using the configured Django Email Backend.
    """
    subject = 'Your Verification Code'
    year = 2026
    domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
    logo_url = f"{domain}/static/ImageLogox.png"

    context = {
        'user_name': first_name or 'User',
        'otp': otp,
        'logo_url': logo_url,
        'year': year,
    }
    
    html_content = render_to_string('accounts/emails/email_passcode_v2.html', context)
    
    EmailThread(subject, html_content, [to_email]).start()

def send_welcome_email(to_email, first_name=None):
    """
    Sends a welcome email using the configured Django Email Backend.
    """
    subject = 'Welcome to JetMyProjects!'
    
    domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
    dashboard_url = f"{domain}/dashboard/"
    
    logo_url = f"{domain}/static/ImageLogox.png"
    year = 2026
    
    context = {
        'user_name': first_name or 'User',
        'dashboard_url': dashboard_url,
        'logo_url': logo_url,
        'year': year,
    }
    
    html_content = render_to_string('accounts/emails/email_welcome_v2.html', context)
    
    EmailThread(subject, html_content, [to_email]).start()

def send_forgot_password_email(to_email, otp, first_name=None):
    """
    Sends a forgot password email using the configured Django Email Backend.
    """
    subject = 'Reset Your Password'
    year = 2026
    domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
    logo_url = f"{domain}/static/ImageLogox.png"

    context = {
        'user_name': first_name or 'User',
        'otp': otp,
        'logo_url': logo_url,
        'year': year,
    }
    
    html_content = render_to_string('accounts/emails/email_forgot_password_v2.html', context)
    
    EmailThread(subject, html_content, [to_email]).start()

def send_profile_update_email(to_email, otp, first_name=None):
    """
    Sends a profile update verification email using the configured Django Email Backend.
    """
    subject = 'Verify Profile Update'
    year = 2026
    domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
    logo_url = f"{domain}/static/ImageLogox.png"

    context = {
        'user_name': first_name or 'User',
        'otp': otp,
        'logo_url': logo_url,
        'year': year,
    }
    
    html_content = render_to_string('accounts/emails/email_profile_update.html', context)
    
    EmailThread(subject, html_content, [to_email]).start()
