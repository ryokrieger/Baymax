from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.views.decorators.http import require_http_methods
from core.db import connect_db, get_current_semester
from core.agents.reset_agent import ResetAgent
from core.ml import predict as ml_predict
from core.agents.triage_agent import TriageAgent

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
            'role':       role,
            'role_label': ROLE_LABELS[role],
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
            messages.error(
                request,
                'No active semester has been configured. Please contact Admin IT.'
            )
            return redirect('landing')

        cursor.execute(
            "SELECT responses_reset, final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user['id'], semester),
        )
        qr = cursor.fetchone()

        if qr and not qr['responses_reset'] and qr['final_status']:
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
        cursor.execute(
            "SELECT id, full_name, role FROM users WHERE email = %s",
            (google_email,),
        )
        existing_user = cursor.fetchone()

        # ── Case B: existing account ──────────────────────────────────
        if existing_user:
            if existing_user['role'] != 'student':
                messages.error(
                    request,
                    'This email is registered under a non-student role. '
                    'Please use email/password login.'
                )
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
                "SELECT responses_reset, final_status FROM questionnaire_responses "
                "WHERE student_id = %s AND semester = %s",
                (existing_user['id'], semester),
            )
            qr = cursor.fetchone()

            if qr and not qr['responses_reset'] and qr['final_status']:
                return redirect('student_dashboard')
            else:
                return redirect('chatbot')

        # ── Case A: new user ──────────────────────────────────────────
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

        student_id = request.POST.get('student_id', '').strip()
        department = request.POST.get('department', '').strip()
        password   = request.POST.get('password',   '').strip()
        confirm    = request.POST.get('confirm',     '').strip()
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
QUESTION_COLS = [q[0] for q in QUESTIONS]

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
            messages.error(
                request,
                'No active semester has been configured. Please contact Admin IT.'
            )
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
            if qr and qr['final_status'] and not qr['responses_reset']:
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
                f"    (student_id, semester, {col}, responses_reset) "
                f"VALUES (%s, %s, %s, FALSE)",
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
            messages.error(request, 'Some answers are missing. Please complete the assessment again.')
            return redirect('chatbot')

        status = ml_predict(answers)

        cursor.execute(
            """
            UPDATE questionnaire_responses
            SET    final_status    = %s,
                   responses_reset = FALSE
            WHERE  student_id = %s AND semester = %s
            """,
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

        final_status = row['final_status']

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
        messages.error(request, 'Please log in as a student.')
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
            messages.error(
                request,
                'No active semester has been configured. Please contact Admin IT.'
            )
            return redirect('landing')

        # Guard: if assessment not complete or was reset, send to chatbot
        cursor.execute(
            "SELECT responses_reset, final_status FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()

        if not qr or qr['responses_reset'] or not qr['final_status']:
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
        if not qr or not qr['final_status'] or qr['responses_reset']:
            return redirect('chatbot')
 
        final_status = qr['final_status']
 
        # ── Build response rows for the table ─────────────────────────
        # Each row: question number, scale, symptom label, raw answer,
        #           human-readable answer label, severity score
        scale_answer_labels = {
            'pss': ['Never', 'Almost Never', 'Sometimes', 'Fairly Often', 'Very Often'],
            'gad': ['Not at all', 'Several days', 'More than half the days', 'Nearly every day'],
            'phq': ['Not at all', 'Several days', 'More than half the days', 'Nearly every day'],
        }
 
        responses = []
        for i, (col, scale, text, symptom) in enumerate(QUESTIONS):
            raw = qr[col]
            if raw is None:
                continue
            answer_label = scale_answer_labels[scale][raw] if raw is not None else '—'
            severity     = raw
            responses.append({
                'number':       i + 1,
                'col':          col,
                'scale':        scale.upper(),
                'symptom':      symptom,
                'text':         text,
                'raw':          raw,
                'answer_label': answer_label,
                'severity':     severity,
            })
 
        # ── Top 3 symptoms by severity score ──────────────────────────
        # Sort by severity descending, take top 3
        sorted_by_severity = sorted(responses, key=lambda r: r['severity'], reverse=True)
        top_symptoms = sorted_by_severity[:3]
 
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
            "SELECT final_status, responses_reset FROM questionnaire_responses "
            "WHERE student_id = %s AND semester = %s",
            (user_id, semester),
        )
        qr = cursor.fetchone()
 
        if not qr or not qr['final_status'] or qr['responses_reset']:
            return redirect('chatbot')
 
        final_status = qr['final_status']
 
        # Student's current active appointment (pending or accepted)
        cursor.execute(
            """
            SELECT a.id, a.status, a.scheduled_at,
                   u.full_name AS professional_name,
                   a.professional_id
            FROM   appointments a
            JOIN   users u ON u.id = a.professional_id
            WHERE  a.student_id = %s
            AND    a.status IN ('pending', 'accepted')
            ORDER  BY a.id DESC
            LIMIT  1
            """,
            (user_id,)
        )
        active_appt = cursor.fetchone()
 
        # All professionals with their current active student count
        cursor.execute(
            """
            SELECT  u.id,
                    u.full_name,
                    COUNT(a.id) AS active_count,
                    CASE WHEN COUNT(a.id) < 12 THEN TRUE ELSE FALSE END AS is_available
            FROM    users u
            LEFT JOIN appointments a
                   ON a.professional_id = u.id
                   AND a.status = 'accepted'
            WHERE   u.role = 'professional'
            GROUP BY u.id, u.full_name
            ORDER BY u.full_name ASC
            """
        )
        professionals = cursor.fetchall()
 
        return render(request, 'student/help.html', {
            'full_name':    request.session.get('full_name', 'Student'),
            'semester':     semester,
            'final_status': final_status,
            'active_appt':  active_appt,
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
            "AND status IN ('pending', 'accepted')",
            (user_id,)
        )
        if cursor.fetchone():
            messages.error(request, 'You already have an active appointment.')
            return redirect('student_help')
 
        # Guard: professional exists and is available
        cursor.execute(
            """
            SELECT u.id,
                   COUNT(a.id) AS active_count
            FROM   users u
            LEFT JOIN appointments a
                   ON a.professional_id = u.id AND a.status = 'accepted'
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
            """
            SELECT id, title, date, time, venue, description, rsvp_count
            FROM   events
            ORDER  BY date ASC, time ASC
            """
        )
        events_raw = cursor.fetchall()
 
        # Which events has this student RSVPd to?
        cursor.execute(
            "SELECT event_id FROM event_rsvps WHERE student_id = %s",
            (user_id,)
        )
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
                "UPDATE events SET rsvp_count = rsvp_count + 1 WHERE id = %s",
                (event_id,)
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