import getpass
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.db import connect_db

class Command(BaseCommand):
    help = 'Create the first Admin IT account (run once during initial setup).'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n── Baymax: Create Admin IT Account ──────────────────────'
        ))
        self.stdout.write(
            'This creates the first Admin IT user so you can log in\n'
            'and create all other non-student accounts from the panel.\n'
        )

        # ── Collect inputs ────────────────────────────────────────────
        full_name = input('Full name : ').strip()
        if not full_name:
            self.stderr.write(self.style.ERROR('Full name cannot be empty.'))
            return

        email = input('Email     : ').strip().lower()
        if not email or '@' not in email:
            self.stderr.write(self.style.ERROR('A valid email address is required.'))
            return

        # getpass hides the typed password in the terminal
        password = getpass.getpass('Password  : ')
        if len(password) < 8:
            self.stderr.write(self.style.ERROR(
                'Password must be at least 8 characters.'
            ))
            return

        confirm = getpass.getpass('Confirm   : ')
        if password != confirm:
            self.stderr.write(self.style.ERROR('Passwords do not match.'))
            return

        # ── Insert into database ──────────────────────────────────────
        hashed = make_password(password)   # PBKDF2-SHA256 hash

        conn = connect_db()
        cursor = conn.cursor()
        try:
            # Check for duplicate email
            cursor.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )
            if cursor.fetchone():
                self.stderr.write(self.style.ERROR(
                    f'An account with email "{email}" already exists.'
                ))
                return

            # Insert the Admin IT user
            cursor.execute(
                """
                INSERT INTO users (role, full_name, email, password)
                VALUES ('admin_it', %s, %s, %s)
                RETURNING id
                """,
                (full_name, email, hashed)
            )
            new_id = cursor.fetchone()['id']
            conn.commit()

            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Admin IT account created successfully.'
                f'\n  ID       : {new_id}'
                f'\n  Name     : {full_name}'
                f'\n  Email    : {email}'
                f'\n\nYou can now log in'
                f'\nSelect "Admin IT" on the landing page.\n'
            ))

        except Exception as exc:
            conn.rollback()
            self.stderr.write(self.style.ERROR(
                f'Database error: {exc}'
            ))
        finally:
            cursor.close()
            conn.close()