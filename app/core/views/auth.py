import functools

from django.core.cache import cache
from django.shortcuts import render, redirect


def login_required_role(*roles):
    """Restrict a view to one or more session-authenticated roles."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.session.get('role') not in roles:
                return redirect('login')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def rate_limit(max_attempts: int = 5, window: int = 900):
    """Block repeated POST failures to a view for `window` seconds."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method == 'POST':
                key = f'rate_limit:{request.POST.get("email", "")}'
                count = cache.get(key, 0)
                if count >= max_attempts:
                    # Let the view handle the error display — it just
                    # checks request.rate_limited.
                    request.rate_limited = True
                    return view_func(request, *args, **kwargs)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def landing_view(request):
    """Public landing page — entry point into registration/login."""
    return render(request, 'auth/landing.html')