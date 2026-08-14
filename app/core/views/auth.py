import functools
import secrets
import time

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render

from core.components import VALID_DEPARTMENTS
from core.db import connect_db
from core.email_utils import send_otp_email

OTP_EXPIRY_SECONDS = 600     # 10 minutes
OTP_RESEND_COOLDOWN = 300    # 5 minutes
OTP_CACHE_TTL = 900          # kept a bit past expiry so we can say "expired", not "not found"

# Maps a `users.role` value to the URL name of that role's dashboard.
# The routes themselves are placeholders — defined here so every view that
# needs to redirect somewhere role-appropriate uses the same mapping.
_DASHBOARD_URL_NAMES = {
    'student': 'student_dashboard',
    'professional': 'professional_dashboard',
    'authority': 'authority_dashboard',
    'admin_it': 'admin_dashboard',
}


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required_role(*roles):
    """Restrict a view to one or more session-authenticated roles."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.session.get('role') not in roles:
                return redirect('login')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def rate_limit(max_attempts: int = 5, window: int = 900):
    """Block repeated POST failures to a view for `window` seconds."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method == 'POST':
                key = f'rate_limit:{request.POST.get("email", "")}'
                count = cache.get(key, 0)
                if count >= max_attempts:
                    # Let the view handle the error display — it just
                    # checks request.rate_limited.
                    request.rate_limited = True
                    return view_func(request, *args, **kwargs)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Landing
# ---------------------------------------------------------------------------

def landing_view(request):
    """Public landing page — entry point into registration/login."""
    return render(request, 'auth/landing.html')


# ---------------------------------------------------------------------------
# Registration — OTP path
# ---------------------------------------------------------------------------

def _pending_key(email: str) -> str:
    return f'pending_registration:{email}'


def _generate_otp() -> str:
    return f'{secrets.randbelow(1_000_000):06d}'


def register_view(request):
    """Step 1 of student self-registration — collect details, send an OTP."""
    errors = {}
    form_data = {'full_name': '', 'email': '', 'student_id': '', 'department': ''}

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        student_id = request.POST.get('student_id', '').strip()
        department = request.POST.get('department', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        form_data = {
            'full_name': full_name,
            'email': email,
            'student_id': student_id,
            'department': department,
        }

        if not full_name:
            errors['full_name'] = 'Full name is required.'

        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'

        if not student_id:
            errors['student_id'] = 'Student ID is required.'

        if department not in VALID_DEPARTMENTS:
            errors['department'] = 'Select a valid department.'

        if not errors.get('email'):
            conn = connect_db()
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT id FROM users WHERE email = %s', [email])
                    if cur.fetchone():
                        errors['email'] = 'An account with this email already exists.'
                    if not errors.get('student_id'):
                        cur.execute('SELECT id FROM students WHERE student_id = %s', [student_id])
                        if cur.fetchone():
                            errors['student_id'] = 'This student ID is already registered.'
            finally:
                conn.close()

        if not password:
            errors['password'] = 'Password is required.'
        else:
            try:
                validate_password(password)
            except ValidationError as exc:
                errors['password'] = ' '.join(exc.messages)

        if password and confirm_password != password:
            errors['confirm_password'] = 'Passwords do not match.'

        if not errors:
            otp_code = _generate_otp()
            now = time.time()
            cache.set(_pending_key(email), {
                'full_name': full_name,
                'student_id': student_id,
                'department': department,
                'password_hash': make_password(password),
                'otp_code': otp_code,
                'otp_expires_at': now + OTP_EXPIRY_SECONDS,
                'last_sent_at': now,
            }, OTP_CACHE_TTL)

            send_otp_email(email, otp_code)

            request.session['pending_registration_email'] = email
            return redirect('register_verify')

    return render(request, 'auth/register.html', {
        'errors': errors,
        'form_data': form_data,
        'departments': VALID_DEPARTMENTS,
    })


@rate_limit(max_attempts=5, window=900)
def register_verify_view(request):
    """Step 2 — enter the emailed code (or request a new one) to finish registration."""
    email = request.session.get('pending_registration_email')
    if not email:
        return redirect('register')

    error = None
    resent = False

    if getattr(request, 'rate_limited', False):
        return render(request, 'auth/register_otp.html', {
            'email': email,
            'error': 'Too many attempts. Please wait 15 minutes and try again.',
        })

    pending = cache.get(_pending_key(email))

    if request.method == 'POST':
        if not pending:
            return redirect('register')

        if 'resend' in request.POST:
            elapsed = time.time() - pending['last_sent_at']
            if elapsed < OTP_RESEND_COOLDOWN:
                wait = int(OTP_RESEND_COOLDOWN - elapsed)
                error = f'Please wait {wait} seconds before requesting a new code.'
            else:
                new_code = _generate_otp()
                pending['otp_code'] = new_code
                pending['otp_expires_at'] = time.time() + OTP_EXPIRY_SECONDS
                pending['last_sent_at'] = time.time()
                cache.set(_pending_key(email), pending, OTP_CACHE_TTL)
                send_otp_email(email, new_code)
                resent = True
        else:
            entered_code = request.POST.get('otp_code', '').strip()

            if time.time() > pending['otp_expires_at']:
                error = 'This code has expired. Request a new one below.'
            elif entered_code != pending['otp_code']:
                key = f'rate_limit:{email}'
                cache.set(key, cache.get(key, 0) + 1, 900)
                error = 'Incorrect code. Please try again.'
            else:
                conn = connect_db()
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                'INSERT INTO users (role, full_name, email, password) '
                                'VALUES (%s, %s, %s, %s) RETURNING id',
                                ['student', pending['full_name'], email, pending['password_hash']],
                            )
                            user_id = cur.fetchone()['id']
                            cur.execute(
                                'INSERT INTO students (user_id, student_id, department) '
                                'VALUES (%s, %s, %s)',
                                [user_id, pending['student_id'], pending['department']],
                            )
                finally:
                    conn.close()

                cache.delete(_pending_key(email))
                del request.session['pending_registration_email']
                request.session['user_id'] = user_id
                request.session['role'] = 'student'
                request.session.cycle_key()
                return redirect(_DASHBOARD_URL_NAMES['student'])

    return render(request, 'auth/register_otp.html', {
        'email': email,
        'error': error,
        'resent': resent,
    })


# ---------------------------------------------------------------------------
# Registration — Google OAuth path
# ---------------------------------------------------------------------------

def google_callback_view(request):
    """
    Where allauth sends the browser after a successful Google handshake
    (LOGIN_REDIRECT_URL in settings.py). Checks the authenticated email
    against our own `users` table — existing account logs straight in,
    new email goes to register_google to collect the remaining fields.
    """
    if not request.user.is_authenticated:
        return redirect('login')

    email = request.user.email
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, role FROM users WHERE email = %s', [email])
            row = cur.fetchone()
    finally:
        conn.close()

    if row:
        request.session['user_id'] = row['id']
        request.session['role'] = row['role']
        request.session.cycle_key()
        return redirect(_DASHBOARD_URL_NAMES[row['role']])

    request.session['pending_google_email'] = email
    request.session['pending_google_name'] = request.user.get_full_name() or email
    return redirect('register_google')


def register_google_view(request):
    """Step 2 of Google sign-up — collect student_id/department, then create the account."""
    email = request.session.get('pending_google_email')
    full_name = request.session.get('pending_google_name')
    if not email:
        return redirect('landing')

    errors = {}
    form_data = {'student_id': '', 'department': ''}

    if request.method == 'POST':
        student_id = request.POST.get('student_id', '').strip()
        department = request.POST.get('department', '').strip()
        form_data = {'student_id': student_id, 'department': department}

        if not student_id:
            errors['student_id'] = 'Student ID is required.'
        if department not in VALID_DEPARTMENTS:
            errors['department'] = 'Select a valid department.'

        if not errors.get('student_id'):
            conn = connect_db()
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT id FROM students WHERE student_id = %s', [student_id])
                    if cur.fetchone():
                        errors['student_id'] = 'This student ID is already registered.'
            finally:
                conn.close()

        if not errors:
            conn = connect_db()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            'INSERT INTO users (role, full_name, email, password) '
                            'VALUES (%s, %s, %s, %s) RETURNING id',
                            ['student', full_name, email, make_password(None)],
                        )
                        user_id = cur.fetchone()['id']
                        cur.execute(
                            'INSERT INTO students (user_id, student_id, department) '
                            'VALUES (%s, %s, %s)',
                            [user_id, student_id, department],
                        )
            finally:
                conn.close()

            del request.session['pending_google_email']
            del request.session['pending_google_name']
            request.session['user_id'] = user_id
            request.session['role'] = 'student'
            request.session.cycle_key()
            return redirect(_DASHBOARD_URL_NAMES['student'])

    return render(request, 'auth/register_google.html', {
        'email': email,
        'full_name': full_name,
        'errors': errors,
        'form_data': form_data,
        'departments': VALID_DEPARTMENTS,
    })


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@rate_limit(max_attempts=5, window=900)
def login_view(request):
    """Single login page for every role — role is detected from the database."""
    error = None

    if getattr(request, 'rate_limited', False):
        return render(request, 'auth/login.html', {
            'error': 'Too many failed attempts. Please wait 15 minutes and try again.',
        })

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT id, role, password FROM users WHERE email = %s', [email])
                row = cur.fetchone()
        finally:
            conn.close()

        if row and check_password(password, row['password']):
            request.session['user_id'] = row['id']
            request.session['role'] = row['role']
            request.session.cycle_key()
            return redirect(_DASHBOARD_URL_NAMES[row['role']])

        key = f'rate_limit:{email}'
        cache.set(key, cache.get(key, 0) + 1, 900)
        error = 'Invalid email or password.'

    return render(request, 'auth/login.html', {'error': error})


def logout_view(request):
    """Clears the session entirely and returns to the landing page."""
    request.session.flush()
    return redirect('landing')


# ---------------------------------------------------------------------------
# Password Change (any authenticated role)
# ---------------------------------------------------------------------------

@login_required_role('student', 'professional', 'authority', 'admin_it')
def password_change_view(request):
    """Change password — requires the current password, works for every role."""
    errors = {}
    success = False

    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT password FROM users WHERE id = %s', [request.session['user_id']])
                row = cur.fetchone()

            if not row or not check_password(current_password, row['password']):
                errors['current_password'] = 'Current password is incorrect.'

            if not new_password:
                errors['new_password'] = 'New password is required.'
            else:
                try:
                    validate_password(new_password)
                except ValidationError as exc:
                    errors['new_password'] = ' '.join(exc.messages)

            if new_password and confirm_password != new_password:
                errors['confirm_password'] = 'Passwords do not match.'

            if not errors:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            'UPDATE users SET password = %s WHERE id = %s',
                            [make_password(new_password), request.session['user_id']],
                        )
                success = True
        finally:
            conn.close()

    return render(request, 'auth/password_change.html', {'errors': errors, 'success': success})


# ---------------------------------------------------------------------------
# Placeholder dashboard
# ---------------------------------------------------------------------------

@login_required_role('student', 'professional', 'authority', 'admin_it')
def role_home(request):
    """
    Shared temporary dashboard for every role. Gets replaced by the real
    dashboard view+template in each role's own sprint (2/4/5/6) — routing
    (core/urls.py) never needs to change again after this.
    """
    return render(request, 'shared/coming_soon.html', {'role': request.session.get('role')})