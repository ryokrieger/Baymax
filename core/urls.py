from django.urls import path
from core import views

urlpatterns = [

    # Landing: "Who are you?" role-selector
    path('', views.landing, name='landing'),

    # Login — single template, role passed via ?role= query param
    path('login/', views.login_view, name='login'),

    # Student self-registration (manual)
    path('register/', views.register, name='register'),

    # Google Sign-In registration completion (extra fields)
    path('register/google/', views.register_google, name='register_google'),

    # Logout — clears session, redirects to landing
    path('logout/', views.logout_view, name='logout'),

    # GET  — show next unanswered question
    # POST — save submitted answer; after 26th run ML & redirect to result
    path('chatbot/', views.chatbot, name='chatbot'),

    # GET — show classification result + triage outcome
    path('chatbot/result/', views.chatbot_result, name='chatbot_result'),

    # POST — run Triage Agent for Critical students
    path('chatbot/request-professional/', views.chatbot_request_professional,
         name='chatbot_request_professional'),
         
]