from datetime import date
from core.db import connect_db

class ResetAgent:
    """
    Automatically performs a mid-semester bulk questionnaire reset
    when the configured reset date has been reached.
    """
    
    def run(self) -> None:
        """
        Check the current semester's reset_date and fire the bulk
        reset if the date has passed and it has not been done yet.

        Returns:
            None.  All side-effects are DB writes.
        """
        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── Step 1: fetch the active semester row ─────────────────
            cursor.execute(
                """
                SELECT semester, reset_date, bulk_reset_performed
                FROM   semester_schedule
                WHERE  is_current = TRUE
                LIMIT  1
                """
            )
            row = cursor.fetchone()

            # No active semester configured — nothing to do
            if not row:
                return

            # Conditions: reset_date set, not yet performed, date reached
            if not row['reset_date']:
                return
            if row['bulk_reset_performed']:
                return
            if date.today() < row['reset_date']:
                return

            semester = row['semester']

            # ── Step 2a: upsert every student's response row ──────────
            # For students who already have a row this semester:
            #   -> set responses_reset = TRUE
            # For students who don't have a row yet:
            #   -> insert one with responses_reset = TRUE, final_status = NULL
            #   This ensures the chatbot launches for ALL students on
            #   their next login regardless of whether they've assessed yet.
            cursor.execute(
                """
                INSERT INTO questionnaire_responses
                    (student_id, semester, responses_reset, final_status)
                SELECT user_id, %s, TRUE, NULL
                FROM   students
                ON CONFLICT (student_id, semester)
                DO UPDATE SET responses_reset = TRUE
                """,
                (semester,)
            )

            # ── Step 2b: mark reset done + set notification flag ──────
            cursor.execute(
                """
                UPDATE semester_schedule
                SET    bulk_reset_performed = TRUE,
                       notification_pending  = TRUE
                WHERE  is_current = TRUE
                """
            )

            conn.commit()

        except Exception:
            conn.rollback()
            # Silently swallow — a reset failure must never block a
            # student from logging in.  Errors will surface in server logs.
            raise
        finally:
            cursor.close()
            conn.close()