"""Development-only views. Removed in Sprint 1 when the landing page arrives."""
from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from core.utils import get_page_range

SAMPLE_ROWS = [
    {'name': 'Jamie Park',    'meta': 'CSE · Year 3', 'state': 'pending',   'status': 'Critical'},
    {'name': 'Morgan Lee',    'meta': 'BBA · Year 2', 'state': 'pending',   'status': 'Challenged'},
    {'name': 'Riley Torres',  'meta': 'ENG · Year 4', 'state': 'active',    'status': 'Stable'},
    {'name': 'Casey Nguyen',  'meta': 'EEE · Year 1', 'state': 'completed', 'status': 'Stable'},
]


def styleguide(request):
    """Shows every design-system component. Only available when DEBUG is on."""
    if not settings.DEBUG:
        raise Http404
    current_page = 9
    return render(request, 'styleguide.html', {
        'rows': SAMPLE_ROWS,
        'current_page': current_page,
        'pages': get_page_range(current_page, 20),
    })