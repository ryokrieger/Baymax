from django.urls import path
from core import views

urlpatterns = [

 # Landing page: "Who are you?" role-selector
    path('', views.landing, name='landing'),

    # Login — single template, role passed via ?role=<role> query param
    path('login/', views.login_view, name='login'),

    # Student self-registration (manual: name, student ID, dept, email, password)
    path('register/', views.register, name='register'),

    # Google Sign-In registration completion
    # (extra fields: student ID, department, password)
    path('register/google/', views.register_google, name='register_google'),

    # Logout — clears session, redirects to landing
    path('logout/', views.logout_view, name='logout'),

]