from datetime import date
from core.db import connect_db

class ResetAgent:

    def run(self):
        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── Fetch the current semester ────────────────────────────
            cursor.execute(
                """
                SELECT semester, end_date, stats_compiled
                FROM   semester_schedule
                WHERE  is_current = TRUE
                LIMIT  1
                """
            )
            current = cursor.fetchone()
            if not current:
                return  # No semester configured — nothing to do

            # ── Check if the semester has ended ───────────────────────
            today = date.today()
            if today <= current['end_date']:
                return  # Still inside the current semester

            if current['stats_compiled']:
                return  # Transition already done this semester

            semester = current['semester']

            # ── 1. Compile semester statistics ────────────────────────
            cursor.execute(
                """
                SELECT
                    COUNT(*)                                                       AS total,
                    COUNT(*) FILTER (WHERE final_status = 'Stable')               AS stable,
                    COUNT(*) FILTER (WHERE final_status = 'Challenged')            AS challenged,
                    COUNT(*) FILTER (WHERE final_status = 'Critical')              AS critical
                FROM questionnaire_responses
                WHERE semester        = %s
                AND   final_status    IS NOT NULL

                """,
                (semester,)
            )
            stats      = cursor.fetchone()
            total      = stats['total']      or 0
            stable     = stats['stable']     or 0
            challenged = stats['challenged'] or 0
            critical   = stats['critical']   or 0
            at_risk_pct = (
                round(((challenged + critical) / total) * 100, 2)
                if total > 0 else 0
            )

            cursor.execute(
                """
                INSERT INTO semester_stats
                    (semester, total, stable, challenged, critical, at_risk_pct)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (semester) DO UPDATE SET
                    total       = EXCLUDED.total,
                    stable      = EXCLUDED.stable,
                    challenged  = EXCLUDED.challenged,
                    critical    = EXCLUDED.critical,
                    at_risk_pct = EXCLUDED.at_risk_pct,
                    compiled_at = NOW()
                """,
                (semester, total, stable, challenged, critical, at_risk_pct)
            )

            # ── 2. Delete all questionnaire responses ────────────────
            # Stats have already been compiled into semester_stats above.
            # Deleting all rows means students start completely fresh
            # next semester — the chatbot will create new rows for them.
            cursor.execute("DELETE FROM questionnaire_responses")

            # ── 3. Delete all appointments ────────────────────────────
            cursor.execute("DELETE FROM appointments")

            # ── 4. Delete all events ──────────────────────────────────
            cursor.execute("DELETE FROM events")

            # ── 5. Mark stats compiled on outgoing semester ───────────
            cursor.execute(
                "UPDATE semester_schedule SET stats_compiled = TRUE "
                "WHERE semester = %s",
                (semester,)
            )

            # ── 6. Transition to the next semester ────────────────────
            cursor.execute(
                """
                SELECT semester
                FROM   semester_schedule
                WHERE  start_date > %s
                ORDER  BY start_date ASC
                LIMIT  1
                """,
                (current['end_date'],)
            )
            next_row = cursor.fetchone()
            if next_row:
                cursor.execute(
                    "UPDATE semester_schedule SET is_current = FALSE"
                )
                cursor.execute(
                    """
                    UPDATE semester_schedule
                    SET    is_current          = TRUE,
                           notification_pending = TRUE
                    WHERE  semester = %s
                    """,
                    (next_row['semester'],)
                )

            conn.commit()

        except Exception:
            conn.rollback()
            raise
        
        finally:
            cursor.close()
            conn.close()