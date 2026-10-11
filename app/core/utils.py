"""Shared helpers. Pagination and small reusable checks live here."""
import re

from core.db import connect_db, get_current_semester

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


# ── Pagination ───────────────────────────────────────────────────────
def get_page_param(request, name='page'):
    """Read ?page= safely. Anything invalid or below 1 becomes page 1."""
    try:
        page = int(request.GET.get(name, 1))
    except (TypeError, ValueError):
        page = 1
    return max(page, 1)


def get_total_pages(total_items, per_page):
    """Number of pages needed for `total_items` (always at least 1)."""
    if per_page < 1:
        raise ValueError('per_page must be at least 1')
    return max(1, -(-int(total_items) // per_page))


def get_page_range(current, total_pages, window=2):
    """Page numbers to render in a pagination bar.

    Always includes the first and last page and `window` pages either side
    of the current one. Gaps are returned as None (render as an ellipsis).

        get_page_range(1, 5)   -> [1, 2, 3, 4, 5]
        get_page_range(10, 20) -> [1, None, 8, 9, 10, 11, 12, None, 20]
    """
    if total_pages < 1:
        return [1]
    current = min(max(current, 1), total_pages)

    pages = sorted(
        {1, total_pages}
        | set(range(max(1, current - window), min(total_pages, current + window) + 1))
    )

    result = []
    previous = None
    for page in pages:
        if previous is not None:
            if page - previous == 2:
                result.append(previous + 1)  # a one-page gap reads better as the page
            elif page - previous > 2:
                result.append(None)
        result.append(page)
        previous = page
    return result


# ── Passwords ────────────────────────────────────────────────────────
def validate_new_password(password):
    """Return a list of problems with a proposed password (empty list = fine).

    Used wherever a password is chosen: registration, password change and,
    later, the admin password-set link.
    """
    problems = []
    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f'Use at least {PASSWORD_MIN_LENGTH} characters.')
    if len(password) > PASSWORD_MAX_LENGTH:
        problems.append(f'Use no more than {PASSWORD_MAX_LENGTH} characters.')
    if not re.search(r'[A-Za-z]', password):
        problems.append('Include at least one letter.')
    if not re.search(r'\d', password):
        problems.append('Include at least one number.')
    return problems


# ── Database conveniences ────────────────────────────────────────────
def fetch_current_semester():
    """The current semester label (e.g. 'Fall 2026'), or None if none is set."""
    conn = connect_db()
    cursor = conn.cursor()
    try:
        return get_current_semester(cursor)
    finally:
        cursor.close()
        conn.close()