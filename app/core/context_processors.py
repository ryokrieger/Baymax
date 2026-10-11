"""Template context available on every page."""
from django.urls import reverse

from core.components import COMMON_NAV_ITEMS, NAV_ITEMS, ROLE_DASHBOARD, ROLE_LABELS


def navigation(request):
    """Navbar data for base.html, built from the signed-in role.

    Adding a page to a role's navbar only means adding it to NAV_ITEMS in
    core/components.py; no template changes.
    """
    session = getattr(request, 'session', None)
    role = session.get('role') if session is not None else None

    if role not in ROLE_DASHBOARD or not session.get('user_id'):
        return {'nav': {
            'is_authenticated': False,
            'home_url': reverse('landing'),
            'items': [],
        }}

    resolver = getattr(request, 'resolver_match', None)
    current = resolver.url_name if resolver else None

    items = [
        {
            'label': label,
            'url': reverse(url_name),
            'active': url_name == current,
        }
        for label, url_name in NAV_ITEMS[role] + COMMON_NAV_ITEMS
    ]

    return {'nav': {
        'is_authenticated': True,
        'home_url': reverse(ROLE_DASHBOARD[role]),
        'items': items,
        'user_name': session.get('full_name', ''),
        'role_label': ROLE_LABELS[role],
    }}