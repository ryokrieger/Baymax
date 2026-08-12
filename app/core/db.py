import os

import psycopg2
import psycopg2.extras


def connect_db():
    """
    Return a new raw psycopg2 connection to the app's business tables
    (users, students, appointments, etc.) — everything outside Django's
    own admin/session/allauth tables, which go through the ORM as usual.

    Rows come back as RealDictCursor objects, so callers can do
    row['email'] instead of positional indexing. Callers are responsible
    for closing the connection — use `with connect_db() as conn:` or an
    explicit `conn.close()` in a `finally` block.
    """
    return psycopg2.connect(
        os.environ['DATABASE_URL'],
        cursor_factory=psycopg2.extras.RealDictCursor,
    )