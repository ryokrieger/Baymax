from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.http import require_http_methods
from core.db import connect_db, get_current_semester
from core.agents.reset_agent import ResetAgent
from core.ml import predict as ml_predict
from core.agents.triage_agent import TriageAgent

# ── Email helper ──────────────────────────────────────────────────────────────
def send_welcome_email(full_name, email, password, role_label):
    """
    Send a congratulatory welcome email to a newly registered
    Professional, Authority, or Admin IT account.
    """
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    subject = f'Welcome to Baymax — Your {role_label} Account'
    message = (
        f'Dear {full_name},\n\n'
        f'Congratulations! Your {role_label} account on the Baymax '
        f'Mental Health Tracking System has been created by the Admin IT team.\n\n'
        f'Your login credentials are:\n'
        f'  Email    : {email}\n'
        f'  Password : {password}\n\n'
        f'Please log in at your earliest convenience and consider changing '
        f'your password after your first login.\n\n'
        f'Best regards,\n'
        f'Baymax Admin IT Team'
    )
    try:
        send_mail(
            subject,
            message,
            django_settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
    except Exception as exc:
        # Log but do not crash — registration has already succeeded
        import logging
        logging.getLogger(__name__).warning(
            f'Welcome email failed for {email}: {exc}'
        )

# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

def get_session_user(request):
    """Return (user_id, role) from the session, or (None, None)."""
    return (
        request.session.get('user_id'),
        request.session.get('role'),
    )

def login_required_role(required_role):
    """Decorator factory that guards a view by session role."""
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

ROLE_DASHBOARD = {
    'student':      'student_dashboard',
    'professional': 'professional_dashboard',
    'authority':    'authority_dashboard',
    'admin_it':     'admin_dashboard',
}

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
    Role-selection screen.  Four cards link to /login/?role=<role>.
    If already logged in, silently forward to the correct dashboard.
    """
    user_id, role = get_session_user(request)
    if user_id and role:
        target = ROLE_DASHBOARD.get(role)
        if target:
            try:
                from django.urls import reverse
                reverse(target)
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
    Role is passed via ?role= query param (GET) or hidden field (POST).

    On success:
      - Non-student roles  → their dashboard (or landing if not built yet).
      - Students           → ResetAgent → semester check →
                             student_dashboard  (completed assessment)
                             chatbot            (first-time or reset)
    """
    valid_roles = {'student', 'professional', 'authority', 'admin_it'}

    if request.method == 'GET':
        role = request.GET.get('role', 'student')
        if role not in valid_roles:
            role = 'student'
        return render(request, 'login.html', {
            'role': role, 'role_label': ROLE_LABELS[role],
        })

    role     = request.POST.get('role', 'student')
    if role not in valid_roles:
        role = 'student'
    email    = request.POST.get('email',    '').strip().lower()
    password = request.POST.get('password', '').strip()

    if not email or not password:
        messages.error(request, 'Email and password are required.')
        return render(request, 'login.html', {
            'role': role, 'role_label': ROLE_LABELS[role], 'email': email,
        })

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, full_name, password, role FROM users "
            "WHERE email = %s AND role = %s",
            (email, role),
        )
        user = cursor.fetchone()

        if not user or not check_password(password, user['password']):
            messages.error(request, 'Invalid email or password.')
            return render(request, 'login.html', {
                'role': role, 'role_label': ROLE_LABELS[role], 'email': email,
            })

        request.session['user_id']   = user['id']
        request.session['role']      = user['role']
        request.session['full_name'] = user['full_name']

        if role != 'student':
            target = ROLE_DASHBOARD.get(role)
            try:
                from django.urls import reverse
                reverse(target)
                return redirect(target)
            except Exception:
                messages.success(
                    request,
                    f'Welcome, {user["full_name"]}! '
                    f'Your dashboard will be available soon.'
                )
                return redirect('landing')

        # ── Student post-login flow ───────────────────────────────────
        ResetAgent().run()
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured. Please contact Admin IT.')
            return redirect('landing')

        cursor.execute(
            "SELECT final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user['id'], semester),
        )
        qr = cursor.fetchone()

        if qr and qr['final_status']:
            return redirect('student_dashboard')
        else:
            return redirect('chatbot')

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
    Collects: full name, student ID, department, email, password.
    """
    if request.method == 'GET':
        return render(request, 'register.html')

    full_name  = request.POST.get('full_name',  '').strip()
    student_id = request.POST.get('student_id', '').strip()
    department = request.POST.get('department', '').strip()
    email      = request.POST.get('email',      '').strip().lower()
    password   = request.POST.get('password',   '').strip()
    confirm    = request.POST.get('confirm',     '').strip()

    form_data = {
        'full_name':  full_name,
        'student_id': student_id,
        'department': department,
        'email':      email,
    }

    valid_depts = {'CSE', 'EEE', 'ENG', 'ECO', 'BBA'}

    if not all([full_name, student_id, department, email, password, confirm]):
        messages.error(request, 'All fields are required.')
        return render(request, 'register.html', form_data)
    if department not in valid_depts:
        messages.error(request, 'Please select a valid department.')
        return render(request, 'register.html', form_data)
    if '@' not in email or '.' not in email.split('@')[-1]:
        messages.error(request, 'Please enter a valid email address.')
        return render(request, 'register.html', form_data)
    if len(password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return render(request, 'register.html', form_data)
    if password != confirm:
        messages.error(request, 'Passwords do not match.')
        return render(request, 'register.html', form_data)

    hashed = make_password(password)
    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            messages.error(request, 'An account with that email already exists.')
            return render(request, 'register.html', form_data)

        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('student', %s, %s, %s) RETURNING id",
            (full_name, email, hashed),
        )
        new_user_id = cursor.fetchone()['id']
        cursor.execute(
            "INSERT INTO students (user_id, student_id, department) VALUES (%s, %s, %s)",
            (new_user_id, student_id, department),
        )
        conn.commit()
        messages.success(request, 'Registration successful! Please log in.')
        return redirect('login')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An unexpected error occurred. ({exc})')
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
    Google OAuth completion page for new students.
    Case A — New user: collect student ID, department, password.
    Case B — Existing user: treat as login with full post-login routing.
    """
    if not request.user.is_authenticated:
        messages.error(request, 'Google Sign-In did not complete. Please try again.')
        return redirect('landing')

    google_email = (request.user.email or '').lower()
    if not google_email:
        messages.error(request, 'Could not retrieve your email from Google.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, full_name, role FROM users WHERE email = %s", (google_email,))
        existing_user = cursor.fetchone()

        # ── Case B: existing account ──────────────────────────────────
        if existing_user:
            if existing_user['role'] != 'student':
                messages.error(request, 'This email is registered under a non-student role.')
                return redirect('login')

            request.session['user_id']   = existing_user['id']
            request.session['role']      = 'student'
            request.session['full_name'] = existing_user['full_name']

            ResetAgent().run()
            semester = get_current_semester(cursor)
            if not semester:
                messages.error(request, 'No active semester configured.')
                return redirect('landing')

            cursor.execute(
                "SELECT final_status FROM questionnaire_responses "
                "WHERE student_id = %s AND semester = %s",
                (existing_user['id'], semester),
            )
            qr = cursor.fetchone()

            if qr and qr['final_status']:
                return redirect('student_dashboard')
            else:
                return redirect('chatbot')

        # ── Case A: new user ──────────────────────────────────────────
        google_full_name = (
            request.user.get_full_name() or request.user.username
            or google_email.split('@')[0]
        )

        if request.method == 'GET':
            return render(request, 'register_google.html', {
                'google_email': google_email, 'google_full_name': google_full_name,
            })

        student_id  = request.POST.get('student_id', '').strip()
        department  = request.POST.get('department', '').strip()
        password    = request.POST.get('password',   '').strip()
        confirm     = request.POST.get('confirm',     '').strip()
        valid_depts = {'CSE', 'EEE', 'ENG', 'ECO', 'BBA'}

        form_data = {
            'google_email':     google_email,
            'google_full_name': google_full_name,
            'student_id':       student_id,
            'department':       department,
        }

        if not all([student_id, department, password, confirm]):
            messages.error(request, 'All fields are required.')
            return render(request, 'register_google.html', form_data)
        if department not in valid_depts:
            messages.error(request, 'Please select a valid department.')
            return render(request, 'register_google.html', form_data)
        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'register_google.html', form_data)
        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'register_google.html', form_data)

        hashed = make_password(password)
        cursor.execute("SELECT id FROM users WHERE email = %s", (google_email,))
        if cursor.fetchone():
            messages.error(request, 'An account with this email already exists.')
            return redirect('login')

        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('student', %s, %s, %s) RETURNING id",
            (google_full_name, google_email, hashed),
        )
        new_user_id = cursor.fetchone()['id']
        cursor.execute(
            "INSERT INTO students (user_id, student_id, department) VALUES (%s, %s, %s)",
            (new_user_id, student_id, department),
        )
        conn.commit()
        messages.success(request, 'Registration complete! Please log in.')
        return redirect('login')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An unexpected error occurred. ({exc})')
        return redirect('landing')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
# LOGOUT  GET /logout/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def logout_view(request):
    """Clear the session and return to landing."""
    request.session.flush()
    messages.success(request, 'You have been logged out successfully.')
    return redirect('landing')

# ─────────────────────────────────────────────────────────────────────
#  QUESTION BANK
#  Single source of truth for all 26 questions.
#  Order MUST match scaler.pkl's fitted feature order:
#  PSS1-10, GAD1-7, PHQ1-9.
#  Each entry: (db_column, scale_type, question_text, symptom_label)
# ─────────────────────────────────────────────────────────────────────

QUESTIONS = [
    # PSS-10  (0=Never … 4=Very Often)
    ('pss1',  'pss', 'During a semester, how often have you felt upset because of something that happened in your academic affairs?',                                                                                                        'Distress'),
    ('pss2',  'pss', 'During a semester, how often have you felt unable to control important things in your academic affairs?',                                                                                                              'Loss of Control'),
    ('pss3',  'pss', 'During a semester, how often have you felt nervous and stressed due to academic pressure?',                                                                                                                            'Stress'),
    ('pss4',  'pss', 'During a semester, how often have you felt unable to cope with all the mandatory academic activities (e.g., assignments, quizzes, exams)?',                                                                            'Inability to Cope'),
    ('pss5',  'pss', 'During a semester, how often have you felt confident about your ability to handle your academic or university problems?',                                                                                              'Low Self-Confidence'),
    ('pss6',  'pss', 'During a semester, how often have you felt that things in your academic life were going your way?',                                                                                                                    'Lack of Progress'),
    ('pss7',  'pss', 'During a semester, how often have you been able to control irritations in your academic or university affairs?',                                                                                                       'Poor Irritation Control'),
    ('pss8',  'pss', 'During a semester, how often have you felt that your academic performance was at its best?',                                                                                                                           'Low Academic Self-Efficacy'),
    ('pss9',  'pss', 'During a semester, how often have you felt angry due to poor performance or low grades that were beyond your control?',                                                                                                'Anger / Frustration'),
    ('pss10', 'pss', 'During a semester, how often have you felt that academic difficulties were piling up so high that you could not overcome them?',                                                                                       'Overwhelm'),
    # GAD-7  (0=Not at all … 3=Nearly every day)
    ('gad1',  'gad', 'During a semester, how often have you felt nervous, anxious, or on edge due to academic pressure?',                                                                                                                   'Anxiety / Nervousness'),
    ('gad2',  'gad', 'During a semester, how often have you been unable to stop worrying about your academic affairs?',                                                                                                                     'Uncontrollable Worry'),
    ('gad3',  'gad', 'During a semester, how often have you had trouble relaxing due to academic pressure?',                                                                                                                                'Inability to Relax'),
    ('gad4',  'gad', 'During a semester, how often have you been easily annoyed or irritated because of academic pressure?',                                                                                                                'Irritability'),
    ('gad5',  'gad', 'During a semester, how often have you worried too much about academic affairs?',                                                                                                                                      'Excessive Worry'),
    ('gad6',  'gad', 'During a semester, how often have you been so restless due to academic pressure that it is hard to sit still?',                                                                                                       'Restlessness'),
    ('gad7',  'gad', 'During a semester, how often have you felt afraid, as if something awful might happen?',                                                                                                                              'Fear / Apprehension'),
    # PHQ-9  (0=Not at all … 3=Nearly every day)
    ('phq1',  'phq', 'During the semester, how often have you had little interest or pleasure in doing things?',                                                                                                                            'Anhedonia (Loss of Interest / Pleasure)'),
    ('phq2',  'phq', 'During the semester, how often have you felt down, depressed, or hopeless?',                                                                                                                                         'Depressed Mood / Hopelessness'),
    ('phq3',  'phq', 'During the semester, how often have you had trouble falling asleep, staying asleep, or sleeping too much?',                                                                                                           'Sleep Disturbance'),
    ('phq4',  'phq', 'During the semester, how often have you felt tired or had little energy?',                                                                                                                                            'Fatigue / Low Energy'),
    ('phq5',  'phq', 'During the semester, how often have you had a poor appetite or overeaten?',                                                                                                                                           'Appetite Disturbance'),
    ('phq6',  'phq', 'During the semester, how often have you felt bad about yourself, or felt that you are a failure or have let yourself or your family down?',                                                                           'Low Self-Worth / Guilt'),
    ('phq7',  'phq', 'During the semester, how often have you had trouble concentrating on things, such as reading books or watching television?',                                                                                          'Concentration Difficulty'),
    ('phq8',  'phq', 'During the semester, how often have you moved or spoken so slowly that other people could notice? Or how often have you been moving much more than usual because you felt restless?',                                  'Psychomotor Agitation / Retardation'),
    ('phq9',  'phq', 'During the semester, how often have you had thoughts that you would be better off dead or of hurting yourself?',                                                                                                      'Suicidal Ideation / Self-Harm Thoughts'),
]

# Column names in exact feature order — used for ML answer extraction
QUESTION_COLS    = [q[0] for q in QUESTIONS]
QUESTION_SYMPTOMS = {q[0]: q[3] for q in QUESTIONS}

# Answer button labels per scale
SCALE_LABELS = {
    'pss': ['Never', 'Almost Never', 'Sometimes', 'Fairly Often', 'Very Often'],
    'gad': ['Not at all', 'Several days', 'More than half the days', 'Nearly every day'],
    'phq': ['Not at all', 'Several days', 'More than half the days', 'Nearly every day'],
}

# Maximum valid answer per scale (inclusive)
SCALE_MAX = {'pss': 4, 'gad': 3, 'phq': 3}


def _next_unanswered(qr_row):
    """
    Return the index (0–25) of the first NULL column in a
    questionnaire_responses row, or None if all 26 are filled.
    Returns 0 if qr_row is None (student hasn't started yet).
    """
    if qr_row is None:
        return 0
    for i, col in enumerate(QUESTION_COLS):
        if qr_row[col] is None:
            return i
    return None

def _build_responses(qr_row):
    """
    Given a questionnaire_responses DB row, return a list of 26 dicts
    suitable for display in templates.  Used by both student status and
    professional appointment/detail views.
    """
    scale_answer_labels = {
        'pss': SCALE_LABELS['pss'],
        'gad': SCALE_LABELS['gad'],
        'phq': SCALE_LABELS['phq'],
    }
    responses = []
    for i, (col, scale, text, symptom) in enumerate(QUESTIONS):
        raw = qr_row[col] if qr_row else None
        if raw is None:
            continue
        answer_label = scale_answer_labels[scale][raw]
        responses.append({
            'number':       i + 1,
            'col':          col,
            'scale':        scale.upper(),
            'symptom':      symptom,
            'text':         text,
            'raw':          raw,
            'answer_label': answer_label,
            'severity':     raw,
        })
    return responses

# ─────────────────────────────────────────────
#  CHATBOT  GET/POST /chatbot/
# ─────────────────────────────────────────────
@require_http_methods(['GET', 'POST'])
def chatbot(request):
    """
    GET  — Show the next unanswered question.
    POST — Save the submitted answer; run ML after the 26th.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student to access the assessment.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured. Please contact Admin IT.')
            return redirect('landing')

        # ── GET ───────────────────────────────────────────────────────
        if request.method == 'GET':
            cursor.execute(
                "SELECT * FROM questionnaire_responses "
                "WHERE student_id = %s AND semester = %s",
                (user_id, semester),
            )
            qr = cursor.fetchone()

            # If already fully answered, go straight to result
            if qr and qr['final_status']:
                return redirect('chatbot_result')

            idx = _next_unanswered(qr)
            # Shouldn't be None here (checked above), but guard anyway
            if idx is None:
                return redirect('chatbot_result')

            col, scale, text, symptom = QUESTIONS[idx]
            labels = list(enumerate(SCALE_LABELS[scale]))

            return render(request, 'chatbot.html', {
                'show_result': False,
                'q_col':       col,
                'q_index':     idx,
                'q_number':    idx + 1,
                'q_total':     26,
                'q_text':      text,
                'q_symptom':   symptom,
                'q_scale':     scale.upper(),
                'labels':      labels,
                'progress':    int((idx / 26) * 100),
            })

        # ── POST ──────────────────────────────────────────────────────
        col        = request.POST.get('col',    '').strip()
        answer_raw = request.POST.get('answer', '').strip()

        # Whitelist: col must be one of our 26 known column names
        if col not in QUESTION_COLS:
            messages.error(request, 'Invalid question submitted.')
            return redirect('chatbot')

        q_entry = QUESTIONS[QUESTION_COLS.index(col)]
        scale   = q_entry[1]
        max_val = SCALE_MAX[scale]

        try:
            answer = int(answer_raw)
            if not (0 <= answer <= max_val):
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, 'Please select a valid answer.')
            return redirect('chatbot')

        # ── Upsert ────────────────────────────────────────────────────
        cursor.execute(
            "SELECT id FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        existing = cursor.fetchone()

        if existing:
            # Update just the submitted column
            cursor.execute(
                f"UPDATE questionnaire_responses SET {col} = %s "
                f"WHERE student_id = %s AND semester = %s",
                (answer, user_id, semester),
            )
        else:
            # First answer — insert the row; all other columns stay NULL
            cursor.execute(
                f"INSERT INTO questionnaire_responses "
                f"    (student_id, semester, {col}) "
                f"VALUES (%s, %s, %s)",
                (user_id, semester, answer),
            )
        conn.commit()

        # ── Check completion ──────────────────────────────────────────
        cursor.execute(
            "SELECT * FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()

        if _next_unanswered(qr) is not None:
            # More questions remain
            return redirect('chatbot')

        # ── All 26 answered — run the model ───────────────────────────
        answers = [qr[c] for c in QUESTION_COLS]
        if any(v is None for v in answers):
            messages.error(request, 'Some answers are missing.')
            return redirect('chatbot')

        status = ml_predict(answers)
        cursor.execute(
            "UPDATE questionnaire_responses SET final_status = %s "
            "WHERE student_id = %s AND semester = %s",
            (status, user_id, semester),
        )
        conn.commit()
        return redirect('chatbot_result')

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  CHATBOT RESULT  GET /chatbot/result/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def chatbot_result(request):
    """Result screen after all 26 answers are submitted."""
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            return redirect('landing')

        cursor.execute(
            "SELECT final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        row = cursor.fetchone()

        if not row or not row['final_status']:
            # Assessment incomplete — go back to chatbot
            return redirect('chatbot')

        final_status        = row['final_status']
        # Consume triage outcome from session (set by request-professional view)
        triage_done         = request.session.pop('triage_done',         False)
        triage_assigned     = request.session.pop('triage_assigned',     False)
        triage_professional = request.session.pop('triage_professional', '')

        return render(request, 'chatbot.html', {
            'show_result':         True,
            'final_status':        final_status,
            'triage_done':         triage_done,
            'triage_assigned':     triage_assigned,
            'triage_professional': triage_professional,
            'q_total':             26,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REQUEST PROFESSIONAL  POST /chatbot/request-professional/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def chatbot_request_professional(request):
    """Run Triage Agent for Critical students."""
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        return redirect('landing')

    try:
        result = TriageAgent().run(user_id)
    except Exception:
        result = {'assigned': False}

    request.session['triage_done']         = True
    request.session['triage_assigned']     = result.get('assigned', False)
    request.session['triage_professional'] = result.get('professional_name', '')

    return redirect('chatbot_result')

# ─────────────────────────────────────────────
#  STUDENT DASHBOARD  GET /student/dashboard/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def student_dashboard(request):
    """
    Student hub page — three cards linking to Status, Help, Events.
    Guards: must be logged in as student AND have a completed assessment.
    If the assessment is not done yet, redirect back to the chatbot.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('landing')

        # Guard: if assessment not complete or was reset, send to chatbot
        cursor.execute(
            "SELECT final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()

        if not qr or not qr['final_status']:
            return redirect('chatbot')

        return render(request, 'student/dashboard.html', {
            'full_name': request.session.get('full_name', 'Student'),
            'semester':  semester,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MENTAL HEALTH STATUS  GET /student/status/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def student_status(request):
    """
    Shows:
      1. Classification badge (Stable / Challenged / Critical).
      2. Table of all 26 responses, each paired with its symptom label.
      3. Top-symptom highlight cards (top 3 most impactful symptoms).
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('landing')

        cursor.execute(
            "SELECT * FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()

        # No complete assessment → redirect to chatbot
        if not qr or not qr['final_status']:
            return redirect('chatbot')

        final_status = qr['final_status']
        responses    = _build_responses(qr)

        # ── Top 3 symptoms by severity score ──────────────────────────
        # Sort by severity descending, take top 3
        top_symptoms = sorted(responses, key=lambda r: r['severity'], reverse=True)[:3]

        return render(request, 'student/status.html', {
            'full_name':    request.session.get('full_name', 'Student'),
            'semester':     semester,
            'final_status': final_status,
            'responses':    responses,
            'top_symptoms': top_symptoms,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REQUEST MENTAL HEALTH HELP  GET /student/help/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def student_help(request):
    """
    Lists all Mental Health Professionals with their availability
    and the correct button state for this student.
 
    Button logic:
      - Stable students         → no button shown
      - No active appointment
        AND (Challenged or Critical)  → Request button per professional
      - Pending appointment     → Cancel Request button
      - Accepted appointment    → "Currently in Treatment" status
                                   showing professional name + scheduled_at
      - Declined or Completed   → Request button (can request again)
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('landing')

        # Student's classification for this semester
        cursor.execute(
            "SELECT final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()

        if not qr or not qr['final_status']:
            return redirect('chatbot')

        final_status = qr['final_status']

        # Student's current active appointment (pending or accepted)
        cursor.execute(
            """
            SELECT a.id, a.status, a.scheduled_at,
                   u.full_name AS professional_name, a.professional_id
            FROM   appointments a
            JOIN   users u ON u.id = a.professional_id
            WHERE  a.student_id = %s AND a.status IN ('pending','accepted')
            ORDER  BY a.id DESC LIMIT 1
            """,
            (user_id,)
        )
        active_appt = cursor.fetchone()

        # All professionals with their current active student count
        cursor.execute(
            """
            SELECT  u.id, u.full_name,
                    COUNT(a.id) AS active_count,
                    CASE WHEN COUNT(a.id) < 12 THEN TRUE ELSE FALSE END AS is_available
            FROM    users u
            LEFT JOIN appointments a ON a.professional_id = u.id AND a.status = 'accepted'
            WHERE   u.role = 'professional'
            GROUP BY u.id, u.full_name
            ORDER BY u.full_name ASC
            """
        )
        professionals = cursor.fetchall()

        return render(request, 'student/help.html', {
            'full_name':     request.session.get('full_name', 'Student'),
            'semester':      semester,
            'final_status':  final_status,
            'active_appt':   active_appt,
            'professionals': professionals,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REQUEST APPOINTMENT  POST /student/help/request/<professional_id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def student_help_request(request, professional_id):
    """
    Manually submit a help request to a specific professional.
    Only available to Challenged or Critical students with no active appointment.
    Inserts a pending appointment row.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            return redirect('landing')

        # Guard: student must be Challenged or Critical
        cursor.execute(
            "SELECT final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()
        if not qr or qr['final_status'] not in ('Challenged', 'Critical'):
            messages.error(request, 'Only Challenged or Critical students can request help.')
            return redirect('student_help')

        # Guard: no existing active appointment
        cursor.execute(
            "SELECT id FROM appointments WHERE student_id = %s "
            "AND status IN ('pending','accepted')",
            (user_id,)
        )
        if cursor.fetchone():
            messages.error(request, 'You already have an active appointment.')
            return redirect('student_help')

        # Guard: professional exists and is available
        cursor.execute(
            """
            SELECT u.id, COUNT(a.id) AS active_count
            FROM   users u
            LEFT JOIN appointments a ON a.professional_id = u.id AND a.status = 'accepted'
            WHERE  u.id = %s AND u.role = 'professional'
            GROUP BY u.id
            """,
            (professional_id,)
        )
        prof = cursor.fetchone()
        if not prof:
            messages.error(request, 'Professional not found.')
            return redirect('student_help')
        if prof['active_count'] >= 12:
            messages.error(request, 'That professional is currently at full capacity.')
            return redirect('student_help')

        cursor.execute(
            "INSERT INTO appointments (student_id, professional_id, status) "
            "VALUES (%s, %s, 'pending')",
            (user_id, professional_id)
        )
        conn.commit()
        messages.success(request, 'Your request has been submitted successfully.')
        return redirect('student_help')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('student_help')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  CANCEL REQUEST  POST /student/help/cancel-request/<appointment_id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def student_help_cancel(request, appointment_id):
    """
    Cancel a pending appointment request.
    Hard-deletes the appointment row so the student can submit
    a new request immediately.
    Only works on appointments with status = 'pending' that
    belong to this student.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Verify the appointment belongs to this student and is pending
        cursor.execute(
            "SELECT id FROM appointments "
            "WHERE id = %s AND student_id = %s AND status = 'pending'",
            (appointment_id, user_id)
        )
        if not cursor.fetchone():
            messages.error(request, 'Appointment not found or cannot be cancelled.')
            return redirect('student_help')

        cursor.execute(
            "DELETE FROM appointments WHERE id = %s AND student_id = %s",
            (appointment_id, user_id)
        )
        conn.commit()
        messages.success(request, 'Your request has been cancelled.')
        return redirect('student_help')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('student_help')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MENTAL HEALTH EVENTS  GET /student/events/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def student_events(request):
    """
    Lists all upcoming mental health events ordered by date ascending.
    For each event, checks whether this student has already RSVP'd
    so the template can show the correct button (RSVP / Cancel RSVP).
    Shows an empty-state message if no events exist.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        messages.error(request, 'Please log in as a student.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('landing')

        # All events ordered by date ascending
        cursor.execute(
            "SELECT id, title, date, time, venue, description, rsvp_count "
            "FROM events ORDER BY date ASC, time ASC"
        )
        events_raw = cursor.fetchall()
        # Which events has this student RSVPd to?
        cursor.execute("SELECT event_id FROM event_rsvps WHERE student_id = %s", (user_id,))
        rsvped_ids = {row['event_id'] for row in cursor.fetchall()}

        # Attach has_rsvpd flag to each event
        events = []
        for ev in events_raw:
            events.append({
                'id':         ev['id'],
                'title':      ev['title'],
                'date':       ev['date'],
                'time':       ev['time'],
                'venue':      ev['venue'],
                'description': ev['description'],
                'rsvp_count': ev['rsvp_count'],
                'has_rsvpd':  ev['id'] in rsvped_ids,
            })

        return render(request, 'student/events.html', {
            'full_name': request.session.get('full_name', 'Student'),
            'semester':  semester,
            'events':    events,
        })
 
    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  RSVP  POST /student/events/rsvp/<event_id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def student_events_rsvp(request, event_id):
    """
    RSVP to an event:
      - Insert a row into event_rsvps.
      - Increment events.rsvp_count by 1.
    Silently ignores duplicate RSVPs (ON CONFLICT DO NOTHING).
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Verify event exists
        cursor.execute("SELECT id FROM events WHERE id = %s", (event_id,))
        if not cursor.fetchone():
            messages.error(request, 'Event not found.')
            return redirect('student_events')

        # Insert RSVP (ignore if already exists)
        cursor.execute(
            "INSERT INTO event_rsvps (student_id, event_id) "
            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, event_id)
        )

        # Only increment if a row was actually inserted
        if cursor.rowcount > 0:
            cursor.execute(
                "UPDATE events SET rsvp_count = rsvp_count + 1 WHERE id = %s", (event_id,)
            )
        conn.commit()
        messages.success(request, "You're going! RSVP confirmed.")
        return redirect('student_events')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('student_events')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  CANCEL RSVP  POST /student/events/cancel-rsvp/<event_id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def student_events_cancel_rsvp(request, event_id):
    """
    Cancel an RSVP:
      - Delete the row from event_rsvps.
      - Decrement events.rsvp_count by 1 (floor at 0 for safety).
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'student':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM event_rsvps WHERE student_id = %s AND event_id = %s",
            (user_id, event_id)
        )

        # Only decrement if a row was actually deleted
        if cursor.rowcount > 0:
            cursor.execute(
                "UPDATE events SET rsvp_count = GREATEST(rsvp_count - 1, 0) WHERE id = %s",
                (event_id,)
            )
        conn.commit()
        messages.success(request, 'RSVP cancelled.')
        return redirect('student_events')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('student_events')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  PROFESSIONAL DASHBOARD  GET /professional/dashboard/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def professional_dashboard(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        messages.error(request, 'Please log in as a Mental Health Professional.')
        return redirect('landing')

    return render(request, 'professional/dashboard.html', {
        'full_name': request.session.get('full_name', 'Professional'),
    })

# ─────────────────────────────────────────────
#  APPOINTMENTS  GET /professional/appointments/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def professional_appointments(request):
    """
    Two sections, both paginated 10 per page:

    Section 1 — Currently Treating (status = 'accepted'):
      student name, student_id, department, scheduled_at
      + View button + Release button

    Section 2 — Pending Requests (status = 'pending'):
      each student's full 26-question responses with symptom labels
      + Accept form (datetime input) + Decline button
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        messages.error(request, 'Please log in as a Mental Health Professional.')
        return redirect('landing')

    PER_PAGE = 10

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)

        # ── Section 1: Currently Treating ────────────────────────────
        page_t = max(1, int(request.GET.get('page_t', 1)))
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM   appointments a
            WHERE  a.professional_id = %s AND a.status = 'accepted'
            """,
            (user_id,)
        )
        total_treating  = cursor.fetchone()['total']
        pages_treating  = max(1, (total_treating + PER_PAGE - 1) // PER_PAGE)
        page_t          = min(page_t, pages_treating)

        cursor.execute(
            """
            SELECT a.id        AS appt_id,
                   a.scheduled_at,
                   u.full_name AS student_name,
                   s.student_id,
                   s.department
            FROM   appointments a
            JOIN   users    u ON u.id       = a.student_id
            JOIN   students s ON s.user_id  = a.student_id
            WHERE  a.professional_id = %s AND a.status = 'accepted'
            ORDER  BY a.scheduled_at ASC NULLS LAST, a.id ASC
            LIMIT  %s OFFSET %s
            """,
            (user_id, PER_PAGE, (page_t - 1) * PER_PAGE)
        )
        treating_rows = cursor.fetchall()

        # ── Section 2: Pending Requests ───────────────────────────────
        page_p = max(1, int(request.GET.get('page_p', 1)))
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM   appointments a
            WHERE  a.professional_id = %s AND a.status = 'pending'
            """,
            (user_id,)
        )
        total_pending = cursor.fetchone()['total']
        pages_pending = max(1, (total_pending + PER_PAGE - 1) // PER_PAGE)
        page_p        = min(page_p, pages_pending)

        cursor.execute(
            """
            SELECT a.id        AS appt_id,
                   u.full_name AS student_name,
                   s.student_id,
                   s.department,
                   a.student_id AS student_user_id
            FROM   appointments a
            JOIN   users    u ON u.id      = a.student_id
            JOIN   students s ON s.user_id = a.student_id
            WHERE  a.professional_id = %s AND a.status = 'pending'
            ORDER  BY a.id ASC
            LIMIT  %s OFFSET %s
            """,
            (user_id, PER_PAGE, (page_p - 1) * PER_PAGE)
        )
        pending_rows_raw = cursor.fetchall()

        # Attach 26-response data to each pending row
        pending_rows = []
        for row in pending_rows_raw:
            if semester:
                cursor.execute(
                    "SELECT * FROM questionnaire_responses "
                    "WHERE student_id = %s AND semester = %s",
                    (row['student_user_id'], semester)
                )
                qr = cursor.fetchone()
                row_responses = _build_responses(qr) if qr else []
            else:
                row_responses = []

            pending_rows.append({
                'appt_id':      row['appt_id'],
                'student_name': row['student_name'],
                'student_id':   row['student_id'],
                'department':   row['department'],
                'responses':    row_responses,
            })

        # Pagination window helper (7-page window)
        def page_range(current, total):
            half  = 3
            start = max(1, current - half)
            end   = min(total, start + 6)
            start = max(1, end - 6)
            return range(start, end + 1)

        return render(request, 'professional/appointments.html', {
            'full_name':      request.session.get('full_name', 'Professional'),
            'semester':       semester,
            # treating
            'treating_rows':  treating_rows,
            'page_t':         page_t,
            'pages_treating': pages_treating,
            'range_t':        page_range(page_t, pages_treating),
            # pending
            'pending_rows':   pending_rows,
            'page_p':         page_p,
            'pages_pending':  pages_pending,
            'range_p':        page_range(page_p, pages_pending),
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  ACCEPT  POST /professional/appointments/accept/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def professional_appointments_accept(request, appointment_id):
    """
    Validates:
      1. The appointment belongs to this professional and is pending.
      2. Professional has fewer than 12 accepted appointments.
      3. Proposed scheduled_at does not conflict with any existing
         accepted appointment's scheduled_at for this professional.
    On success: sets status='accepted', stores scheduled_at.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        return redirect('landing')

    scheduled_at_str = request.POST.get('scheduled_at', '').strip()
    if not scheduled_at_str:
        messages.error(request, 'Please provide a session date and time.')
        return redirect('professional_appointments')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Verify appointment belongs to this professional and is pending
        cursor.execute(
            "SELECT id FROM appointments "
            "WHERE id = %s AND professional_id = %s AND status = 'pending'",
            (appointment_id, user_id)
        )
        if not cursor.fetchone():
            messages.error(request, 'Appointment not found or already processed.')
            return redirect('professional_appointments')

        # Check 12-student cap
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM appointments "
            "WHERE professional_id = %s AND status = 'accepted'",
            (user_id,)
        )
        if cursor.fetchone()['cnt'] >= 12:
            messages.error(
                request,
                'You have reached the maximum of 12 active students. '
                'Please release a student before accepting new requests.'
            )
            return redirect('professional_appointments')

        # Parse the submitted datetime
        from datetime import datetime
        try:
            # HTML datetime-local format: "YYYY-MM-DDTHH:MM"
            scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            try:
                scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%d %H:%M')
            except ValueError:
                messages.error(request, 'Invalid date/time format. Please try again.')
                return redirect('professional_appointments')

        # ── Weekly recurring conflict check ───────────────────────────
        # Each appointment is a 2-hour weekly slot on a fixed day + time.
        # A conflict exists if any existing accepted appointment falls on
        # the SAME day of the week AND its start time is within 2 hours
        # of the proposed start time (i.e. the slots would overlap).
        #
        # Example: existing slot = Monday 10:00 (runs until 12:00).
        #   Proposed Monday 09:30 → conflict (10:00 - 09:30 = 30 min < 2 h).
        #   Proposed Monday 12:00 → no conflict (exactly 2 h apart).
        #   Proposed Tuesday 10:00 → no conflict (different day).
        cursor.execute(
            """
            SELECT id, scheduled_at FROM appointments
            WHERE  professional_id = %s
            AND    status          = 'accepted'
            AND    scheduled_at    IS NOT NULL
            AND    EXTRACT(DOW FROM scheduled_at) = EXTRACT(DOW FROM %s::timestamp)
            AND    ABS(EXTRACT(EPOCH FROM (
                       scheduled_at::time - %s::time
                   ))) < 7200
            """,
            (user_id, scheduled_at, scheduled_at)
        )
        conflict = cursor.fetchone()
        if conflict:
            existing_dt = conflict['scheduled_at']
            day_name    = existing_dt.strftime('%A')
            time_str    = existing_dt.strftime('%I:%M %p')
            messages.error(
                request,
                f'You already have a recurring session every {day_name} at '
                f'{time_str} (2-hour slot). The proposed time conflicts with '
                f'that slot. Please choose a different day or time.'
            )
            return redirect('professional_appointments')

        # Accept the appointment
        cursor.execute(
            "UPDATE appointments SET status = 'accepted', scheduled_at = %s "
            "WHERE id = %s AND professional_id = %s",
            (scheduled_at, appointment_id, user_id)
        )
        conn.commit()
        messages.success(request, 'Appointment accepted and session time set.')
        return redirect('professional_appointments')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('professional_appointments')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DECLINE  POST /professional/appointments/decline/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def professional_appointments_decline(request, appointment_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE appointments SET status = 'declined' "
            "WHERE id = %s AND professional_id = %s AND status = 'pending'",
            (appointment_id, user_id)
        )
        if cursor.rowcount == 0:
            messages.error(request, 'Appointment not found or already processed.')
        else:
            conn.commit()
            messages.success(request, 'Request declined.')
        return redirect('professional_appointments')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('professional_appointments')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  RELEASE  POST /professional/appointments/release/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def professional_appointments_release(request, appointment_id):
    """Sets status='completed', freeing the slot toward the 12-cap."""
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE appointments SET status = 'completed' "
            "WHERE id = %s AND professional_id = %s AND status = 'accepted'",
            (appointment_id, user_id)
        )
        if cursor.rowcount == 0:
            messages.error(request, 'Appointment not found or not currently active.')
        else:
            conn.commit()
            messages.success(request, 'Student released. Slot is now available.')
        return redirect('professional_appointments')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('professional_appointments')
    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  RESCHEDULE  POST /professional/appointments/reschedule/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def professional_appointments_reschedule(request, appointment_id):
    """
    Update the scheduled_at timestamp for an existing accepted appointment.
    Applies the same weekly-recurring conflict check as the accept view —
    checks that the proposed day-of-week + time does not overlap any other
    accepted appointment for this professional (excluding the one being
    rescheduled itself).
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        return redirect('landing')

    scheduled_at_str = request.POST.get('scheduled_at', '').strip()
    if not scheduled_at_str:
        messages.error(request, 'Please provide a new session date and time.')
        return redirect('professional_appointments')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Verify appointment belongs to this professional and is accepted
        cursor.execute(
            "SELECT id FROM appointments "
            "WHERE id = %s AND professional_id = %s AND status = 'accepted'",
            (appointment_id, user_id)
        )
        if not cursor.fetchone():
            messages.error(request, 'Appointment not found or not currently active.')
            return redirect('professional_appointments')

        # Parse datetime
        from datetime import datetime
        try:
            scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            try:
                scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%d %H:%M')
            except ValueError:
                messages.error(request, 'Invalid date/time format. Please try again.')
                return redirect('professional_appointments')

        # Weekly recurring conflict check — exclude this appointment itself
        cursor.execute(
            """
            SELECT id, scheduled_at FROM appointments
            WHERE  professional_id = %s
            AND    status          = 'accepted'
            AND    id             != %s
            AND    scheduled_at    IS NOT NULL
            AND    EXTRACT(DOW FROM scheduled_at) = EXTRACT(DOW FROM %s::timestamp)
            AND    ABS(EXTRACT(EPOCH FROM (
                       scheduled_at::time - %s::time
                   ))) < 7200
            """,
            (user_id, appointment_id, scheduled_at, scheduled_at)
        )
        conflict = cursor.fetchone()
        if conflict:
            existing_dt = conflict['scheduled_at']
            day_name    = existing_dt.strftime('%A')
            time_str    = existing_dt.strftime('%I:%M %p')
            messages.error(
                request,
                f'You already have a recurring session every {day_name} at '
                f'{time_str} (2-hour slot). The proposed time conflicts. '
                f'Please choose a different day or time.'
            )
            return redirect('professional_appointments')

        # Update the appointment
        cursor.execute(
            "UPDATE appointments SET scheduled_at = %s "
            "WHERE id = %s AND professional_id = %s",
            (scheduled_at, appointment_id, user_id)
        )
        conn.commit()
        messages.success(
            request,
            f'Session rescheduled to every '
            f'{scheduled_at.strftime("%A")} at '
            f'{scheduled_at.strftime("%I:%M %p")}.'
        )
        return redirect('professional_appointments')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('professional_appointments')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  VIEW STUDENT  GET /professional/appointments/view/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def professional_appointments_view(request, appointment_id):
    """
    Student detail page — only accessible for accepted appointments
    belonging to this professional.
    Shows: student info, full 26-response table with symptom labels,
           top-5 symptoms, scheduled_at.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        messages.error(request, 'Please log in as a Mental Health Professional.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Verify this appointment belongs to this professional and is accepted
        cursor.execute(
            """
            SELECT a.id, a.scheduled_at, a.student_id AS student_user_id,
                   u.full_name AS student_name,
                   s.student_id, s.department
            FROM   appointments a
            JOIN   users    u ON u.id      = a.student_id
            JOIN   students s ON s.user_id = a.student_id
            WHERE  a.id = %s AND a.professional_id = %s AND a.status = 'accepted'
            """,
            (appointment_id, user_id)
        )
        appt = cursor.fetchone()

        if not appt:
            messages.error(request, 'Appointment not found or not currently active.')
            return redirect('professional_appointments')

        semester = get_current_semester(cursor)

        # Fetch the student's questionnaire responses
        qr = None
        if semester:
            cursor.execute(
                "SELECT * FROM questionnaire_responses "
                "WHERE student_id = %s AND semester = %s",
                (appt['student_user_id'], semester)
            )
            qr = cursor.fetchone()

        responses    = _build_responses(qr) if qr else []
        top_symptoms = sorted(responses, key=lambda r: r['severity'], reverse=True)[:5]

        return render(request, 'professional/student_detail.html', {
            'full_name':      request.session.get('full_name', 'Professional'),
            'semester':       semester,
            'appt':           appt,
            'responses':      responses,
            'top_symptoms':   top_symptoms,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  PROFESSIONAL STATS  GET /professional/stats/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def professional_stats(request):
    """
    Aggregated mental health analytics page.
    Calls AnalyticsAgent at the top of every load.
    No individual student data — all aggregated and anonymised.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'professional':
        messages.error(request, 'Please log in as a Mental Health Professional.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('professional_dashboard')

        # ── Run Analytics Agent ───────────────────────────────────────
        from core.agents.analytics_agent import AnalyticsAgent
        alerts = AnalyticsAgent().run(semester)

        # ── Overall status distribution ───────────────────────────────
        cursor.execute(
            """
            SELECT final_status, COUNT(*) AS cnt
            FROM   questionnaire_responses
            WHERE  semester        = %s
            AND    final_status    IS NOT NULL
            GROUP  BY final_status
            """,
            (semester,)
        )
        dist_rows = cursor.fetchall()
        total_assessed = sum(r['cnt'] for r in dist_rows)
        distribution   = {r['final_status']: r['cnt'] for r in dist_rows}
        stable     = distribution.get('Stable',     0)
        challenged = distribution.get('Challenged', 0)
        critical   = distribution.get('Critical',   0)

        def pct(n):
            return round((n / total_assessed * 100), 1) if total_assessed else 0

        # ── Per-department breakdown ──────────────────────────────────
        cursor.execute(
            """
            SELECT s.department,
                   COUNT(*)                                                        AS total,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Stable')             AS stable,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Challenged')         AS challenged,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Critical')           AS critical
            FROM   questionnaire_responses qr
            JOIN   students s ON s.user_id = qr.student_id
            WHERE  qr.semester        = %s
            AND    qr.final_status    IS NOT NULL
            GROUP  BY s.department
            ORDER  BY s.department ASC
            """,
            (semester,)
        )
        dept_rows = cursor.fetchall()

        # ── Top symptoms by frequency ─────────────────────────────────
        # Count how many students scored > 0 on each question column
        symptom_counts = []
        for col, scale, text, symptom in QUESTIONS:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM   questionnaire_responses
                WHERE  semester        = %s
                AND    final_status    IS NOT NULL
                AND    {col} > 0
                """,
                (semester,)
            )
            row = cursor.fetchone()
            cnt = row['cnt'] if row else 0
            symptom_counts.append({
                'symptom': symptom,
                'scale':   scale.upper(),
                'count':   cnt,
                'col':     col,
            })
        symptom_counts.sort(key=lambda x: x['count'], reverse=True)
        top_symptoms = symptom_counts[:10]

        # ── Historical semester trends ─────────────────────────────────
        # Past semesters: read from semester_stats (compiled by Reset Agent).
        # Current semester: read live from questionnaire_responses.
        cursor.execute(
            """
            SELECT semester, total, stable, challenged, critical
            FROM   semester_stats
            UNION ALL
            SELECT %s                                                               AS semester,
                   COUNT(*)                                                         AS total,
                   COUNT(*) FILTER (WHERE final_status = 'Stable')                 AS stable,
                   COUNT(*) FILTER (WHERE final_status = 'Challenged')              AS challenged,
                   COUNT(*) FILTER (WHERE final_status = 'Critical')               AS critical
            FROM   questionnaire_responses
            WHERE  semester        = %s
            AND    final_status    IS NOT NULL
            ORDER  BY
                CAST(SPLIT_PART(semester, ' ', 2) AS INTEGER) DESC,
                CASE SPLIT_PART(semester, ' ', 1)
                    WHEN 'Spring' THEN 1
                    WHEN 'Summer' THEN 2
                    WHEN 'Fall'   THEN 3
                    ELSE 4
                END DESC
            """,
            (semester, semester)
        )
        history = cursor.fetchall()

        return render(request, 'professional/stats.html', {
            'full_name':       request.session.get('full_name', 'Professional'),
            'semester':        semester,
            'alerts':          alerts,
            # distribution
            'total_assessed':  total_assessed,
            'stable':          stable,
            'challenged':      challenged,
            'critical':        critical,
            'stable_pct':      pct(stable),
            'challenged_pct':  pct(challenged),
            'critical_pct':    pct(critical),
            # dept
            'dept_rows':       dept_rows,
            # symptoms
            'top_symptoms':    top_symptoms,
            # history
            'history':         history,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DISMISS ALERT  POST /alerts/dismiss/<id>/
#  Shared by Professional and Authority stats pages.
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def alerts_dismiss(request, alert_id):
    user_id, role = get_session_user(request)
    if not user_id or role not in ('professional', 'authority'):
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE analytics_alerts SET dismissed = TRUE WHERE id = %s",
            (alert_id,)
        )
        conn.commit()

        # Redirect back to the correct stats page
        if role == 'professional':
            return redirect('professional_stats')
        return redirect('authority_stats')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        if role == 'professional':
            return redirect('professional_stats')
        return redirect('authority_stats')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  AUTHORITY DASHBOARD  GET /authority/dashboard/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def authority_dashboard(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        messages.error(request, 'Please log in as a University Authority.')
        return redirect('landing')

    return render(request, 'authority/dashboard.html', {
        'full_name': request.session.get('full_name', 'Authority'),
    })

# ─────────────────────────────────────────────
#  AUTHORITY STATS  GET /authority/stats/
#  Identical content to professional_stats.
#  Reuses the shared alerts_dismiss view.
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def authority_stats(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        messages.error(request, 'Please log in as a University Authority.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        semester = get_current_semester(cursor)
        if not semester:
            messages.error(request, 'No active semester configured.')
            return redirect('authority_dashboard')

        # Run Analytics Agent
        from core.agents.analytics_agent import AnalyticsAgent
        alerts = AnalyticsAgent().run(semester)

        # Overall status distribution
        cursor.execute(
            """
            SELECT final_status, COUNT(*) AS cnt
            FROM   questionnaire_responses
            WHERE  semester        = %s
            AND    final_status    IS NOT NULL
            GROUP  BY final_status
            """,
            (semester,)
        )
        dist_rows      = cursor.fetchall()
        total_assessed = sum(r['cnt'] for r in dist_rows)
        distribution   = {r['final_status']: r['cnt'] for r in dist_rows}
        stable         = distribution.get('Stable',     0)
        challenged     = distribution.get('Challenged', 0)
        critical       = distribution.get('Critical',   0)

        def pct(n):
            return round((n / total_assessed * 100), 1) if total_assessed else 0

        # Per-department breakdown
        cursor.execute(
            """
            SELECT s.department,
                   COUNT(*)                                                        AS total,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Stable')             AS stable,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Challenged')         AS challenged,
                   COUNT(*) FILTER (WHERE qr.final_status = 'Critical')           AS critical
            FROM   questionnaire_responses qr
            JOIN   students s ON s.user_id = qr.student_id
            WHERE  qr.semester        = %s
            AND    qr.final_status    IS NOT NULL
            GROUP  BY s.department
            ORDER  BY s.department ASC
            """,
            (semester,)
        )
        dept_rows = cursor.fetchall()

        # Top symptoms by frequency
        symptom_counts = []
        for col, scale, text, symptom in QUESTIONS:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM   questionnaire_responses
                WHERE  semester        = %s
                AND    final_status    IS NOT NULL
                AND    {col} > 0
                """,
                (semester,)
            )
            row = cursor.fetchone()
            cnt = row['cnt'] if row else 0
            symptom_counts.append({
                'symptom': symptom,
                'scale':   scale.upper(),
                'count':   cnt,
                'col':     col,
            })
        symptom_counts.sort(key=lambda x: x['count'], reverse=True)
        top_symptoms = symptom_counts[:10]

        # Historical semester trends (descending — current first)
        cursor.execute(
            """
            SELECT semester, total, stable, challenged, critical
            FROM   semester_stats
            UNION ALL
            SELECT %s                                                               AS semester,
                   COUNT(*)                                                         AS total,
                   COUNT(*) FILTER (WHERE final_status = 'Stable')                 AS stable,
                   COUNT(*) FILTER (WHERE final_status = 'Challenged')              AS challenged,
                   COUNT(*) FILTER (WHERE final_status = 'Critical')               AS critical
            FROM   questionnaire_responses
            WHERE  semester        = %s
            AND    final_status    IS NOT NULL
            ORDER  BY
                CAST(SPLIT_PART(semester, ' ', 2) AS INTEGER) DESC,
                CASE SPLIT_PART(semester, ' ', 1)
                    WHEN 'Spring' THEN 1
                    WHEN 'Summer' THEN 2
                    WHEN 'Fall'   THEN 3
                    ELSE 4
                END DESC
            """,
            (semester, semester)
        )
        history = cursor.fetchall()

        return render(request, 'authority/stats.html', {
            'full_name':      request.session.get('full_name', 'Authority'),
            'semester':       semester,
            'alerts':         alerts,
            'total_assessed': total_assessed,
            'stable':         stable,
            'challenged':     challenged,
            'critical':       critical,
            'stable_pct':     pct(stable),
            'challenged_pct': pct(challenged),
            'critical_pct':   pct(critical),
            'dept_rows':      dept_rows,
            'top_symptoms':   top_symptoms,
            'history':        history,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  AUTHORITY EVENTS  GET /authority/events/
#  Lists all events + create form at the top.
#  When editing, the same page re-renders with
#  the form pre-filled via ?edit=<event_id>.
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def authority_events(request):
    """
    Paginated event list (10 per page) with a create/edit form at the top.

    URL parameters:
      ?page=<n>       — which page of events to show
      ?edit=<id>      — pre-fill the form for editing this event
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        messages.error(request, 'Please log in as a University Authority.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))
    edit_id  = request.GET.get('edit')
    edit_event = None

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Total count for pagination
        cursor.execute("SELECT COUNT(*) AS total FROM events")
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        # Paginated event list ordered by date ascending
        cursor.execute(
            """
            SELECT id, title, date, time, venue, description, rsvp_count
            FROM   events
            ORDER  BY date ASC, time ASC
            LIMIT  %s OFFSET %s
            """,
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        events = cursor.fetchall()

        # If ?edit=<id> is in the URL, fetch that event for the form
        if edit_id:
            cursor.execute(
                "SELECT id, title, date, time, venue, description "
                "FROM events WHERE id = %s AND created_by = %s",
                (edit_id, user_id)
            )
            edit_event = cursor.fetchone()

        # Pagination window (7-page)
        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)
        page_range = range(start_page, end_page + 1)

        return render(request, 'authority/events.html', {
            'full_name':   request.session.get('full_name', 'Authority'),
            'events':      events,
            'edit_event':  edit_event,
            'page':        page,
            'total_pages': total_pages,
            'page_range':  page_range,
            'start_page':  start_page,
            'end_page':    end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  CREATE EVENT  POST /authority/events/create/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def authority_events_create(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        return redirect('landing')

    title       = request.POST.get('title',       '').strip()
    date        = request.POST.get('date',         '').strip()
    time        = request.POST.get('time',         '').strip()
    venue       = request.POST.get('venue',        '').strip()
    description = request.POST.get('description', '').strip()

    if not all([title, date, time, venue]):
        messages.error(request, 'Title, date, time, and venue are required.')
        return redirect('authority_events')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO events (title, date, time, venue, description,
                                rsvp_count, created_by)
            VALUES (%s, %s, %s, %s, %s, 0, %s)
            """,
            (title, date, time, venue, description, user_id)
        )
        conn.commit()
        messages.success(request, f'Event "{title}" created successfully.')
        return redirect('authority_events')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('authority_events')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  EDIT EVENT  GET/POST /authority/events/edit/<event_id>/
# ─────────────────────────────────────────────
@require_http_methods(['GET', 'POST'])
def authority_events_edit(request, event_id):
    """
    GET  — Redirect to the events list with ?edit=<id> so the form
           at the top is pre-filled. This keeps the list visible
           while editing, matching the CityConnect single-page pattern.
    POST — Validate and update the event row.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        return redirect('landing')

    # GET — redirect to list with edit mode active
    if request.method == 'GET':
        page = request.GET.get('page', 1)
        return redirect(f'/authority/events/?edit={event_id}&page={page}')

    # POST — update the event
    title       = request.POST.get('title',       '').strip()
    date        = request.POST.get('date',         '').strip()
    time        = request.POST.get('time',         '').strip()
    venue       = request.POST.get('venue',        '').strip()
    description = request.POST.get('description', '').strip()
    page        = request.POST.get('page', 1)

    if not all([title, date, time, venue]):
        messages.error(request, 'Title, date, time, and venue are required.')
        return redirect(f'/authority/events/?edit={event_id}&page={page}')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Only the authority who created the event can edit it
        cursor.execute(
            """
            UPDATE events
            SET    title       = %s,
                   date        = %s,
                   time        = %s,
                   venue       = %s,
                   description = %s
            WHERE  id         = %s
            AND    created_by  = %s
            """,
            (title, date, time, venue, description, event_id, user_id)
        )
        if cursor.rowcount == 0:
            messages.error(request, 'Event not found or you do not have permission to edit it.')
        else:
            conn.commit()
            messages.success(request, f'Event "{title}" updated successfully.')
        return redirect(f'/authority/events/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('authority_events')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE EVENT  POST /authority/events/delete/<event_id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def authority_events_delete(request, event_id):
    """
    Hard-deletes the event. ON DELETE CASCADE in the schema
    automatically removes all related event_rsvps rows.
    Redirects back to the same page number after deletion.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'authority':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        # Fetch title before deletion for the success message
        cursor.execute(
            "SELECT title FROM events WHERE id = %s AND created_by = %s",
            (event_id, user_id)
        )
        event = cursor.fetchone()
        if not event:
            messages.error(request, 'Event not found or you do not have permission to delete it.')
            return redirect(f'/authority/events/?page={page}')

        cursor.execute(
            "DELETE FROM events WHERE id = %s AND created_by = %s",
            (event_id, user_id)
        )
        conn.commit()
        messages.success(request, f'Event "{event["title"]}" deleted successfully.')
        return redirect(f'/authority/events/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('authority_events')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  ADMIN DASHBOARD  GET /admin/dashboard/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_dashboard(request):
    """
    Six-card hub. Checks notification_pending on the current semester —
    if TRUE, flashes the auto-reset message once then clears the flag.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT semester, notification_pending "
            "FROM semester_schedule WHERE is_current = TRUE LIMIT 1"
        )
        row = cursor.fetchone()
        if row and row['notification_pending']:
            messages.info(
                request,
                f'Automatic mid-semester reset was performed for '
                f'{row["semester"]}.'
            )
            cursor.execute(
                "UPDATE semester_schedule SET notification_pending = FALSE "
                "WHERE is_current = TRUE"
            )
            conn.commit()

        return render(request, 'admin/dashboard.html', {
            'full_name': request.session.get('full_name', 'Admin IT'),
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE STUDENTS  GET /admin/students/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_students(request):
    """
    Paginated list of all students with their current-semester status.
    Control panel shows:
      - Current semester name + dates
      - Next upcoming semester with editable start date
      - Historical compiled stats from semester_stats table
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        from datetime import date as _date
        today = _date.today()

        # Current semester
        cursor.execute(
            """
            SELECT semester, start_date, end_date, stats_compiled
            FROM   semester_schedule
            WHERE  is_current = TRUE
            LIMIT  1
            """
        )
        current_sem = cursor.fetchone()

        # Next upcoming semester (first one that starts after today)
        cursor.execute(
            """
            SELECT semester, start_date, end_date
            FROM   semester_schedule
            WHERE  start_date > %s
            AND    is_current = FALSE
            ORDER  BY start_date ASC
            LIMIT  1
            """,
            (today,)
        )
        next_sem = cursor.fetchone()

        # Compiled semester stats history
        cursor.execute(
            """
            SELECT semester, total, stable, challenged, critical, at_risk_pct, compiled_at
            FROM   semester_stats
            ORDER  BY compiled_at DESC
            """
        )
        semester_stats_rows = cursor.fetchall()

        # Total student count
        cursor.execute("SELECT COUNT(*) AS total FROM users WHERE role = 'student'")
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        # Paginated student list with current-semester status
        semester_label = current_sem['semester'] if current_sem else None
        cursor.execute(
            """
            SELECT u.id, u.full_name, u.email,
                   s.student_id, s.department,
                   qr.final_status
            FROM   users u
            JOIN   students s ON s.user_id = u.id
            LEFT JOIN questionnaire_responses qr
                   ON qr.student_id = u.id
                   AND qr.semester  = %s
            WHERE  u.role = 'student'
            ORDER  BY u.full_name ASC
            LIMIT  %s OFFSET %s
            """,
            (semester_label, PER_PAGE, (page - 1) * PER_PAGE)
        )
        students = cursor.fetchall()

        student_rows = []
        for s in students:
            if not s['final_status']:
                display_status = 'Not Assessed'
            else:
                display_status = s['final_status']
            student_rows.append({
                'id':         s['id'],
                'full_name':  s['full_name'],
                'email':      s['email'],
                'student_id': s['student_id'],
                'department': s['department'],
                'status':     display_status,
            })

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        tomorrow = (today + __import__('datetime').timedelta(days=1)).isoformat()

        return render(request, 'admin/students.html', {
            'full_name':          request.session.get('full_name', 'Admin IT'),
            'students':           student_rows,
            'current_sem':        current_sem,
            'next_sem':           next_sem,
            'semester_stats_rows': semester_stats_rows,
            'tomorrow':           tomorrow,
            'page':               page,
            'total_pages':        total_pages,
            'page_range':         range(start_page, end_page + 1),
            'start_page':         start_page,
            'end_page':           end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  RESET ONE STUDENT  POST /admin/students/reset/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_students_reset(request, student_id):
    """
    Upserts the student's questionnaire_responses row for the current
    Deletes the student's questionnaire_responses row for the
    current semester so they retake the chatbot on next login.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT semester FROM semester_schedule WHERE is_current = TRUE LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'No active semester configured.')
            return redirect(f'/admin/students/?page={page}')

        semester = row['semester']
        cursor.execute(
            "DELETE FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (student_id, semester)
        )
        conn.commit()
        messages.success(request, 'Student responses deleted. They will retake the chatbot on next login.')
        return redirect(f'/admin/students/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/students/?page={page}')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE STUDENT  POST /admin/students/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_students_delete(request, student_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name FROM users WHERE id = %s AND role = 'student'",
            (student_id,)
        )
        student = cursor.fetchone()
        if not student:
            messages.error(request, 'Student not found.')
            return redirect(f'/admin/students/?page={page}')

        cursor.execute("DELETE FROM users WHERE id = %s", (student_id,))
        conn.commit()
        messages.success(request, f'Student "{student["full_name"]}" deleted.')
        return redirect(f'/admin/students/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/students/?page={page}')
    
    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  SET UPCOMING SEMESTER START DATE
#  POST /admin/students/set-start-date/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_students_set_start_date(request):
    """
    Allows Admin IT to adjust the start_date of the next upcoming semester.

    Rules:
      - Only future (non-current) semesters may be edited.
      - The chosen date must be after today.
      - The semester that immediately precedes the edited one has its
        end_date automatically set to new_start - 1 day, so there are
        never any gaps between consecutive semesters.
    """
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    semester   = request.POST.get('semester',   '').strip()
    start_date = request.POST.get('start_date', '').strip()

    if not semester or not start_date:
        messages.error(request, 'Semester and start date are required.')
        return redirect('admin_students')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        from datetime import date as _date, timedelta

        today     = _date.today()
        new_start = _date.fromisoformat(start_date)

        # Guard: date must be in the future
        if new_start <= today:
            messages.error(
                request,
                'The start date must be after today. Please choose a future date.'
            )
            return redirect('admin_students')

        # Guard: semester must exist and must not be current
        cursor.execute(
            "SELECT semester FROM semester_schedule "
            "WHERE semester = %s AND is_current = FALSE",
            (semester,)
        )
        if not cursor.fetchone():
            messages.error(request, 'Semester not found or it is the current semester.')
            return redirect('admin_students')

        # Update the upcoming semester's start_date
        cursor.execute(
            "UPDATE semester_schedule SET start_date = %s WHERE semester = %s",
            (new_start, semester)
        )

        # Update the immediately preceding semester's end_date to
        # new_start - 1 day, ensuring no gaps in the schedule.
        # "Preceding" = the semester with the largest start_date
        # that is still less than new_start.
        new_end_prev = new_start - timedelta(days=1)
        cursor.execute(
            """
            UPDATE semester_schedule
            SET    end_date = %s
            WHERE  semester = (
                SELECT semester
                FROM   semester_schedule
                WHERE  start_date < %s
                ORDER  BY start_date DESC
                LIMIT  1
            )
            """,
            (new_end_prev, new_start)
        )

        conn.commit()
        messages.success(
            request,
            f'{semester} start date updated to {new_start.strftime("%B %d, %Y")}. '
            f'The preceding semester now ends on {new_end_prev.strftime("%B %d, %Y")}.'
        )
        return redirect('admin_students')

    except ValueError:
        messages.error(request, 'Invalid date format. Please try again.')
        return redirect('admin_students')
    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('admin_students')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE PROFESSIONALS  GET /admin/professionals/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_professionals(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'professional'"
        )
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        cursor.execute(
            """
            SELECT u.id, u.full_name, u.email,
                   COUNT(a.id) AS active_count
            FROM   users u
            LEFT JOIN appointments a
                   ON a.professional_id = u.id AND a.status = 'accepted'
            WHERE  u.role = 'professional'
            GROUP  BY u.id, u.full_name, u.email
            ORDER  BY u.full_name ASC
            LIMIT  %s OFFSET %s
            """,
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        professionals = cursor.fetchall()

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        return render(request, 'admin/professionals.html', {
            'full_name':    request.session.get('full_name', 'Admin IT'),
            'professionals': professionals,
            'page':         page,
            'total_pages':  total_pages,
            'page_range':   range(start_page, end_page + 1),
            'start_page':   start_page,
            'end_page':     end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REGISTER PROFESSIONAL  POST /admin/professionals/register/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_professionals_register(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    full_name = request.POST.get('full_name', '').strip()
    email     = request.POST.get('email',     '').strip().lower()
    password  = request.POST.get('password',  '').strip()

    if not all([full_name, email, password]):
        messages.error(request, 'All fields are required.')
        return redirect('admin_professionals')
    if len(password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return redirect('admin_professionals')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            messages.error(request, 'An account with that email already exists.')
            return redirect('admin_professionals')

        hashed = make_password(password)
        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('professional', %s, %s, %s)",
            (full_name, email, hashed)
        )
        conn.commit()
        send_welcome_email(full_name, email, password, 'Mental Health Professional')
        messages.success(request, f'Professional "{full_name}" registered. A welcome email has been sent.')
        return redirect('admin_professionals')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('admin_professionals')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE PROFESSIONAL  POST /admin/professionals/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_professionals_delete(request, prof_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name FROM users WHERE id = %s AND role = 'professional'",
            (prof_id,)
        )
        prof = cursor.fetchone()
        if not prof:
            messages.error(request, 'Professional not found.')
            return redirect(f'/admin/professionals/?page={page}')

        cursor.execute("DELETE FROM users WHERE id = %s", (prof_id,))
        conn.commit()
        messages.success(request, f'Professional "{prof["full_name"]}" deleted.')
        return redirect(f'/admin/professionals/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/professionals/?page={page}')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE AUTHORITY  GET /admin/authority/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_authority(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'authority'"
        )
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        cursor.execute(
            "SELECT id, full_name, email FROM users "
            "WHERE role = 'authority' "
            "ORDER BY full_name ASC LIMIT %s OFFSET %s",
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        authority_users = cursor.fetchall()

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        return render(request, 'admin/authority.html', {
            'full_name':       request.session.get('full_name', 'Admin IT'),
            'authority_users': authority_users,
            'page':            page,
            'total_pages':     total_pages,
            'page_range':      range(start_page, end_page + 1),
            'start_page':      start_page,
            'end_page':        end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REGISTER AUTHORITY  POST /admin/authority/register/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_authority_register(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    full_name = request.POST.get('full_name', '').strip()
    email     = request.POST.get('email',     '').strip().lower()
    password  = request.POST.get('password',  '').strip()

    if not all([full_name, email, password]):
        messages.error(request, 'All fields are required.')
        return redirect('admin_authority')
    if len(password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return redirect('admin_authority')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            messages.error(request, 'An account with that email already exists.')
            return redirect('admin_authority')

        hashed = make_password(password)
        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('authority', %s, %s, %s)",
            (full_name, email, hashed)
        )
        conn.commit()
        send_welcome_email(full_name, email, password, 'University Authority')
        messages.success(request, f'Authority "{full_name}" registered. A welcome email has been sent.')
        return redirect('admin_authority')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('admin_authority')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE AUTHORITY  POST /admin/authority/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_authority_delete(request, authority_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name FROM users WHERE id = %s AND role = 'authority'",
            (authority_id,)
        )
        auth = cursor.fetchone()
        if not auth:
            messages.error(request, 'Authority not found.')
            return redirect(f'/admin/authority/?page={page}')

        cursor.execute("DELETE FROM users WHERE id = %s", (authority_id,))
        conn.commit()
        messages.success(request, f'Authority "{auth["full_name"]}" deleted.')
        return redirect(f'/admin/authority/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/authority/?page={page}')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE ADMIN IT  GET /admin/it/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_it(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM users WHERE role = 'admin_it'"
        )
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        cursor.execute(
            "SELECT id, full_name, email FROM users "
            "WHERE role = 'admin_it' "
            "ORDER BY full_name ASC LIMIT %s OFFSET %s",
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        admins = cursor.fetchall()

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        return render(request, 'admin/it.html', {
            'full_name':    request.session.get('full_name', 'Admin IT'),
            'admins':       admins,
            'current_id':   user_id,   # used in template for self-protect
            'page':         page,
            'total_pages':  total_pages,
            'page_range':   range(start_page, end_page + 1),
            'start_page':   start_page,
            'end_page':     end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  REGISTER ADMIN IT  POST /admin/it/register/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_it_register(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    full_name = request.POST.get('full_name', '').strip()
    email     = request.POST.get('email',     '').strip().lower()
    password  = request.POST.get('password',  '').strip()

    if not all([full_name, email, password]):
        messages.error(request, 'All fields are required.')
        return redirect('admin_it')
    if len(password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return redirect('admin_it')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            messages.error(request, 'An account with that email already exists.')
            return redirect('admin_it')

        hashed = make_password(password)
        cursor.execute(
            "INSERT INTO users (role, full_name, email, password) "
            "VALUES ('admin_it', %s, %s, %s)",
            (full_name, email, hashed)
        )
        conn.commit()
        send_welcome_email(full_name, email, password, 'Admin IT')
        messages.success(request, f'Admin IT "{full_name}" registered. A welcome email has been sent.')
        return redirect('admin_it')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect('admin_it')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE ADMIN IT  POST /admin/it/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_it_delete(request, admin_user_id):
    """Self-protect: cannot delete your own account."""
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    # Self-protect check
    if admin_user_id == user_id:
        messages.error(request, 'You cannot delete your own Admin IT account.')
        return redirect(f'/admin/it/?page={page}')

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name FROM users WHERE id = %s AND role = 'admin_it'",
            (admin_user_id,)
        )
        admin = cursor.fetchone()
        if not admin:
            messages.error(request, 'Admin IT account not found.')
            return redirect(f'/admin/it/?page={page}')

        cursor.execute("DELETE FROM users WHERE id = %s", (admin_user_id,))
        conn.commit()
        messages.success(request, f'Admin IT "{admin["full_name"]}" deleted.')
        return redirect(f'/admin/it/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/it/?page={page}')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE APPOINTMENTS  GET /admin/appointments/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_appointments(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM appointments")
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        cursor.execute(
            """
            SELECT a.id,
                   a.status,
                   a.scheduled_at,
                   su.full_name  AS student_name,
                   s.student_id,
                   pu.full_name  AS professional_name
            FROM   appointments a
            JOIN   users    su ON su.id      = a.student_id
            JOIN   students s  ON s.user_id  = a.student_id
            JOIN   users    pu ON pu.id      = a.professional_id
            ORDER  BY a.id DESC
            LIMIT  %s OFFSET %s
            """,
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        appointments = cursor.fetchall()

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        return render(request, 'admin/appointments.html', {
            'full_name':    request.session.get('full_name', 'Admin IT'),
            'appointments': appointments,
            'page':         page,
            'total_pages':  total_pages,
            'page_range':   range(start_page, end_page + 1),
            'start_page':   start_page,
            'end_page':     end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE APPOINTMENT  POST /admin/appointments/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_appointments_delete(request, appointment_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM appointments WHERE id = %s", (appointment_id,)
        )
        if not cursor.fetchone():
            messages.error(request, 'Appointment not found.')
            return redirect(f'/admin/appointments/?page={page}')

        cursor.execute("DELETE FROM appointments WHERE id = %s", (appointment_id,))
        conn.commit()
        messages.success(request, 'Appointment deleted.')
        return redirect(f'/admin/appointments/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/appointments/?page={page}')

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  MANAGE EVENTS  GET /admin/events/
# ─────────────────────────────────────────────
@require_http_methods(['GET'])
def admin_events(request):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        messages.error(request, 'Please log in as Admin IT.')
        return redirect('landing')

    PER_PAGE = 10
    page     = max(1, int(request.GET.get('page', 1)))

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) AS total FROM events")
        total       = cursor.fetchone()['total']
        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page        = min(page, total_pages)

        cursor.execute(
            """
            SELECT e.id, e.title, e.date, e.time, e.venue,
                   e.rsvp_count, u.full_name AS created_by_name
            FROM   events e
            JOIN   users  u ON u.id = e.created_by
            ORDER  BY e.date ASC, e.time ASC
            LIMIT  %s OFFSET %s
            """,
            (PER_PAGE, (page - 1) * PER_PAGE)
        )
        events = cursor.fetchall()

        half       = 3
        start_page = max(1, page - half)
        end_page   = min(total_pages, start_page + 6)
        start_page = max(1, end_page - 6)

        return render(request, 'admin/events.html', {
            'full_name':   request.session.get('full_name', 'Admin IT'),
            'events':      events,
            'page':        page,
            'total_pages': total_pages,
            'page_range':  range(start_page, end_page + 1),
            'start_page':  start_page,
            'end_page':    end_page,
        })

    finally:
        cursor.close()
        conn.close()

# ─────────────────────────────────────────────
#  DELETE EVENT  POST /admin/events/delete/<id>/
# ─────────────────────────────────────────────
@require_http_methods(['POST'])
def admin_events_delete(request, event_id):
    user_id, role = get_session_user(request)
    if not user_id or role != 'admin_it':
        return redirect('landing')

    page = request.POST.get('page', 1)

    conn   = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT title FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()
        if not event:
            messages.error(request, 'Event not found.')
            return redirect(f'/admin/events/?page={page}')

        cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
        conn.commit()
        messages.success(request, f'Event "{event["title"]}" deleted.')
        return redirect(f'/admin/events/?page={page}')

    except Exception as exc:
        conn.rollback()
        messages.error(request, f'An error occurred: {exc}')
        return redirect(f'/admin/events/?page={page}')

    finally:
        cursor.close()
        conn.close()