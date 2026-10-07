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

# Classification labels, in severity order.
STATUSES = ('Stable', 'Challenged', 'Critical')