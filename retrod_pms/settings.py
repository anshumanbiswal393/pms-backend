import os
from pathlib import Path
from datetime import timedelta
import environ

# Initialize environ
env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, 'django-insecure-vp!0!ob!0(z@%=5y*h5f_xscvp3ky=%v^=#o&7io7r*5)hr0be'),
    ALLOWED_HOSTS=(list, ['*']),
    DATABASE_URL=(str, ''),
)

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Read .env file if it exists
env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env('SECRET_KEY', default='django-insecure-retrod-pms-secret-key-production-dev')
DEBUG = env.bool('DEBUG', default=True)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['*'])
RAZORPAY_KEY_ID = env('RAZORPAY_KEY_ID', default='')
RAZORPAY_KEY_SECRET = env('RAZORPAY_KEY_SECRET', default='')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party packages
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
    
    # Local apps
    'apps.core.common',
    'apps.core.tenants',
    'apps.core.rbac',
    'apps.core.accounts',
    'apps.core.audit',
    'apps.features.inventory',
    'apps.features.availability',
    'apps.features.rates',
    'apps.features.crm',
    'apps.core.reference',
    'apps.features.reservations',
    'apps.core.subscriptions',
    'apps.features.assets',
    'apps.features.maintenance',
    'apps.core.compliance',
    'apps.core.monitoring',
    'apps.features.properties',
    'apps.features.linen',
    'apps.features.lost_found',
    'apps.features.front_office',
    'apps.features.housekeeping',
    'apps.features.billing',
    'apps.features.b2b',
    
    # AI Chatbot Apps (Product 2)
    'apps.chatbot.ai_engine',
    'apps.chatbot.core',
    'apps.chatbot.integrations',

    # Booking Engine (Product 3)
    'apps.booking',
]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # Custom Middlewares
    'apps.core.tenants.middleware.TenantResolutionMiddleware',
    'apps.core.subscriptions.middleware.ProductAccessMiddleware',
    'apps.core.accounts.middleware.AccountLockoutMiddleware',
    'apps.core.accounts.middleware.IPWhitelistMiddleware',
    'apps.core.audit.middleware.AuditMiddleware',
    'apps.core.monitoring.middleware.ApplicationLoggingMiddleware',
]

ROOT_URLCONF = 'retrod_pms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'retrod_pms.wsgi.application'

import sys

# Database configuration (psycopg2 for postgres, sqlite as local fallback)
if env('DATABASE_URL'):
    DATABASES = {
        'default': env.db()
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }



# Custom Auth Model
AUTH_USER_MODEL = 'accounts.AppUser'

# Password hashing
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# Password validators
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Localization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Config
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = env.bool('CORS_ALLOW_ALL_ORIGINS', default=False)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://144.31.146.64:3000",
    "https://app.dev.retrod.in",
    "https://app.dev.retrod.in:8443",
    "http://app.dev.retrod.in",
    "http://app.dev.retrod.in:8443",
])
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https?://.*\.retrod\.in(:\d+)?$",
    r"^https?://localhost(:\d+)?$",
    r"^https?://127\.0\.0\.1(:\d+)?$",
]

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    "https://app.dev.retrod.in",
    "https://app.dev.retrod.in:8443",
    "http://app.dev.retrod.in",
    "http://app.dev.retrod.in:8443",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://*.retrod.in",
    "http://*.retrod.in",
])

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant-subdomain",
    "x-property-id",
    "x-hotel-slug",
    "x-hotel-subdomain",
    "x-tenant-slug",
]

# SSL & Proxy headers when behind Nginx/Cloudflare/Reverse Proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True


# Django REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'apps.core.common.pagination.OptionalPageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/minute',
        'user': '1000/minute'
    }
}

# JWT Token configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,  # Handled manually in our auth service to audit appropriately
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Swagger/OpenAPI settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'Retrod PMS API',
    'DESCRIPTION': 'API documentation for Retrod Property Management System foundation layer.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# SMTP Email Settings
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtppro.zoho.in')
EMAIL_PORT = env('EMAIL_PORT', cast=int, default=587)
EMAIL_USE_TLS = env('EMAIL_USE_TLS', cast=bool, default=True)
EMAIL_USE_SSL = env('EMAIL_USE_SSL', cast=bool, default=False)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@retrod.in')

# OTP & Domain Configuration
OTP_PROVIDER = env('OTP_PROVIDER', default='email')
APP_BASE_URL = env('APP_BASE_URL', default='https://app.dev.retrod.in:8443')

# Caching with Redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': env('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'IGNORE_EXCEPTIONS': True, # Ignore exceptions when Redis is down
            'CONNECTION_POOL_KWARGS': {'max_connections': 100},
            'SOCKET_CONNECT_TIMEOUT': 0.05, # Fail fast in 50ms if Redis is down
            'SOCKET_TIMEOUT': 0.05,
        }
    }
}

# Celery & Async Message Broker
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6379/1')
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=None)
CELERY_TASK_IGNORE_RESULT = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Structured Logging with PII Redaction Filter & Database Error Log Persistence
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'pii_masking': {
            '()': 'apps.chatbot.core.logging_filters.PIIMaskingFilter',
        }
    },
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{name}:{lineno}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'filters': ['pii_masking'],
            'formatter': 'verbose',
        },
        'db_error_log': {
            'class': 'apps.core.monitoring.handlers.DatabaseErrorLogHandler',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'db_error_log'],
        'level': 'INFO',
    },
}

# AI Chatbot & Twilio Configuration
GROQ_API_KEY = env('GROQ_API_KEY', default='')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')
TWILIO_ACCOUNT_SID = env('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env('TWILIO_AUTH_TOKEN', default='')
TWILIO_WHATSAPP_FROM = env('TWILIO_WHATSAPP_FROM', default='')
TWILIO_SKIP_SIGNATURE_VALIDATION = env.bool('TWILIO_SKIP_SIGNATURE_VALIDATION', default=DEBUG)

TWILIO_CONTENT_SID = env('TWILIO_CONTENT_SID', default='HX25c95ef5a1120456a63cc31ec212edd5')
TWILIO_CONTENT_SID_FRONTDESK = env('TWILIO_CONTENT_SID_FRONTDESK', default='HXb3a3090c3ec58449bb96cb67db7e658a')
TWILIO_CONTENT_SID_ANALYTICS = env('TWILIO_CONTENT_SID_ANALYTICS', default='HX544516ed67845dc3656a028985b03da2')
TWILIO_CONTENT_SID_OPERATIONS = env('TWILIO_CONTENT_SID_OPERATIONS', default='HX25beb28d0eac668d4c637a37b8b0c117')
TWILIO_CONTENT_SID_SECURITY = env('TWILIO_CONTENT_SID_SECURITY', default='HX459d842b55f9a19a2f58fdd8f583b262')


