from django.urls import path

from core.views import auth

urlpatterns = [
    path('', auth.landing_view, name='landing'),
]