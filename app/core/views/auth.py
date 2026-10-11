"""
Authentication: decorators, landing, login, logout, password change.

Sessions carry four keys once someone is signed in:
    user_id, role, full_name, email
The role always comes from the database, never from the request.
"""
import functools
import hashlib
import math
import time

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.cache import add_never_cache_headers
from django.views.decorators.http import require_http_methods

from core import email_utils
from core.components import ROLE_CARDS, ROLE_DASHBOARD, ROLE_LABELS, VALID_ROLES
from core.db import connect_db
from core.utils import validate_new_password

# ════════════════════════════════════════════════════════════════════
#  DECORATORS
# ════════════════════════════════════════════════════════════════════


def login_required_role(*roles):
    """Restrict a view to signed-in users with one of `roles`.

    - Not signed in: sent to the login page.
    - Signed in with another role: told so, and sent to their own dashboard.
    Responses are marked no-store so the Back button after logout cannot
    show someone's wellbeing data from the browser cache.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = request.session.get('role')
            if not request.session.get('user_id') or role not in ROLE_DASHBOARD:
                request.session.flush()
                return redirect('login')

            if role not in roles:
                messages.error(request, "You don't have access to that page.")
                return redirect(ROLE_DASHBOARD[role])

            response = view_func(request, *args, **kwargs)
            add_never_cache_headers(response)
            return response
        return wrapper
    return decorator


def _rate_limit_cache_key(request, scope, key_func):
    identity = key_func(request) if key_func else request.POST.get('email', '')
    identity = str(identity or '').strip().lower()[:254]
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]
    return f'rate_limit:{scope}:{digest}'


def rate_limit(max_attempts=5, window=900, scope='login', key=None):
    """Block repeated failures for `window` seconds.

    The decorator only *checks*: on a POST it sets `request.rate_limited` to
    True once `max_attempts` failures are on record. The view decides what to
    show, and reports each failure with `register_failed_attempt(request)` and
    a success with `clear_failed_attempts(request)`.

    By default attempts are counted per submitted email address. Pass
    `key=lambda request: ...` to count by something else, and a different
    `scope` so counters for different forms stay separate.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            request.rate_limited = False
            request.rate_limit_key = None
            request.rate_limit_window = window
            request.rate_limit_max = max_attempts

            if request.method == 'POST':
                cache_key = _rate_limit_cache_key(request, scope, key)
                request.rate_limit_key = cache_key
                record = cache.get(cache_key)
                if record and record['count'] >= max_attempts:
                    if time.time() - record['start'] < window:
                        request.rate_limited = True
                    else:
                        cache.delete(cache_key)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def register_failed_attempt(request):
    """Count one failure against the current request's rate-limit key."""
    cache_key = getattr(request, 'rate_limit_key', None)
    if not cache_key:
        return
    window = request.rate_limit_window
    now = time.time()
    record = cache.get(cache_key)
    if not record or now - record['start'] >= window:
        record = {'count': 0, 'start': now}
    record['count'] += 1
    # Expire when the window that began at the first failure ends.
    cache.set(cache_key, record, timeout=max(1, int(window - (now - record['start']))))


def clear_failed_attempts(request):
    cache_key = getattr(request, 'rate_limit_key', None)
    if cache_key:
        cache.delete(cache_key)


def lockout_minutes_remaining(request):
    """Whole minutes (at least 1) until the lockout ends."""
    record = cache.get(getattr(request, 'rate_limit_key', None) or '')
    if not record:
        return 1
    remaining = request.rate_limit_window - (time.time() - record['start'])
    return max(1, math.ceil(remaining / 60))


# ════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════

_dummy_hash = None


def _burn_password_check(password):
    """Spend the same time on an unknown email as on a real one, so response
    time does not reveal which email addresses have accounts."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password('baymax-not-a-real-password')
    check_password(password, _dummy_hash)


def _signed_in(request):
    return bool(request.session.get('user_id')) and request.session.get('role') in ROLE_DASHBOARD


def _start_session(request, user):
    """Create a fresh signed-in session (new key, so no session fixation)."""
    request.session.cycle_key()
    request.session['user_id'] = user['id']
    request.session['role'] = user['role']
    request.session['full_name'] = user['full_name']
    request.session['email'] = user['email']


def _login_context(request, role_hint, email='', error=None):
    return {
        'role': role_hint,
        'role_cards': ROLE_CARDS,
        'email': email,
        'error': error,
    }


# ════════════════════════════════════════════════════════════════════
#  LANDING
# ════════════════════════════════════════════════════════════════════


@require_http_methods(['GET'])
def landing(request):
    if _signed_in(request):
        return redirect(ROLE_DASHBOARD[request.session['role']])
    return render(request, 'auth/landing.html', {'role_cards': ROLE_CARDS})


# ════════════════════════════════════════════════════════════════════
#  LOGIN
# ════════════════════════════════════════════════════════════════════


@require_http_methods(['GET', 'POST'])
@rate_limit(max_attempts=5, window=900)
def login_view(request):
    """One login page for all four roles.

    The role comes from the database. The optional `role` value (from the
    landing-page cards) only says which door the person walked through: if
    the account turns out to belong to another role, they are told, instead
    of silently landing somewhere unexpected.
    """
    if _signed_in(request):
        return redirect(ROLE_DASHBOARD[request.session['role']])

    role_hint = request.GET.get('role') or request.POST.get('role') or ''
    if role_hint not in VALID_ROLES:
        role_hint = ''

    if request.method == 'GET':
        return render(request, 'auth/login.html', _login_context(request, role_hint))

    email = request.POST.get('email', '').strip().lower()[:254]
    password = request.POST.get('password', '')

    if request.rate_limited:
        minutes = lockout_minutes_remaining(request)
        unit = 'minute' if minutes == 1 else 'minutes'
        error = f'Too many failed attempts. Please try again in {minutes} {unit}.'
        return render(request, 'auth/login.html',
                      _login_context(request, role_hint, email, error), status=429)

    if not email or not password:
        return render(request, 'auth/login.html',
                      _login_context(request, role_hint, email, 'Enter your email and password.'))

    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, full_name, email, password, role, is_active "
            "FROM users WHERE email = %s",
            (email,),
        )
        user = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if user is None:
        _burn_password_check(password)
        valid = False
    else:
        valid = check_password(password, user['password'])

    if not valid:
        register_failed_attempt(request)
        return render(request, 'auth/login.html',
                      _login_context(request, role_hint, email, 'Invalid email or password.'))

    # From here on the password was correct, so it is safe to say more.
    if not user['is_active']:
        return render(request, 'auth/login.html', _login_context(
            request, role_hint, email,
            'This account has been deactivated. Please contact Admin IT.'))

    if role_hint and role_hint != user['role']:
        error = (f'That is a {ROLE_LABELS[user["role"]]} account, not a '
                 f'{ROLE_LABELS[role_hint]} account. Choose the right role above and try again.')
        return render(request, 'auth/login.html', _login_context(request, role_hint, email, error))

    clear_failed_attempts(request)
    _start_session(request, user)
    messages.success(request, f'Welcome back, {user["full_name"]}.')
    return redirect(ROLE_DASHBOARD[user['role']])


# ════════════════════════════════════════════════════════════════════
#  LOGOUT
# ════════════════════════════════════════════════════════════════════


@require_http_methods(['GET', 'POST'])
def logout_view(request):
    """Sign out. POST only does the work, so another site cannot log someone
    out with a link or image; a GET just goes home."""
    if request.method == 'POST':
        request.session.flush()
        messages.success(request, 'You have been signed out.')
    return redirect('landing')


# ════════════════════════════════════════════════════════════════════
#  PASSWORD CHANGE (all roles)
# ════════════════════════════════════════════════════════════════════


@require_http_methods(['GET', 'POST'])
@login_required_role(*VALID_ROLES)
@rate_limit(max_attempts=5, window=900, scope='password_change',
            key=lambda request: request.session.get('user_id'))
def password_change_view(request):
    role = request.session['role']
    user_id = request.session['user_id']

    if request.method == 'GET':
        return render(request, 'auth/password_change.html', {'errors': {}})

    current = request.POST.get('current_password', '')
    new = request.POST.get('new_password', '')
    confirm = request.POST.get('confirm_password', '')

    if request.rate_limited:
        minutes = lockout_minutes_remaining(request)
        unit = 'minute' if minutes == 1 else 'minutes'
        return render(request, 'auth/password_change.html', {
            'errors': {'form': f'Too many failed attempts. Please try again in {minutes} {unit}.'},
        }, status=429)

    errors = {}

    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name, email, password FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()

        if user is None:
            # The account was removed while signed in.
            request.session.flush()
            return redirect('login')

        if not current:
            errors['current_password'] = 'Enter your current password.'
        elif not check_password(current, user['password']):
            register_failed_attempt(request)
            errors['current_password'] = 'That is not your current password.'

        if not errors:
            problems = validate_new_password(new)
            if problems:
                errors['new_password'] = problems[0]
            elif new == current:
                errors['new_password'] = 'Choose a password different from your current one.'
            elif new != confirm:
                errors['confirm_password'] = 'The two passwords do not match.'

        if errors:
            return render(request, 'auth/password_change.html', {'errors': errors})

        cursor.execute(
            "UPDATE users SET password = %s WHERE id = %s",
            (make_password(new), user_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    clear_failed_attempts(request)
    request.session.cycle_key()
    email_utils.send_password_changed_email(user['email'], user['full_name'])
    messages.success(request, 'Your password has been changed.')
    return redirect(ROLE_DASHBOARD[role])