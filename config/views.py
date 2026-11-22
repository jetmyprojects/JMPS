from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
import json
from adminpanel.models import ContactInquiry

from django.contrib.staticfiles import finders
from email.mime.image import MIMEImage
import os
import requests



def index(request):
    """
    Redirects root URL traffic.
    Includes subscription status for the landing page.
    """
    context = {}
    if request.user.is_authenticated:
        from subscriptions.models import UserSubscription
        from django.utils import timezone
        
        sub = UserSubscription.objects.filter(user=request.user, is_active=True).first()
        is_premium = False
        days_left = 0
        
        if sub:
            is_premium = True
            if sub.end_date:
                delta = sub.end_date - timezone.now().date()
                days_left = max(0, delta.days)
        
        context.update({
            'is_premium': is_premium,
            'days_left': days_left
        })
    
    # Pass reCAPTCHA Key
    context['recaptcha_public_key'] = getattr(settings, 'RECAPTCHA_PUBLIC_KEY', '')
        
    return render(request, 'Landing.html', context)

@csrf_exempt
def contact_sales(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            context = {
                'first_name': data.get('firstName'),
                'last_name': data.get('lastName'),
                'email': data.get('email'),
                'phone': data.get('phone'),
                'company': data.get('company', 'N/A'),
                'team_size': data.get('teamSize', 'N/A'),
                'country': data.get('country', 'N/A'),
                'industry': data.get('industry', 'N/A'),
                'message': data.get('message'),
                'recaptcha_token': data.get('recaptchaToken')
            }

            # --- VALIDATION START ---
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            import re

            # 1. XSS Check (Strict: Reject HTML tags)
            for key, value in context.items():
                if isinstance(value, str):
                    if '<' in value or '>' in value:
                        return JsonResponse({'status': 'error', 'message': 'Invalid characters detected (HTML tags not allowed).'}, status=400)

            # 2. Email Validation
            email = context.get('email')
            if not email:
                 return JsonResponse({'status': 'error', 'message': 'Email is required.'}, status=400)
            try:
                validate_email(email)
            except ValidationError:
                return JsonResponse({'status': 'error', 'message': 'Invalid email address.'}, status=400)

            # 2.1 MX Record Check
            try:
                import dns.resolver
                domain = email.split('@')[1]
                
                # Configure resolver to be robust
                resolver = dns.resolver.Resolver()
                resolver.lifetime = 3.0 # Timeout in seconds
                resolver.nameservers = ['8.8.8.8', '8.8.4.4', '1.1.1.1'] # Use Google/Cloudflare to bypass ISP wildcards
                
                records = resolver.resolve(domain, 'MX')
                if not records:
                    raise Exception("No MX records found")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                return JsonResponse({'status': 'error', 'message': 'Invalid email domain. No mail server found.'}, status=400)
            except dns.exception.Timeout:
                 return JsonResponse({'status': 'error', 'message': 'Email domain validation timed out. Please try again or use a different email.'}, status=400)
            except ImportError:
                 # Should not happen if installed, but better to fail securely or log critical error
                 print("CRITICAL: dnspython not installed. Validation skipped.")
                 # If we want to be strict: 
                 return JsonResponse({'status': 'error', 'message': 'Server configuration error (missing DNS lib).'}, status=500)
            except Exception as e:
                print(f"DNS Check Failed: {e}")
                # Fail verification for any other DNS error to be safe
                return JsonResponse({'status': 'error', 'message': f'Invalid email domain ({str(e)}).'}, status=400)

            # 3. Phone Validation
            phone = context.get('phone', '').strip()
            if not phone:
                 return JsonResponse({'status': 'error', 'message': 'Phone number is required.'}, status=400)
            
            # Strict regex: Optional +, allowed chars digits/space/hyphen. Must end with digit.
            # Length roughly 10-15 digits.
            if not re.match(r'^\+?[0-9][0-9\- ]{8,18}[0-9]$', phone):
                 return JsonResponse({'status': 'error', 'message': 'Invalid phone number. Please use 10-15 digits.'}, status=400)
            # --- VALIDATION END ---

            # Prepare Logo URL
            domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
            context['logo_url'] = f"{domain}/static/ImageLogox.png"

            # --- reCAPTCHA Validation ---
            recaptcha_response = context.get('recaptcha_token')
            if not recaptcha_response:
                return JsonResponse({'status': 'error', 'message': 'Please complete the reCAPTCHA.'}, status=400)

            secret_key = getattr(settings, 'RECAPTCHA_PRIVATE_KEY', '')
            verify_url = 'https://www.google.com/recaptcha/api/siteverify'
            verify_data = {
                'secret': secret_key,
                'response': recaptcha_response
            }
            
            try:
                verify_req = requests.post(verify_url, data=verify_data)
                verify_json = verify_req.json()
                if not verify_json.get('success') or verify_json.get('score', 0) < 0.5:
                     return JsonResponse({'status': 'error', 'message': 'reCAPTCHA verification failed. Please try again.'}, status=400)
            except Exception as e:
                 print(f"reCAPTCHA Error: {e}")
                 # Fail open or closed? Closed for security.
                 return JsonResponse({'status': 'error', 'message': 'reCAPTCHA service error.'}, status=400)
            # ---------------------------

            # Save to Database
            ContactInquiry.objects.create(
                first_name=context['first_name'],
                last_name=context['last_name'],
                email=context['email'],
                phone=context['phone'],
                company=context['company'],
                team_size=context['team_size'],
                country=context['country'],
                industry=context['industry'],
                message=context['message']
            )
            
            # Use a default admin email if settings.ADMIN_EMAIL is not set
            admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@example.com')
            
            html_content = render_to_string('emails/EmailContactUsAdmin.html', context)
            text_content = f"New inquiry from {context['first_name']} {context['last_name']} ({context['email']}).\n\nMessage:\n{context['message']}"
            
            msg = EmailMultiAlternatives(
                subject='New Contact Sales Inquiry',
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[admin_email]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()

            # --- User Auto-Reply ---
            try:
                user_html = render_to_string('emails/ContactUsConfirmation.html', context)
                user_text = f"Hi {context['first_name']},\n\nThank you for contacting JetMyProjects. We have received your inquiry and will respond shortly.\n\nBest,\nThe JetMyProjects Team"
                
                user_msg = EmailMultiAlternatives(
                    subject='We Received Your Inquiry - JetMyProjects',
                    body=user_text,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[context['email']]
                )
                user_msg.attach_alternative(user_html, "text/html")
                user_msg.send()
            except Exception as e:
                print(f"Failed to send auto-reply: {e}") 
                # Don't fail the whole request if auto-reply fails

            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    # GET request
    return render(request, 'ContactSales.html')


def sitemap(request):
    """
    Generates a sitemap.xml for SEO.
    """
    domain = getattr(settings, 'FRONTEND_DOMAIN', 'https://www.jetmyprojects.com')
    
    # Static pages
    static_paths = [
        'index',
        'contact_sales',
        'terms',
        'privacy',
    ]
    
    urls = []
    for path_name in static_paths:
        try:
            full_url = f"{domain}{reverse(path_name)}"
            urls.append({
                'loc': full_url,
                'lastmod': timezone.now().strftime('%Y-%m-%d'),
                'changefreq': 'weekly',
                'priority': '1.0' if path_name == 'index' else '0.8'
            })
        except Exception:
            pass

    # xml_content = render_to_string('sitemap_template.xml', {'urls': urls})
    # If template doesn't exist, we construct manually to avoid creating a file if user didn't ask, 
    # but a template is cleaner. 
    # Let's actually construct it manually in the view to keep it single-file for simplicity 
    # as per my plan to avoid complex dependencies, unless I create a template.
    # Re-writing the manual generation approach below to be self-contained.
    
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    
    for url in urls:
        xml_lines.append(f"  <url>")
        xml_lines.append(f"    <loc>{url['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{url['lastmod']}</lastmod>")
        xml_lines.append(f"    <changefreq>{url['changefreq']}</changefreq>")
        xml_lines.append(f"    <priority>{url['priority']}</priority>")
        xml_lines.append(f"  </url>")
        
    xml_lines.append('</urlset>')
    
    return HttpResponse("\n".join(xml_lines), content_type="application/xml")
