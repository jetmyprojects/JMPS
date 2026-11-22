class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Content-Security-Policy
        # Adjust sources as needed based on used CDNs
        csp = (
    "default-src 'self'; "

    "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
    "https://www.gstatic.com "
    "https://www.recaptcha.net "
    "https://cdn.jsdelivr.net "
    "https://cdnjs.cloudflare.com "
    "https://www.googletagmanager.com "
    "https://cdn.tailwindcss.com "
    "https://static.cloudflareinsights.com; "

    "style-src 'self' 'unsafe-inline' "
    "https://fonts.googleapis.com "
    "https://cdn.jsdelivr.net "
    "https://cdnjs.cloudflare.com; "

    "img-src 'self' data: "
    "https://www.google-analytics.com "
    "https://www.googletagmanager.com "
    "https://cdnjs.cloudflare.com "
    "https://www.gstatic.com; "

    "font-src 'self' "
    "https://fonts.gstatic.com "
    "https://cdnjs.cloudflare.com; "

    "frame-src 'self' "
    "https://www.google.com "
    "https://www.recaptcha.net "
    "https://www.googletagmanager.com; "

    "connect-src 'self' "
    "https://www.google.com "
    "https://www.gstatic.com "
    "https://www.google-analytics.com "
    "https://stats.g.doubleclick.net "
    "https://www.recaptcha.net "
    "https://www.googletagmanager.com "
    "https://cdn.jsdelivr.net "
    "https://cdnjs.cloudflare.com "
    "https://static.cloudflareinsights.com;"
)

        response['Content-Security-Policy'] = csp
        
        # Permissions-Policy
        response['Permissions-Policy'] = "geolocation=(), microphone=(), camera=()"
        
        return response

class JWTAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow standard auth to work first
        if not request.user.is_authenticated:
            from django.conf import settings
            from rest_framework_simplejwt.tokens import AccessToken
            from accounts.models import User
            from rest_framework_simplejwt.exceptions import TokenError
            
            cookie_name = settings.SIMPLE_JWT.get('AUTH_COOKIE', 'access_token')
            token = request.COOKIES.get(cookie_name)
            
            if token:
                try:
                    # Validate token
                    access_token = AccessToken(token)
                    # Get user
                    user_id = access_token.get('user_id')
                    user = User.objects.get(id=user_id)
                    request.user = user
                except (TokenError, User.DoesNotExist, Exception):
                    # Invalid token or user, leave as Anonymous
                    pass
        
        return self.get_response(request)
