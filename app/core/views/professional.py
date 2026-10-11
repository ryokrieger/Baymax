"""Professional portal views."""
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from core.utils import fetch_current_semester
from core.views.auth import login_required_role


@require_http_methods(['GET'])
@login_required_role('professional')
def professional_dashboard(request):
    # Placeholder: the real dashboard arrives in a later sprint.
    return render(request, 'professional/dashboard.html', {
        'semester': fetch_current_semester(),
        'full_name': request.session.get('full_name', ''),
        'email': request.session.get('email', ''),
    })