import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# ─────────────────────────────────────────────
#  SECURITY
# ─────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = True  # Set to False in production

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']

# ─────────────────────────────────────────────
#  INSTALLED APPS
# ─────────────────────────────────────────────
INSTALLED_APPS = [
    # Django built-ins
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Google OAuth via django-allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Baymax app
    'core',
]

# Required by django.contrib.sites and allauth
SITE_ID = 1

# ─────────────────────────────────────────────
#  MIDDLEWARE
# ─────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

# ─────────────────────────────────────────────
#  URL CONFIGURATION
# ─────────────────────────────────────────────
ROOT_URLCONF = 'config.urls'

# ─────────────────────────────────────────────
#  TEMPLATES
# ─────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Look for templates inside core/templates/
        'DIRS': [BASE_DIR / 'core' / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'

# ─────────────────────────────────────────────
#  DATABASE — PostgreSQL via psycopg2
# ─────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.postgresql_psycopg2',
        'NAME':     os.environ.get('DB_NAME'),
        'USER':     os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST':     os.environ.get('DB_HOST'),
        'PORT':     os.environ.get('DB_PORT'),
    }
}

# ─────────────────────────────────────────────
#  AUTHENTICATION BACKENDS
#  Needed so allauth can handle Google OAuth
#  alongside our custom session-based auth.
# ─────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    # Default Django backend (for Django admin)
    'django.contrib.auth.backends.ModelBackend',
    # allauth backend (for Google Sign-In)
    'allauth.account.auth_backends.AuthenticationBackend',
]

# ─────────────────────────────────────────────
#  SESSIONS
#  Store sessions in the database (default).
#  Session data holds user_id and role.
# ─────────────────────────────────────────────
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400          # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True

# ─────────────────────────────────────────────
#  STATIC FILES (CSS, JS)
# ─────────────────────────────────────────────
STATIC_URL = '/static/'

# Django looks for static files in these directories
STATICFILES_DIRS = [
    BASE_DIR / 'core' / 'static',
]

# Where collectstatic deposits files for production
STATIC_ROOT = BASE_DIR / 'staticfiles'

# ─────────────────────────────────────────────
#  ML MODEL PATHS
#  Stored in .env so paths work on any machine.
# ─────────────────────────────────────────────
SVM_PATH    = os.environ.get('SVM_PATH',    str(BASE_DIR / 'models'   / 'svm.pkl'))
SCALER_PATH = os.environ.get('SCALER_PATH', str(BASE_DIR / 'features' / 'scaler.pkl'))

# ─────────────────────────────────────────────
#  ALLAUTH CONFIGURATION
# ─────────────────────────────────────────────

# Where allauth redirects after a successful OAuth login.
# but this acts as the fallback.
LOGIN_REDIRECT_URL = '/register/google/'

# Allow GET requests to initiate social login (required for button links)
SOCIALACCOUNT_LOGIN_ON_GET = True

# Where allauth redirects if login is required.
LOGIN_URL = '/'

# allauth account settings
ACCOUNT_EMAIL_REQUIRED        = True
ACCOUNT_USERNAME_REQUIRED     = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_VERIFICATION    = 'none'

# Google OAuth 2.0 — APP block embeds credentials directly from .env
# so no SocialApp database record needs to be created manually.
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'secret':    os.environ.get('GOOGLE_CLIENT_SECRET', ''),
            'key':       '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'OAUTH_PKCE_ENABLED': True,
    }
}

# Auto-connect social accounts to existing email addresses
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

# ─────────────────────────────────────────────
#  MESSAGES FRAMEWORK
#  Used for flash messages (success / error)
# ─────────────────────────────────────────────
from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.DEBUG:   'debug',
    message_constants.INFO:    'info',
    message_constants.SUCCESS: 'success',
    message_constants.WARNING: 'warning',
    message_constants.ERROR:   'error',
}

# ─────────────────────────────────────────────
#  DEFAULT AUTO FIELD
# ─────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─────────────────────────────────────────────
#  EMAIL — SMTP
#  Used to send congratulatory emails to newly
#  registered professionals, authority, and
#  admin IT accounts.
# ─────────────────────────────────────────────
EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST          = os.environ.get('EMAIL_HOST')
EMAIL_PORT          = int(os.environ.get('EMAIL_PORT'))
EMAIL_USE_TLS       = os.environ.get('EMAIL_USE_TLS') == 'True'
EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL  = os.environ.get('DEFAULT_FROM_EMAIL')

# ─────────────────────────────────────────────
#  CSRF
# ─────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
]