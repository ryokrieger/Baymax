from django.urls import path

from core import views

# Single placeholder route to verify base.html renders.
urlpatterns = [
    path('', views.home, name='home'),
]