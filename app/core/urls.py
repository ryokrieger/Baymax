"""
Baymax routes.

Sprint 1 so far: landing, login, logout, password change, OTP registration
and a placeholder dashboard for each role. Google sign-in follows in this
sprint; the real portals are built in Sprints 2-6.
"""
from django.urls import path

from core.views import admin as admin_portal
from core.views import auth, authority, professional, register, student

urlpatterns = [
    # Authentication
    path('',                 auth.landing,              name='landing'),
    path('login/',           auth.login_view,           name='login'),
    path('logout/',          auth.logout_view,          name='logout'),
    path('account/password/', auth.password_change_view, name='password_change'),

    path('register/',        register.register_view,        name='register'),
    path('register/verify/', register.register_verify_view, name='register_verify'),
    path('register/resend/', register.register_resend_view, name='register_resend'),

    # Role portals
    path('student/',      student.student_dashboard,           name='student_dashboard'),
    path('professional/', professional.professional_dashboard, name='professional_dashboard'),
    path('authority/',    authority.authority_dashboard,       name='authority_dashboard'),
    path('admin/',        admin_portal.admin_dashboard,        name='admin_dashboard'),
]