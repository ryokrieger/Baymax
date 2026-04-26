from core.db import connect_db
from core.components import QUESTIONS, QUESTION_COLS


class AnalyticsAgent:

    def run(self, semester: str) -> list:
        """
        Run all three detection checks and return undismissed alerts.

        Args:
            semester: Label of the current semester (e.g. "Spring 2026").

        Returns:
            List of analytics_alerts row dicts (may be empty).
        """
        if not semester:
            return []

        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── 1. Critical Surge ──────────────────────────────────────
            self._check_critical_surge(cursor, semester)

            # ── 2. Symptom Spike ───────────────────────────────────────
            self._check_symptom_spike(cursor, semester)

            # ── 3. Department at Risk ──────────────────────────────────
            self._check_departments_at_risk(cursor, semester)

            conn.commit()

            # ── Return all undismissed alerts for this semester ────────
            cursor.execute(
                """
                SELECT id, alert_type, message, semester,
                       department, dismissed, created_at
                FROM   analytics_alerts
                WHERE  semester  = %s
                AND    dismissed = FALSE
                ORDER  BY created_at DESC
                """,
                (semester,)
            )
            return cursor.fetchall()

        except Exception:
            conn.rollback()
            raise

        finally:
            cursor.close()
            conn.close()

    # ─────────────────────────────────────────────────────────────────
    #  CHECK 1 — Critical Surge
    # ─────────────────────────────────────────────────────────────────
    def _check_critical_surge(self, cursor, semester):
        """
        Alert when Critical students exceed 40 % of all assessed students
        in the given semester.
        """
        cursor.execute(
            """
            SELECT
                COUNT(*)                                            AS total,
                COUNT(*) FILTER (WHERE final_status = 'Critical')  AS critical_count
            FROM questionnaire_responses
            WHERE semester     = %s
            AND   final_status IS NOT NULL
            """,
            (semester,)
        )
        row      = cursor.fetchone()
        total    = row['total']         or 0
        critical = row['critical_count'] or 0

        if total == 0:
            return

        if (critical / total) > 0.40:
            # Skip if an alert already exists for this semester
            cursor.execute(
                """
                SELECT id FROM analytics_alerts
                WHERE alert_type = 'critical_surge'
                AND   semester   = %s
                """,
                (semester,)
            )
            if cursor.fetchone():
                return

            pct = round((critical / total) * 100, 1)
            cursor.execute(
                """
                INSERT INTO analytics_alerts
                    (alert_type, message, semester, department, dismissed)
                VALUES ('critical_surge', %s, %s, NULL, FALSE)
                """,
                (
                    f"Critical student count has reached {critical} out of "
                    f"{total} assessed students ({pct}%) in {semester}, "
                    f"exceeding the 40% threshold.",
                    semester,
                )
            )

    # ─────────────────────────────────────────────────────────────────
    #  CHECK 2 — Symptom Spike
    # ─────────────────────────────────────────────────────────────────
    def _check_symptom_spike(self, cursor, semester):
        """
        Compare the top-3 symptoms of the current semester against the
        top-3 symptoms of the immediately preceding semester.

        Semester ordering within a year: Spring < Summer < Fall.
        Across years: earlier years come first.
        """
        # Build mapping from DB column name to symptom label
        col_to_symptom = {q[0]: q[3] for q in QUESTIONS}

        # Get top-3 symptoms for the current semester
        current_top3 = self._top3_symptoms(cursor, semester, col_to_symptom)
        if not current_top3:
            return

        # Find the previous semester
        prev_semester = self._previous_semester(cursor, semester)
        if not prev_semester:
            return

        # Get top-3 symptoms for the previous semester
        prev_top3 = self._top3_symptoms(cursor, prev_semester, col_to_symptom)
        if not prev_top3:
            return

        # Find overlapping symptoms
        overlap = set(current_top3) & set(prev_top3)
        if not overlap:
            return

        # Insert one alert per overlapping symptom (skip duplicates)
        for symptom in overlap:
            cursor.execute(
                """
                SELECT id FROM analytics_alerts
                WHERE alert_type = 'symptom_spike'
                AND   semester   = %s
                AND   message LIKE %s
                """,
                (semester, f"%{symptom}%")
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                """
                INSERT INTO analytics_alerts
                    (alert_type, message, semester, department, dismissed)
                VALUES ('symptom_spike', %s, %s, NULL, FALSE)
                """,
                (
                    f"Symptom '{symptom}' appeared in the top 3 most prevalent "
                    f"symptoms in both {prev_semester} and {semester}, "
                    f"indicating a persistent pattern.",
                    semester,
                )
            )

    def _top3_symptoms(self, cursor, semester, col_to_symptom):
        """
        Return the top-3 symptom labels (by student count) for a semester.
        For each question column, count how many students scored > 0.
        Returns a list of up to 3 symptom label strings.
        """
        counts = []
        for col in QUESTION_COLS:
            cursor.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM   questionnaire_responses
                WHERE  semester    = %s
                AND    final_status IS NOT NULL
                AND    {col}       > 0
                """,
                (semester,)
            )
            row = cursor.fetchone()
            cnt = row['cnt'] if row else 0
            counts.append((col, cnt))

        # Sort descending by count
        counts.sort(key=lambda x: x[1], reverse=True)

        top3 = []
        for col, cnt in counts[:3]:
            if cnt > 0 and col in col_to_symptom:
                top3.append(col_to_symptom[col])
        return top3

    def _previous_semester(self, cursor, current_semester):
        """
        Find the semester that immediately precedes current_semester.

        Ordering: Spring < Summer < Fall within a year;
                  earlier years before later years.
        """
        SEASON_ORDER = {'Spring': 0, 'Summer': 1, 'Fall': 2}

        cursor.execute(
            "SELECT semester FROM semester_schedule ORDER BY semester"
        )
        rows = cursor.fetchall()
        if not rows:
            return None

        def sort_key(sem_label):
            parts = sem_label.split()
            if len(parts) == 2:
                season, year = parts[0], parts[1]
                try:
                    return (int(year), SEASON_ORDER.get(season, 99))
                except ValueError:
                    pass
            return (9999, 99)

        semesters = sorted([r['semester'] for r in rows], key=sort_key)

        try:
            idx = semesters.index(current_semester)
        except ValueError:
            return None

        if idx == 0:
            return None
        return semesters[idx - 1]

    # ─────────────────────────────────────────────────────────────────
    #  CHECK 3 — Department at Risk
    # ─────────────────────────────────────────────────────────────────
    def _check_departments_at_risk(self, cursor, semester):
        """
        Alert when Critical + Challenged students exceed 60 % of all
        assessed students in a single department.
        """
        cursor.execute(
            """
            SELECT
                s.department,
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE qr.final_status IN ('Critical', 'Challenged')
                ) AS at_risk_count
            FROM   questionnaire_responses qr
            JOIN   students s ON s.user_id = qr.student_id
            WHERE  qr.semester     = %s
            AND    qr.final_status IS NOT NULL
            GROUP  BY s.department
            """,
            (semester,)
        )
        rows = cursor.fetchall()

        for row in rows:
            dept    = row['department']
            total   = row['total']         or 0
            at_risk = row['at_risk_count'] or 0

            if total == 0:
                continue

            if (at_risk / total) > 0.60:
                # Skip if an alert already exists for this semester + dept
                cursor.execute(
                    """
                    SELECT id FROM analytics_alerts
                    WHERE alert_type = 'department_at_risk'
                    AND   semester   = %s
                    AND   department = %s
                    """,
                    (semester, dept)
                )
                if cursor.fetchone():
                    continue

                pct = round((at_risk / total) * 100, 1)
                cursor.execute(
                    """
                    INSERT INTO analytics_alerts
                        (alert_type, message, semester, department, dismissed)
                    VALUES ('department_at_risk', %s, %s, %s, FALSE)
                    """,
                    (
                        f"{dept} had {at_risk} out of {total} assessed students "
                        f"({pct}%) classified as Critical or Challenged in "
                        f"{semester}, exceeding the 60% threshold.",
                        semester,
                        dept,
                    )
                )