"""
Baymax routes.

Sprint 0 has one temporary route: the design-system style guide, shown at
/ and /styleguide/ while DEBUG is on. Sprint 1 replaces it with the landing
page and adds auth, then the four role portals:
/student/, /professional/, /authority/, /admin/.
"""
from django.urls import path

from core.views import dev

urlpatterns = [
    path('', dev.styleguide, name='styleguide'),
    path('styleguide/', dev.styleguide),
]