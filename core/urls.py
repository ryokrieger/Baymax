from django.urls import path
from core import views

urlpatterns = [

    # Landing: "Who are you?" role-selector
    path('',
         views.landing,
         name='landing'),

    # Login — single template, role passed via ?role= query param
    path('login/',
         views.login_view,
         name='login'),

    # Student self-registration (manual)
    path('register/',
         views.register,
         name='register'),

    # Google Sign-In registration completion (extra fields)
    path('register/google/',
         views.register_google,
         name='register_google'),

    # Logout — clears session, redirects to landing
    path('logout/',
         views.logout_view,
         name='logout'),

    # GET  — show next unanswered question
    # POST — save answer; after 26th run ML & redirect to result
    path('chatbot/',
         views.chatbot,
         name='chatbot'),

    # GET — show classification result + triage outcome
    path('chatbot/result/',
         views.chatbot_result,
         name='chatbot_result'),

    # POST — run Triage Agent for Critical students
    path('chatbot/request-professional/',
         views.chatbot_request_professional,
         name='chatbot_request_professional'),

    # Dashboard — three-card hub page
    path('student/dashboard/',
         views.student_dashboard,
         name='student_dashboard'),

    # Mental Health Status — classification + 26 responses + top symptoms
    path('student/status/',
         views.student_status,
         name='student_status'),

    # Request Mental Health Help — professional list + appointment buttons
    path('student/help/',
         views.student_help,
         name='student_help'),

    # POST — submit a new help request to a specific professional
    path('student/help/request/<int:professional_id>/',
         views.student_help_request,
         name='student_help_request'),

    # POST — cancel a pending appointment request
    path('student/help/cancel-request/<int:appointment_id>/',
         views.student_help_cancel,
         name='student_help_cancel'),

    # Mental Health Events — list + RSVP
    path('student/events/',
         views.student_events,
         name='student_events'),

    # POST — RSVP to an event
    path('student/events/rsvp/<int:event_id>/',
         views.student_events_rsvp,
         name='student_events_rsvp'),

    # POST — cancel an RSVP
    path('student/events/cancel-rsvp/<int:event_id>/',
         views.student_events_cancel_rsvp,
         name='student_events_cancel_rsvp'),

]