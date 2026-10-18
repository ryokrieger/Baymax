"""
Student self-registration with email verification (OTP).

Flow:
    /register/          form -> a pending sign-up is kept in the session and a
                        six-digit code is emailed
    /register/verify/   the code is checked; only then are the user and
                        student rows created and the person signed in
    /register/resend/   a new code, at most once every five minutes

Nothing is written to the database until the code is confirmed. The pending
sign-up holds the password only as a hash, and the code only as an HMAC.
"""
import hashlib
import hmac
import re
import secrets
import time

import psycopg2
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core import email_utils
from core.components import ROLE_DASHBOARD, VALID_DEPARTMENTS
from core.db import connect_db
from core.utils import validate_new_password
from core.views.auth import (
    _signed_in, _start_session, clear_failed_attempts, lockout_minutes_remaining,
    rate_limit, register_failed_attempt,
)

OTP_LIFETIME = 600        # seconds a code stays valid (10 minutes)
RESEND_COOLDOWN = 300     # seconds before another code can be requested
MAX_CODE_ATTEMPTS = 5     # wrong codes allowed per code
SESSION_KEY = 'register_pending'

STUDENT_ID_PATTERN = re.compile(r'^[A-Za-z0-9-]{4,30}$')
DEPARTMENTS = sorted(VALID_DEPARTMENTS)
SEMESTERS = list(range(1, 13))


# ── Helpers ──────────────────────────────────────────────────────────

def _hash_code(email, code):
    message = f'{email}:{code}'.encode('utf-8')
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), message, hashlib.sha256).hexdigest()


def _new_code():
    return f'{secrets.randbelow(10 ** 6):06d}'


def _pending(request):
    data = request.session.get(SESSION_KEY)
    return data if isinstance(data, dict) else None


def _minutes(seconds):
    return max(1, -(-int(seconds) // 60))


def _form_context(values=None, errors=None):
    return {
        'values': values or {},
        'errors': errors or {},
        'departments': DEPARTMENTS,
        'semesters': SEMESTERS,
    }


def _email_key(request):
    pending = _pending(request)
    return (pending or {}).get('email') or 'none'


def _find_conflicts(email, student_id):
    """Which of these are already taken? Returns a dict of field -> message."""
    conflicts = {}
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            conflicts['email'] = 'An account with this email already exists. Try signing in.'
        cursor.execute("SELECT 1 FROM students WHERE lower(student_id) = lower(%s)", (student_id,))
        if cursor.fetchone():
            conflicts['student_id'] = 'This Student ID is already registered.'
    finally:
        cursor.close()
        conn.close()
    return conflicts


def _validate_registration(post):
    """Return (clean_values, errors). Passwords are not echoed back."""
    full_name = ' '.join(post.get('full_name', '').split())
    email = post.get('email', '').strip().lower()
    student_id = post.get('student_id', '').strip().upper()
    department = post.get('department', '')
    semester_raw = post.get('semester', '')
    password = post.get('password', '')
    confirm = post.get('confirm_password', '')

    errors = {}

    if not 2 <= len(full_name) <= 120:
        errors['full_name'] = 'Enter your full name (2 to 120 characters).'

    try:
        if len(email) > 254:
            raise ValidationError('too long')
        validate_email(email)
    except ValidationError:
        errors['email'] = 'Enter a valid email address.'

    if not STUDENT_ID_PATTERN.match(student_id):
        errors['student_id'] = 'Use 4 to 30 letters, numbers or hyphens.'

    if department not in VALID_DEPARTMENTS:
        errors['department'] = 'Choose your department.'

    semester = None
    try:
        semester = int(semester_raw)
        if semester not in SEMESTERS:
            raise ValueError
    except (TypeError, ValueError):
        semester = None
        errors['semester'] = 'Choose your current semester (1 to 12).'

    problems = validate_new_password(password)
    if problems:
        errors['password'] = problems[0]
    elif password != confirm:
        errors['confirm_password'] = 'The two passwords do not match.'

    values = {
        'full_name': full_name, 'email': email, 'student_id': student_id,
        'department': department, 'semester': semester, 'password': password,
    }
    return values, errors


# ── Views ────────────────────────────────────────────────────────────

@require_http_methods(['GET', 'POST'])
@rate_limit(max_attempts=5, window=900, scope='register')
def register_view(request):
    if _signed_in(request):
        return redirect(ROLE_DASHBOARD[request.session['role']])

    if request.method == 'GET':
        return render(request, 'auth/register.html', _form_context())

    values, errors = _validate_registration(request.POST)
    shown = {k: v for k, v in values.items() if k != 'password'}

    if request.rate_limited:
        minutes = lockout_minutes_remaining(request)
        unit = 'minute' if minutes == 1 else 'minutes'
        errors = {'form': f'Too many sign-up attempts for this email. Try again in {minutes} {unit}.'}
        return render(request, 'auth/register.html', _form_context(shown, errors), status=429)

    if not errors:
        errors.update(_find_conflicts(values['email'], values['student_id']))

    if errors:
        return render(request, 'auth/register.html', _form_context(shown, errors))

    code = _new_code()
    if not email_utils.send_otp_email(values['email'], values['full_name'], code,
                                      minutes=OTP_LIFETIME // 60):
        errors['form'] = 'We could not send the verification email. Please try again in a moment.'
        return render(request, 'auth/register.html', _form_context(shown, errors))

    # Each code sent counts toward the per-email limit, so the form cannot be
    # used to flood someone's inbox.
    register_failed_attempt(request)

    now = time.time()
    request.session[SESSION_KEY] = {
        'full_name': values['full_name'],
        'email': values['email'],
        'student_id': values['student_id'],
        'department': values['department'],
        'semester': values['semester'],
        'password_hash': make_password(values['password']),
        'code_hash': _hash_code(values['email'], code),
        'expires_at': now + OTP_LIFETIME,
        'sent_at': now,
        'attempts': 0,
    }
    messages.info(request, f'We sent a 6-digit code to {values["email"]}.')
    return redirect('register_verify')


@require_http_methods(['GET', 'POST'])
@rate_limit(max_attempts=10, window=900, scope='register_verify', key=_email_key)
def register_verify_view(request):
    if _signed_in(request):
        return redirect(ROLE_DASHBOARD[request.session['role']])

    pending = _pending(request)
    if pending is None:
        messages.error(request, 'Your sign-up session has expired. Please start again.')
        return redirect('register')

    now = time.time()
    context = {
        'email': pending['email'],
        'minutes_left': _minutes(max(0, pending['expires_at'] - now)),
        'resend_wait': _minutes(max(0, pending['sent_at'] + RESEND_COOLDOWN - now))
                       if now < pending['sent_at'] + RESEND_COOLDOWN else 0,
        'error': None,
    }

    if request.method == 'GET':
        return render(request, 'auth/register_otp.html', context)

    if request.rate_limited:
        minutes = lockout_minutes_remaining(request)
        unit = 'minute' if minutes == 1 else 'minutes'
        context['error'] = f'Too many wrong codes. Try again in {minutes} {unit}.'
        return render(request, 'auth/register_otp.html', context, status=429)

    if now > pending['expires_at']:
        context['error'] = 'That code has expired. Request a new one below.'
        context['minutes_left'] = 0
        return render(request, 'auth/register_otp.html', context)

    code = re.sub(r'\D', '', request.POST.get('code', ''))[:6]
    matches = len(code) == 6 and hmac.compare_digest(
        _hash_code(pending['email'], code), pending['code_hash'])

    if not matches:
        register_failed_attempt(request)
        pending['attempts'] += 1
        if pending['attempts'] >= MAX_CODE_ATTEMPTS:
            request.session.pop(SESSION_KEY, None)
            messages.error(request, 'Too many wrong codes. Please start again.')
            return redirect('register')
        request.session[SESSION_KEY] = pending
        left = MAX_CODE_ATTEMPTS - pending['attempts']
        context['error'] = (f'That code is not correct. {left} '
                            f'{"try" if left == 1 else "tries"} left.')
        return render(request, 'auth/register_otp.html', context)

    # Code confirmed: create the account.
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('student', %s, %s, %s) RETURNING id",
            (pending['full_name'], pending['email'], pending['password_hash']),
        )
        user_id = cursor.fetchone()['id']
        cursor.execute(
            "INSERT INTO students (user_id, student_id, department, semester) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, pending['student_id'], pending['department'], pending['semester']),
        )
        conn.commit()
    except psycopg2.IntegrityError:
        # Someone registered this email in the meantime.
        conn.rollback()
        request.session.pop(SESSION_KEY, None)
        messages.error(request, 'An account with this email already exists. Please sign in.')
        return redirect('login')
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    clear_failed_attempts(request)
    user = {'id': user_id, 'role': 'student',
            'full_name': pending['full_name'], 'email': pending['email']}
    request.session.pop(SESSION_KEY, None)
    _start_session(request, user)
    messages.success(request, f'Welcome to Baymax, {user["full_name"]}! Your account is ready.')
    return redirect(ROLE_DASHBOARD['student'])


@require_http_methods(['POST'])
def register_resend_view(request):
    pending = _pending(request)
    if pending is None:
        messages.error(request, 'Your sign-up session has expired. Please start again.')
        return redirect('register')

    now = time.time()
    wait = pending['sent_at'] + RESEND_COOLDOWN - now
    if wait > 0:
        messages.error(request, f'Please wait {_minutes(wait)} more '
                                f'{"minute" if _minutes(wait) == 1 else "minutes"} before asking for a new code.')
        return redirect('register_verify')

    code = _new_code()
    if not email_utils.send_otp_email(pending['email'], pending['full_name'], code,
                                      minutes=OTP_LIFETIME // 60):
        messages.error(request, 'We could not send the email. Please try again in a moment.')
        return redirect('register_verify')

    pending.update(code_hash=_hash_code(pending['email'], code), expires_at=now + OTP_LIFETIME,
                   sent_at=now, attempts=0)
    request.session[SESSION_KEY] = pending
    messages.info(request, f'A new code is on its way to {pending["email"]}.')
    return redirect('register_verify')