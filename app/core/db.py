import os

import psycopg2
from psycopg2.extras import RealDictCursor


def connect_db():
    """Open a psycopg2 connection that returns rows as dicts.

    DATABASE_URL (Neon / production) wins; otherwise the local DB_* values
    from .env are used. Callers close the cursor and connection themselves.
    """
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    return psycopg2.connect(
        dbname=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        host=os.environ.get('DB_HOST'),
        port=os.environ.get('DB_PORT'),
        cursor_factory=RealDictCursor,
    )


def get_current_semester(cursor):
    """Return the current semester label (e.g. 'Fall 2026'), or None."""
    cursor.execute(
        "SELECT semester FROM semester_schedule WHERE is_current = TRUE LIMIT 1"
    )
    row = cursor.fetchone()
    return row['semester'] if row else None