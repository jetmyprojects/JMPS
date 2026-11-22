import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-falback-change-in-prod")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Hosts: Vercel + custom domain by default; extend via ALLOWED_HOSTS env
# (comma-separated) e.g. "api.example.com,staging.example.com".
ALLOWED_HOSTS = ['.vercel.app', 'localhost', '127.0.0.1', 'jetmyprojects.com', 'www.jetmyprojects.com']
_extra_hosts = os.getenv('ALLOWED_HOSTS', '')
if _extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(',') if h.strip()]


# CORS & Security
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "https://www.jetmyprojects.com",
    "https://jetmyprojects.com",
]
CSRF_TRUSTED_ORIGINS = [
    "https://*.vercel.app",
    "https://www.jetmyprojects.com",
    "https://jetmyprojects.com",
]
# Extend CSRF/CORS from env (comma-separated full origins, incl. scheme).
_extra_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _extra_csrf.split(',') if o.strip()]
_extra_cors = os.getenv('CORS_ALLOWED_ORIGINS', '')
if _extra_cors:
    CORS_ALLOWED_ORIGINS += [o.strip() for o in _extra_cors.split(',') if o.strip()]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'accounts',
    'tasks',
    'subscriptions',
    'storage',
    'payments',
    'adminpanel',
    'drf_yasg',
    'django_crontab',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'accounts.authentication.CookieJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_COOKIE': 'access_token',
    'AUTH_COOKIE_REFRESH': 'refresh_token',
    'AUTH_COOKIE_DOMAIN': None,
    'AUTH_COOKIE_SECURE': os.getenv('AUTH_COOKIE_SECURE', 'True') == 'True', # Configurable for local dev (http) vs prod (https)
    'AUTH_COOKIE_HTTP_ONLY': True,
    'AUTH_COOKIE_PATH': '/',
    'AUTH_COOKIE_SAMESITE': 'Lax',
}

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'fe_login'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.middleware.SecurityHeadersMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', 
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'tasks.middleware.NotificationTriggerMiddleware',
    'tasks.middleware.TaskSchedulerMiddleware',
    'config.middleware.JWTAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'middleware.FreeAccessMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'tasks.context_processors.user_context',  # Custom context processor
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

# Prefer DATABASE_URL (set by Vercel's Neon/Postgres integration); fall back
# to discrete DB_* env vars for local/other environments.
import urllib.parse

_DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL')
if _DATABASE_URL:
    _u = urllib.parse.urlparse(_DATABASE_URL)
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _u.path.lstrip('/'),
            'USER': urllib.parse.unquote(_u.username or ''),
            'PASSWORD': urllib.parse.unquote(_u.password or ''),
            'HOST': _u.hostname or '',
            'PORT': str(_u.port or '5432'),
            'OPTIONS': {'sslmode': 'require'},
            'CONN_MAX_AGE': 0,  # serverless: don't hold connections open
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'todo_app_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# SMTP Configuration for SMTP2GO
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'mail.smtp2go.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 443))
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
EMAIL_TIMEOUT = 10

DEFAULT_FROM_EMAIL = 'JetMyProjects <no-reply@jetmyprojects.com>'
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'contact@jetmyprojects.com')

# Google reCAPTCHA Configuration
# Usage: Always use Production Keys (Localhost must be whitelisted in Google Admin Console)
RECAPTCHA_PUBLIC_KEY = os.getenv("RECAPTCHA_PUBLIC_KEY", "6Ld4BV0sAAAAAE3tCfTiaor2hu9_fpKyUG-j4qZ2") 
RECAPTCHA_PRIVATE_KEY = os.getenv("RECAPTCHA_PRIVATE_KEY", "6Ld4BV0sAAAAAFXj8EYSi4Sx-x50zLWAMec4ED9O") 

# Stripe Configuration
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# Security Production Settings
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'errors.log',
        },
        'webhook_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'webhook_debug.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'subscriptions': {
            'handlers': ['webhook_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'ERROR',
    },
}

FRONTEND_DOMAIN = "https://www.jetmyprojects.com"



CRONJOBS = [
    ('*/10 * * * *', 'django.core.management.call_command', ['process_deadline_notifications']),
]



