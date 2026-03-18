import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from pathlib import Path

# Ensure .env is loaded even if this module is imported before settings
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def connect_db():
    return psycopg2.connect(
        dbname   = os.environ.get('DB_NAME'),
        user     = os.environ.get('DB_USER'),
        password = os.environ.get('DB_PASSWORD'),
        host     = os.environ.get('DB_HOST'),
        port     = os.environ.get('DB_PORT'),
        cursor_factory = RealDictCursor,
    )


def get_current_semester(cursor):
    cursor.execute(
        "SELECT semester FROM semester_schedule WHERE is_current = TRUE LIMIT 1"
    )
    row = cursor.fetchone()
    return row['semester'] if row else None