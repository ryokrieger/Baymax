from django.urls import path
from core import views

urlpatterns = [

    # Authentication
    path('',
         views.landing,
         name='landing'),

    path('login/',
         views.login_view,
         name='login'),

    path('register/',
         views.register,
         name='register'),

    path('register/google/',
         views.register_google,
         name='register_google'),

    path('logout/',
         views.logout_view,
         name='logout'),

    # Chatbot & ML
    path('chatbot/',
         views.chatbot,
         name='chatbot'),

    path('chatbot/result/',
         views.chatbot_result,
         name='chatbot_result'),

    path('chatbot/request-professional/',
         views.chatbot_request_professional,
         name='chatbot_request_professional'),

    # Student Portal
    path('student/dashboard/',
         views.student_dashboard,
         name='student_dashboard'),

    path('student/status/',
         views.student_status,
         name='student_status'),

    path('student/help/',
         views.student_help,
         name='student_help'),

    path('student/help/request/<int:professional_id>/',
         views.student_help_request,
         name='student_help_request'),

    path('student/help/cancel-request/<int:appointment_id>/',
         views.student_help_cancel,
         name='student_help_cancel'),

    path('student/events/',
         views.student_events,
         name='student_events'),

    path('student/events/rsvp/<int:event_id>/',
         views.student_events_rsvp,
         name='student_events_rsvp'),

    path('student/events/cancel-rsvp/<int:event_id>/',
         views.student_events_cancel_rsvp,
         name='student_events_cancel_rsvp'),

    # Professional Portal
    path('professional/dashboard/',
         views.professional_dashboard,
         name='professional_dashboard'),

    path('professional/appointments/',
         views.professional_appointments,
         name='professional_appointments'),

    path('professional/appointments/accept/<int:appointment_id>/',
         views.professional_appointments_accept,
         name='professional_appointments_accept'),

    path('professional/appointments/decline/<int:appointment_id>/',
         views.professional_appointments_decline,
         name='professional_appointments_decline'),

    path('professional/appointments/release/<int:appointment_id>/',
         views.professional_appointments_release,
         name='professional_appointments_release'),

    path('professional/appointments/view/<int:appointment_id>/',
         views.professional_appointments_view,
         name='professional_appointments_view'),

    path('professional/stats/',
         views.professional_stats,
         name='professional_stats'),

    # Shared by Professional + Authority stats pages
    path('alerts/dismiss/<int:alert_id>/',
         views.alerts_dismiss,
         name='alerts_dismiss'),

]