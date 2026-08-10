import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


def env(key: str) -> str:
    """Fetch a required environment variable or fail fast with a clear error."""
    value = os.environ.get(key)
    if value is None or value == '':
        raise ImproperlyConfigured(
            f"Required environment variable '{key}' is not set. "
            f"Check app/.env (local) or your deployment's environment variables."
        )
    return value


def env_optional(key: str) -> str:
    """Fetch an environment variable that is allowed to be empty (e.g. CSRF_TRUSTED_ORIGINS in local dev)."""
    return os.environ.get(key, '')


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG') == 'True'

ALLOWED_HOSTS = [h.strip() for h in env('ALLOWED_HOSTS').split(',') if h.strip()]

CSRF_TRUSTED_ORIGINS = [o.strip() for o in env_optional('CSRF_TRUSTED_ORIGINS').split(',') if o.strip()]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
SITE_ID = 1

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
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

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # must stay second
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

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

# ---------------------------------------------------------------------------
# Database — Neon Postgres. Raw psycopg2 is used for all app queries
# (see core/db.py); this connection is for Django's own auth/session/admin
# tables only.
# ---------------------------------------------------------------------------

DATABASES = {
    'default': dj_database_url.parse(env('DATABASE_URL')),
}

# ---------------------------------------------------------------------------
# Security — hardened automatically whenever DEBUG is off. SECURE_SSL_REDIRECT
# stays False deliberately: Vercel terminates TLS at the edge, so redirecting
# again inside the app causes a redirect loop.
# ---------------------------------------------------------------------------

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ---------------------------------------------------------------------------
# Static files (WhiteNoise)
# ---------------------------------------------------------------------------

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ---------------------------------------------------------------------------
# Auth / allauth (Google OAuth)
# ---------------------------------------------------------------------------

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': env('GOOGLE_CLIENT_ID'),
            'secret': env('GOOGLE_CLIENT_SECRET'),
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
    },
}

# ---------------------------------------------------------------------------
# Email (core/email_utils.py handles all sending)
# ---------------------------------------------------------------------------

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = int(env('EMAIL_PORT'))
EMAIL_USE_TLS = env('EMAIL_USE_TLS') == 'True'
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

# ---------------------------------------------------------------------------
# Groq LLM (core/agents/llm_client.py — Singleton + Adapter)
# ---------------------------------------------------------------------------

GROQ_API_KEY = env('GROQ_API_KEY')
GROQ_MODEL = env('GROQ_MODEL')
GROQ_TIMEOUT = int(env('GROQ_TIMEOUT'))

# ---------------------------------------------------------------------------
# ML model artifacts — trained already; the two files this app loads at
# runtime (core/ml.py, Singleton loader) live inside app/models/.
# Paths are relative to BASE_DIR (= app/) and come entirely from .env.
# ---------------------------------------------------------------------------

SVM_PATH = str(BASE_DIR / env('SVM_PATH'))
SCALER_PATH = str(BASE_DIR / env('SCALER_PATH'))

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True