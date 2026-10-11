"""
Baymax routes.

Sprint 1 so far: landing, login, logout, password change and a placeholder
dashboard for each role. Registration (OTP and Google) follows in this sprint;
the real portals are built in Sprints 2-6.
"""
from django.urls import path

from core.views import admin as admin_portal
from core.views import auth, authority, professional, student

urlpatterns = [
    # Authentication
    path('',                 auth.landing,              name='landing'),
    path('login/',           auth.login_view,           name='login'),
    path('logout/',          auth.logout_view,          name='logout'),
    path('account/password/', auth.password_change_view, name='password_change'),

    # Role portals
    path('student/',      student.student_dashboard,           name='student_dashboard'),
    path('professional/', professional.professional_dashboard, name='professional_dashboard'),
    path('authority/',    authority.authority_dashboard,       name='authority_dashboard'),
    path('admin/',        admin_portal.admin_dashboard,        name='admin_dashboard'),
]