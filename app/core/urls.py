from django.urls import path

from core.views import auth

urlpatterns = [
    path('', auth.landing_view, name='landing'),

    path('register/', auth.register_view, name='register'),
    path('register/verify/', auth.register_verify_view, name='register_verify'),
    path('register/google/', auth.register_google_view, name='register_google'),
    path('google/callback/', auth.google_callback_view, name='google_callback'),
]