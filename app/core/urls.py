from django.urls import path

from core.views import auth

urlpatterns = [
    path('', auth.landing_view, name='landing'),

    # Registration
    path('register/', auth.register_view, name='register'),
    path('register/verify/', auth.register_verify_view, name='register_verify'),
    path('register/google/', auth.register_google_view, name='register_google'),
    path('google/callback/', auth.google_callback_view, name='google_callback'),

    # Login / logout / password
    path('login/', auth.login_view, name='login'),
    path('logout/', auth.logout_view, name='logout'),
    path('password/change/', auth.password_change_view, name='password_change'),

    # Placeholder dashboards
    path('student/dashboard/', auth.role_home, name='student_dashboard'),
    path('professional/dashboard/', auth.role_home, name='professional_dashboard'),
    path('authority/dashboard/', auth.role_home, name='authority_dashboard'),
    path('admin/dashboard/', auth.role_home, name='admin_dashboard'),
]