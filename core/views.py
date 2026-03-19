from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.http import require_http_methods
from core.db import connect_db, get_current_semester
from core.agents.reset_agent import ResetAgent

# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

def get_session_user(request):
    """
    Return (user_id, role) from the current session, or (None, None).

    Usage at the top of every protected view:
        user_id, role = get_session_user(request)
        if not user_id:
            return redirect('landing')
    """
    return (
        request.session.get('user_id'),
        request.session.get('role'),
    )


def login_required_role(required_role):
    """
    Decorator factory that guards a view by session role.

    Usage:
        @login_required_role('student')
        def student_dashboard(request): ...
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            user_id, role = get_session_user(request)
            if not user_id or role != required_role:
                messages.error(request, 'Please log in to access that page.')
                return redirect('landing')
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator


# Role → redirect target after successful login
ROLE_DASHBOARD = {
    'student':      'student_dashboard',
    'professional': 'professional_dashboard',
    'authority':    'authority_dashboard',
    'admin_it':     'admin_dashboard',
}

# Human-readable role labels used in templates
ROLE_LABELS = {
    'student':      'Student',
    'professional': 'Mental Health Professional',
    'authority':    'University Authority',
    'admin_it':     'Admin IT',
}

# ─────────────────────────────────────────────
# LANDING PAGE  GET /
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def landing(request):
    """
    Role-selection screen.
    Shows four cards: Student / Mental Health Professional /
    University Authority / Admin IT.
    Clicking a card redirects to /login/?role=<role>.

    If a user is already logged in, redirect them straight to
    their dashboard so they don't have to log in again.
    """
    user_id, role = get_session_user(request)
    if user_id and role:
        target = ROLE_DASHBOARD.get(role)
        if target:
            # Dashboard views are added in later.
            # If they don't exist yet, just stay on landing.
            try:
                from django.urls import reverse
                reverse(target)          # raises NoReverseMatch if not wired yet
                return redirect(target)
            except Exception:
                pass

    return render(request, 'landing.html')


# ─────────────────────────────────────────────
# LOGIN  GET /login/  POST /login/
# ─────────────────────────────────────────────
@require_http_methods(['GET', 'POST'])
def login_view(request):
    """
    Single login page shared by all four roles.

    GET  — render login form.  The active role is taken from the
           query-string ?role=<role> (set by the landing page cards).
           Defaults to 'student' if the param is missing or invalid.
           The Student login includes a Google Sign-In button and a
           Register link; the other three do not.

    POST — validate email + password against the users table.
           On success:
             • Store user_id and role in session.
             • Non-student roles → redirect to their dashboard.
             • Students → run ResetAgent, then check questionnaire
               status for the current semester:
                 - Row exists AND responses_reset = FALSE → dashboard.
                 - Otherwise → chatbot (first-time or reset).
           On failure:
             • Flash an error and re-render the form.
    """
    # Accepted roles
    valid_roles = {'student', 'professional', 'authority', 'admin_it'}

    # ── GET ────────────────────────────────────────────────────────────
    if request.method == 'GET':
        role = request.GET.get('role', 'student')
        if role not in valid_roles:
            role = 'student'
        return render(request, 'login.html', {
            'role':       role,
            'role_label': ROLE_LABELS[role],
        })

    # ── POST ───────────────────────────────────────────────────────────
    role  = request.POST.get('role', 'student')
    if role not in valid_roles:
        role = 'student'

    email    = request.POST.get('email',    '').strip().lower()
    password = request.POST.get('password', '').strip()

    if not email or not password:
        messages.error(request, 'Email and password are required.')
        return render(request, 'login.html', {
            'role':       role,
            'role_label': ROLE_LABELS[role],
            'email':      email,
        })

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Look up user by email AND role (so a student can't log in
        # through the Professional login page, etc.)
        cursor.execute(
            """
            SELECT id, full_name, password, role
            FROM   users
            WHERE  email = %s AND role = %s
            """,
            (email, role),
        )
        user = cursor.fetchone()

        if not user or not check_password(password, user['password']):
            messages.error(request, 'Invalid email or password.')
            return render(request, 'login.html', {
                'role':       role,
                'role_label': ROLE_LABELS[role],
                'email':      email,
            })

        # ── Credentials valid — set session ──────────────────────────
        request.session['user_id']   = user['id']
        request.session['role']      = user['role']
        request.session['full_name'] = user['full_name']

        # ── Non-student roles → straight to their dashboard ──────────
        if role != 'student':
            target = ROLE_DASHBOARD.get(role)
            try:
                from django.urls import reverse
                reverse(target)
                return redirect(target)
            except Exception:
                # Dashboard not implemented yet;
                # send to landing with a success message.
                messages.success(
                    request,
                    f'Welcome, {user["full_name"]}! '
                    f'Your dashboard will be available soon.'
                )
                return redirect('landing')

        # ── Student: run ResetAgent then check questionnaire status ──
        ResetAgent().run()

        semester = get_current_semester(cursor)
        if not semester:
            messages.error(
                request,
                'No active semester has been configured. '
                'Please contact Admin IT.'
            )
            return redirect('landing')

        cursor.execute(
            """
            SELECT responses_reset, final_status
            FROM   questionnaire_responses
            WHERE  student_id = %s AND semester = %s
            """,
            (user['id'], semester),
        )
        qr = cursor.fetchone()

        # If a completed, non-reset row exists → go to dashboard.
        # Otherwise (no row, or responses_reset=TRUE, or no
        # final_status yet) → launch chatbot.
        if qr and not qr['responses_reset'] and qr['final_status']:
            try:
                from django.urls import reverse
                reverse('student_dashboard')
                return redirect('student_dashboard')
            except Exception:
                messages.success(
                    request,
                    f'Welcome back, {user["full_name"]}!'
                )
                return redirect('landing')
        else:
            try:
                from django.urls import reverse
                reverse('chatbot')
                return redirect('chatbot')
            except Exception:
                messages.success(
                    request,
                    f'Welcome, {user["full_name"]}! '
                    f'The assessment chatbot will be available soon.'
                )
                return redirect('landing')

    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# STUDENT REGISTRATION  GET/POST /register/
# ─────────────────────────────────────────────
@require_http_methods(['GET', 'POST'])
def register(request):
    """
    Manual student self-registration.

    GET  — render the registration form.
    POST — validate inputs, insert into users + students tables,
           then redirect to the Student login page on success.

    Collects: full name, student ID, department, email, password.
    Passwords are hashed with Django's PBKDF2-SHA256 hasher.
    Email uniqueness is enforced at the database level (UNIQUE constraint)
    and also checked explicitly here to give a friendly error message.
    """
    if request.method == 'GET':
        return render(request, 'register.html')

    # ── Collect & validate form inputs ────────────────────────────────
    full_name  = request.POST.get('full_name',  '').strip()
    student_id = request.POST.get('student_id', '').strip()
    department = request.POST.get('department', '').strip()
    email      = request.POST.get('email',      '').strip().lower()
    password   = request.POST.get('password',   '').strip()
    confirm    = request.POST.get('confirm',     '').strip()

    # Preserve form values so the user doesn't retype everything
    form_data = {
        'full_name':  full_name,
        'student_id': student_id,
        'department': department,
        'email':      email,
    }

    # Required field check
    if not all([full_name, student_id, department, email, password, confirm]):
        messages.error(request, 'All fields are required.')
        return render(request, 'register.html', form_data)

    # Basic email format check
    if '@' not in email or '.' not in email.split('@')[-1]:
        messages.error(request, 'Please enter a valid email address.')
        return render(request, 'register.html', form_data)

    # Password length
    if len(password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return render(request, 'register.html', form_data)

    # Password match
    if password != confirm:
        messages.error(request, 'Passwords do not match.')
        return render(request, 'register.html', form_data)

    # ── Database insert ────────────────────────────────────────────────
    hashed = make_password(password)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Check for duplicate email
        cursor.execute(
            "SELECT id FROM users WHERE email = %s",
            (email,),
        )
        if cursor.fetchone():
            messages.error(
                request,
                'An account with that email address already exists.'
            )
            return render(request, 'register.html', form_data)

        # Insert into users
        cursor.execute(
            """
            INSERT INTO users (role, full_name, email, password)
            VALUES ('student', %s, %s, %s)
            RETURNING id
            """,
            (full_name, email, hashed),
        )
        new_user_id = cursor.fetchone()['id']

        # Insert into students (extra student-specific fields)
        cursor.execute(
            """
            INSERT INTO students (user_id, student_id, department)
            VALUES (%s, %s, %s)
            """,
            (new_user_id, student_id, department),
        )

        conn.commit()

        messages.success(
            request,
            'Registration successful! Please log in.'
        )
        return redirect('login')

    except Exception as exc:
        conn.rollback()
        messages.error(
            request,
            f'An unexpected error occurred. Please try again. ({exc})'
        )
        return render(request, 'register.html', form_data)
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# GOOGLE REGISTRATION COMPLETION
# GET/POST /register/google/
# ─────────────────────────────────────────────
@require_http_methods(['GET', 'POST'])
def register_google(request):
    """
    Shown after a student authenticates with Google OAuth (allauth).

    Two cases when this view is reached:

    Case A — New Google user (no existing account):
      allauth has authenticated with Google and redirected here
      (because LOGIN_REDIRECT_URL = '/register/google/').
      The student must supply: student ID, department, and a password.
      On success → insert into users + students → redirect to login.

    Case B — Existing student (email already in users table):
      Treat as a login: set session and apply the same post-login
      routing as the regular login view (chatbot vs dashboard).

    The Google email is obtained from the allauth SocialAccount
    connected to the currently authenticated Django user
    (request.user, set by allauth after OAuth callback).
    """
    # allauth sets request.user after the OAuth callback.
    # If the user is not authenticated at all, redirect to landing.
    if not request.user.is_authenticated:
        messages.error(
            request,
            'Google Sign-In did not complete. Please try again.'
        )
        return redirect('landing')

    google_email = request.user.email
    if not google_email:
        messages.error(
            request,
            'Could not retrieve your email from Google. Please try again.'
        )
        return redirect('landing')

    google_email = google_email.lower()

    # ── Check if this Google email already has a Baymax account ───────
    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT u.id, u.full_name, u.role, u.password
            FROM   users u
            WHERE  u.email = %s
            """,
            (google_email,),
        )
        existing_user = cursor.fetchone()

        # ── Case B: existing account → treat as login ─────────────────
        if existing_user:
            if existing_user['role'] != 'student':
                messages.error(
                    request,
                    'This email is registered under a non-student role. '
                    'Please use the email/password login.'
                )
                return redirect('login')

            # Set session
            request.session['user_id']   = existing_user['id']
            request.session['role']      = 'student'
            request.session['full_name'] = existing_user['full_name']

            # Apply same post-login routing as regular student login
            ResetAgent().run()

            semester = get_current_semester(cursor)
            if not semester:
                messages.error(
                    request,
                    'No active semester has been configured. '
                    'Please contact Admin IT.'
                )
                return redirect('landing')

            cursor.execute(
                """
                SELECT responses_reset, final_status
                FROM   questionnaire_responses
                WHERE  student_id = %s AND semester = %s
                """,
                (existing_user['id'], semester),
            )
            qr = cursor.fetchone()

            if qr and not qr['responses_reset'] and qr['final_status']:
                try:
                    from django.urls import reverse
                    reverse('student_dashboard')
                    return redirect('student_dashboard')
                except Exception:
                    messages.success(
                        request,
                        f'Welcome back, {existing_user["full_name"]}!'
                    )
                    return redirect('landing')
            else:
                try:
                    from django.urls import reverse
                    reverse('chatbot')
                    return redirect('chatbot')
                except Exception:
                    messages.success(
                        request,
                        f'Welcome, {existing_user["full_name"]}! '
                        f'The assessment chatbot will be available soon.'
                    )
                    return redirect('landing')

        # ── Case A: new Google user → show completion form ─────────────

        # Retrieve the full name from the allauth social account
        # so we can pre-populate it (read-only display in the template)
        google_full_name = (
            request.user.get_full_name()
            or request.user.username
            or google_email.split('@')[0]
        )

        if request.method == 'GET':
            return render(request, 'register_google.html', {
                'google_email':     google_email,
                'google_full_name': google_full_name,
            })

        # ── POST: collect extra fields ─────────────────────────────────
        student_id = request.POST.get('student_id', '').strip()
        department = request.POST.get('department', '').strip()
        password   = request.POST.get('password',   '').strip()
        confirm    = request.POST.get('confirm',     '').strip()

        form_data = {
            'google_email':     google_email,
            'google_full_name': google_full_name,
            'student_id':       student_id,
            'department':       department,
        }

        if not all([student_id, department, password, confirm]):
            messages.error(request, 'All fields are required.')
            return render(request, 'register_google.html', form_data)

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'register_google.html', form_data)

        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'register_google.html', form_data)

        hashed = make_password(password)

        # Re-check for duplicate email (race condition guard)
        cursor.execute(
            "SELECT id FROM users WHERE email = %s",
            (google_email,),
        )
        if cursor.fetchone():
            messages.error(
                request,
                'An account with this Google email already exists. '
                'Please log in instead.'
            )
            return redirect('login')

        # Insert into users
        cursor.execute(
            """
            INSERT INTO users (role, full_name, email, password)
            VALUES ('student', %s, %s, %s)
            RETURNING id
            """,
            (google_full_name, google_email, hashed),
        )
        new_user_id = cursor.fetchone()['id']

        # Insert into students
        cursor.execute(
            """
            INSERT INTO students (user_id, student_id, department)
            VALUES (%s, %s, %s)
            """,
            (new_user_id, student_id, department),
        )

        conn.commit()

        messages.success(
            request,
            'Registration complete! Please log in with your email and password.'
        )
        return redirect('login')

    except Exception as exc:
        conn.rollback()
        messages.error(
            request,
            f'An unexpected error occurred. Please try again. ({exc})'
        )
        return redirect('landing')
    finally:
        cursor.close()
        conn.close()


# ─────────────────────────────────────────────
# LOGOUT  GET /logout/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def logout_view(request):
    """
    Clear the session and redirect to the landing page.

    Using request.session.flush() destroys the current session data
    AND the session cookie, which is more thorough than .clear().
    """
    request.session.flush()
    messages.success(request, 'You have been logged out successfully.')
    return redirect('landing')