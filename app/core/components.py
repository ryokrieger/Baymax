"""
Shared constants.

The 26 assessment questions (QUESTIONS, QUESTION_COLS) are added in Sprint 2.
"""

VALID_DEPARTMENTS = frozenset({'CSE', 'EEE', 'ENG', 'ECO', 'BBA'})

# Role values stored in users.role and in request.session['role'].
VALID_ROLES = frozenset({'student', 'professional', 'authority', 'admin_it'})

ROLE_LABELS = {
    'student':      'Student',
    'professional': 'Mental Health Professional',
    'authority':    'University Authority',
    'admin_it':     'Admin IT',
}

# Where each role lands after signing in (URL names).
ROLE_DASHBOARD = {
    'student':      'student_dashboard',
    'professional': 'professional_dashboard',
    'authority':    'authority_dashboard',
    'admin_it':     'admin_dashboard',
}

# Landing-page cards and the role chips on the login page.
# `accent` picks the card colour (card-top-<accent>).
ROLE_CARDS = (
    {'role': 'student',      'title': 'Student',      'icon': '🎓', 'accent': 'mint',
     'blurb': 'Take assessments & track wellbeing'},
    {'role': 'professional', 'title': 'Professional', 'icon': '🧠', 'accent': 'lavender',
     'blurb': 'Manage appointments & students'},
    {'role': 'authority',    'title': 'Authority',    'icon': '🏛️', 'accent': 'peach',
     'blurb': 'View campus-wide analytics'},
    {'role': 'admin_it',     'title': 'Admin IT',     'icon': '⚙️', 'accent': 'coral',
     'blurb': 'Manage users & semesters'},
)

# Navbar links per role: (label, URL name). Each sprint adds the pages it builds.
NAV_ITEMS = {
    'student':      (('Dashboard', 'student_dashboard'),),
    'professional': (('Dashboard', 'professional_dashboard'),),
    'authority':    (('Dashboard', 'authority_dashboard'),),
    'admin_it':     (('Dashboard', 'admin_dashboard'),),
}

# Links every signed-in role gets, after its own.
COMMON_NAV_ITEMS = (('Password', 'password_change'),)

# Classification labels, in severity order.
STATUSES = ('Stable', 'Challenged', 'Critical')