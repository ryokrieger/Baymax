# ══════════════════════════════════════════════════════════════════════
#  ROLE ROUTING
# ══════════════════════════════════════════════════════════════════════

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

# ══════════════════════════════════════════════════════════════════════
#  QUESTION BANK
#  Single source of truth for all 26 assessment questions.
#
#  Order MUST match scaler.pkl's fitted feature order:
#      PSS1–PSS10, GAD1–GAD7, PHQ1–PHQ9
#
#  Each tuple: (db_column, scale_type, question_text, symptom_label)
# ══════════════════════════════════════════════════════════════════════

QUESTIONS = [
    # ── PSS-10  (0 = Never … 4 = Very Often) ─────────────────────────
    (
        'pss1', 'pss',
        'During a semester, how often have you felt upset because of '
        'something that happened in your academic affairs?',
        'Distress',
    ),
    (
        'pss2', 'pss',
        'During a semester, how often have you felt unable to control '
        'important things in your academic affairs?',
        'Loss of Control',
    ),
    (
        'pss3', 'pss',
        'During a semester, how often have you felt nervous and stressed '
        'due to academic pressure?',
        'Stress',
    ),
    (
        'pss4', 'pss',
        'During a semester, how often have you felt unable to cope with '
        'all the mandatory academic activities (e.g., assignments, '
        'quizzes, exams)?',
        'Inability to Cope',
    ),
    (
        'pss5', 'pss',
        'During a semester, how often have you felt confident about your '
        'ability to handle your academic or university problems?',
        'Low Self-Confidence',
    ),
    (
        'pss6', 'pss',
        'During a semester, how often have you felt that things in your '
        'academic life were going your way?',
        'Lack of Progress',
    ),
    (
        'pss7', 'pss',
        'During a semester, how often have you been able to control '
        'irritations in your academic or university affairs?',
        'Poor Irritation Control',
    ),
    (
        'pss8', 'pss',
        'During a semester, how often have you felt that your academic '
        'performance was at its best?',
        'Low Academic Self-Efficacy',
    ),
    (
        'pss9', 'pss',
        'During a semester, how often have you felt angry due to poor '
        'performance or low grades that were beyond your control?',
        'Anger / Frustration',
    ),
    (
        'pss10', 'pss',
        'During a semester, how often have you felt that academic '
        'difficulties were piling up so high that you could not overcome '
        'them?',
        'Overwhelm',
    ),

    # ── GAD-7  (0 = Not at all … 3 = Nearly every day) ───────────────
    (
        'gad1', 'gad',
        'During a semester, how often have you felt nervous, anxious, or '
        'on edge due to academic pressure?',
        'Anxiety / Nervousness',
    ),
    (
        'gad2', 'gad',
        'During a semester, how often have you been unable to stop '
        'worrying about your academic affairs?',
        'Uncontrollable Worry',
    ),
    (
        'gad3', 'gad',
        'During a semester, how often have you had trouble relaxing due '
        'to academic pressure?',
        'Inability to Relax',
    ),
    (
        'gad4', 'gad',
        'During a semester, how often have you been easily annoyed or '
        'irritated because of academic pressure?',
        'Irritability',
    ),
    (
        'gad5', 'gad',
        'During a semester, how often have you worried too much about '
        'academic affairs?',
        'Excessive Worry',
    ),
    (
        'gad6', 'gad',
        'During a semester, how often have you been so restless due to '
        'academic pressure that it is hard to sit still?',
        'Restlessness',
    ),
    (
        'gad7', 'gad',
        'During a semester, how often have you felt afraid, as if '
        'something awful might happen?',
        'Fear / Apprehension',
    ),

    # ── PHQ-9  (0 = Not at all … 3 = Nearly every day) ───────────────
    (
        'phq1', 'phq',
        'During the semester, how often have you had little interest or '
        'pleasure in doing things?',
        'Anhedonia (Loss of Interest / Pleasure)',
    ),
    (
        'phq2', 'phq',
        'During the semester, how often have you felt down, depressed, '
        'or hopeless?',
        'Depressed Mood / Hopelessness',
    ),
    (
        'phq3', 'phq',
        'During the semester, how often have you had trouble falling '
        'asleep, staying asleep, or sleeping too much?',
        'Sleep Disturbance',
    ),
    (
        'phq4', 'phq',
        'During the semester, how often have you felt tired or had '
        'little energy?',
        'Fatigue / Low Energy',
    ),
    (
        'phq5', 'phq',
        'During the semester, how often have you had a poor appetite or '
        'overeaten?',
        'Appetite Disturbance',
    ),
    (
        'phq6', 'phq',
        'During the semester, how often have you felt bad about yourself, '
        'or felt that you are a failure or have let yourself or your '
        'family down?',
        'Low Self-Worth / Guilt',
    ),
    (
        'phq7', 'phq',
        'During the semester, how often have you had trouble concentrating '
        'on things, such as reading books or watching television?',
        'Concentration Difficulty',
    ),
    (
        'phq8', 'phq',
        'During the semester, how often have you moved or spoken so '
        'slowly that other people could notice? Or how often have you '
        'been moving much more than usual because you felt restless?',
        'Psychomotor Agitation / Retardation',
    ),
    (
        'phq9', 'phq',
        'During the semester, how often have you had thoughts that you '
        'would be better off dead or of hurting yourself?',
        'Suicidal Ideation / Self-Harm Thoughts',
    ),
]

# ── Derived look-ups (computed once at import time) ───────────────────

# Column names in exact ML feature order
QUESTION_COLS = [q[0] for q in QUESTIONS]

# column → symptom label
QUESTION_SYMPTOMS = {q[0]: q[3] for q in QUESTIONS}

# ══════════════════════════════════════════════════════════════════════
#  ANSWER LABELS
# ══════════════════════════════════════════════════════════════════════

SCALE_LABELS = {
    'pss': [
        'Never',
        'Almost Never',
        'Sometimes',
        'Fairly Often',
        'Very Often',
    ],
    'gad': [
        'Not at all',
        'Several days',
        'More than half the days',
        'Nearly every day',
    ],
    'phq': [
        'Not at all',
        'Several days',
        'More than half the days',
        'Nearly every day',
    ],
}

# Maximum valid integer answer per scale (inclusive)
SCALE_MAX = {
    'pss': 4,
    'gad': 3,
    'phq': 3,
}