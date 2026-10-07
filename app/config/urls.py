from django.urls import include, path

urlpatterns = [
    # Google OAuth routes provided by django-allauth
    # (/accounts/google/login/, /accounts/google/login/callback/, ...)
    path('accounts/', include('allauth.urls')),

    # All Baymax routes: landing, auth, and the four role portals.
    path('', include('core.urls')),
]