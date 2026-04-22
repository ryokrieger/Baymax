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

    path('register/verify/',
         views.register_verify_otp,
         name='register_verify_otp'),

    path('register/resend-otp/',
         views.register_resend_otp,
         name='register_resend_otp'),

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

    path('professional/appointments/reschedule/<int:appointment_id>/',
         views.professional_appointments_reschedule,
         name='professional_appointments_reschedule'),

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

    # Authority Portal
    path('authority/dashboard/',
         views.authority_dashboard,
         name='authority_dashboard'),

    path('authority/stats/',
         views.authority_stats,
         name='authority_stats'),

    path('authority/events/',
         views.authority_events,
         name='authority_events'),

    path('authority/events/create/',
         views.authority_events_create,
         name='authority_events_create'),

    path('authority/events/edit/<int:event_id>/',
         views.authority_events_edit,
         name='authority_events_edit'),

    path('authority/events/delete/<int:event_id>/',
         views.authority_events_delete,
         name='authority_events_delete'),

    # Admin IT Panel
    path('admin/dashboard/',
         views.admin_dashboard,
         name='admin_dashboard'),

    path('admin/students/',
         views.admin_students,
         name='admin_students'),
     
    path('admin/students/reset/<int:student_id>/',
         views.admin_students_reset,
         name='admin_students_reset'),
     
    path('admin/students/delete/<int:student_id>/',
         views.admin_students_delete,
         name='admin_students_delete'),
    path('admin/students/set-start-date/',
         views.admin_students_set_start_date,
         name='admin_students_set_start_date'),

    path('admin/professionals/',
         views.admin_professionals,
         name='admin_professionals'),
     
    path('admin/professionals/register/',
         views.admin_professionals_register,
         name='admin_professionals_register'),
     
    path('admin/professionals/delete/<int:prof_id>/',
         views.admin_professionals_delete,
         name='admin_professionals_delete'),

    path('admin/authority/',
         views.admin_authority,
         name='admin_authority'),
     
    path('admin/authority/register/',
         views.admin_authority_register,
         name='admin_authority_register'),
     
    path('admin/authority/delete/<int:authority_id>/',
         views.admin_authority_delete,
         name='admin_authority_delete'),

    path('admin/it/',
         views.admin_it,
         name='admin_it'),
     
    path('admin/it/register/',
         views.admin_it_register,
         name='admin_it_register'),
     
    path('admin/it/delete/<int:admin_user_id>/',
         views.admin_it_delete,
         name='admin_it_delete'),

    path('admin/appointments/',
         views.admin_appointments,
         name='admin_appointments'),

    path('admin/appointments/delete/<int:appointment_id>/',
         views.admin_appointments_delete,
         name='admin_appointments_delete'),

    path('admin/events/',
         views.admin_events,
         name='admin_events'),
     
    path('admin/events/delete/<int:event_id>/',
         views.admin_events_delete,
         name='admin_events_delete'),
     
]