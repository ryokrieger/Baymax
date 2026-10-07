"""
Baymax — Django settings.

Everything environment-specific comes from environment variables
(loaded from app/.env locally; set in the Vercel dashboard in production).
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # = app/

load_dotenv(BASE_DIR / '.env')

# ── Security ─────────────────────────────────────────────────────────
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        # Local convenience only. Never reachable when DEBUG is False.
        SECRET_KEY = 'insecure-local-development-key-change-me'
    else:
        raise ImproperlyConfigured(
            'SECRET_KEY environment variable is required when DEBUG is False.'
        )

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
_extra = os.environ.get('ALLOWED_HOSTS', '')
if _extra:
    ALLOWED_HOSTS += [h.strip() for h in _extra.split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
]
_extra_csrf = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS += [o.strip() for o in _extra_csrf.split(',') if o.strip()]

# ── Applications ─────────────────────────────────────────────────────
# django.contrib.admin is deliberately absent: Baymax has its own Admin IT
# portal under /admin/, and no Django models to administer.
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    'core',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # must be second
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ── Database ─────────────────────────────────────────────────────────
# Django itself only uses this for its own tables (sessions, sites,
# allauth). All Baymax data goes through core/db.py with raw psycopg2.
# DATABASE_URL (Neon) wins; otherwise the DB_* values are used.
_local_db_url = 'postgresql://{user}:{password}@{host}:{port}/{name}'.format(
    user=quote_plus(os.environ.get('DB_USER', 'postgres')),
    password=quote_plus(os.environ.get('DB_PASSWORD', '')),
    host=os.environ.get('DB_HOST', 'localhost'),
    port=os.environ.get('DB_PORT', '5432'),
    name=os.environ.get('DB_NAME', 'baymax'),
)
DATABASES = {'default': dj_database_url.config(default=_local_db_url)}

# ── Sessions & cache ─────────────────────────────────────────────────
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True

# Used by @rate_limit (Sprint 1). Local-memory is fine for development;
# it is replaced by a shared database cache in Sprint 7 for Vercel.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'baymax-default',
    }
}

# ── Authentication (Google OAuth via django-allauth) ─────────────────
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/'  # Sprint 1 points this at the Google profile step

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        # Credentials come from .env, so no SocialApp row is needed.
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret':    os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            'key':       '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    }
}

# ── Static files (WhiteNoise) ────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ── Messages ─────────────────────────────────────────────────────────
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG:   'debug',
    message_constants.INFO:    'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR:   'error',
}

# ── Email (Gmail SMTP) ───────────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT          = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS       = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# ── Groq LLM ─────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL   = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_TIMEOUT = int(os.environ.get('GROQ_TIMEOUT', '30'))

# ── ML artifacts ─────────────────────────────────────────────────────
# Copies live inside app/ so they are deployed to Vercel (its root is app/).
SVM_PATH    = os.environ.get('SVM_PATH',    str(BASE_DIR / 'ml_artifacts' / 'svm.pkl'))
SCALER_PATH = os.environ.get('SCALER_PATH', str(BASE_DIR / 'ml_artifacts' / 'scaler.pkl'))

# ── Production hardening ─────────────────────────────────────────────
if not DEBUG:
    SESSION_COOKIE_SECURE   = True
    CSRF_COOKIE_SECURE      = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # SECURE_SSL_REDIRECT must stay False — Vercel terminates SSL at the edge.

# ── Misc ─────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
USE_TZ = False  # the schema uses naive TIMESTAMP columns
TIME_ZONE = 'Asia/Dhaka'