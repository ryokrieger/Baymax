from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Django built-in admin (superuser only — separate from Baymax Admin IT panel)
    path('django-admin/', admin.site.urls),

    # Google OAuth routes provided by django-allauth
    # Handles: /accounts/google/login/, /accounts/google/login/callback/, etc.
    path('accounts/', include('allauth.urls')),

    # All Baymax application routes (landing, login, register, dashboards, etc.)
    path('', include('core.urls')),
]