from core.db import connect_db

class TriageAgent:
    """
    Automatically assigns a Critical student to the best-fit
    Mental Health Professional.
    """

    def run(self, student_id: int) -> dict:
        """
        Find the available professional with the lowest active student
        count and create a pending appointment for the given student.

        Args:
            student_id: The users.id of the Critical student
                        (same as students.user_id).

        Returns:
            {'assigned': True,  'professional_name': 'Dr. Jane Doe'}
                — professional was successfully assigned.
            {'assigned': False}
                — all professionals are at or above the 12-student cap.
        """
        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── Step 1: check student doesn't already have an active
            #            appointment (pending or accepted).
            #            Guard against double-assignment on rapid clicks.
            cursor.execute(
                """
                SELECT id FROM appointments
                WHERE  student_id = %s
                AND    status IN ('pending', 'accepted')
                LIMIT  1
                """,
                (student_id,)
            )
            if cursor.fetchone():
                # Already has an active appointment — return as if assigned
                # so the result screen doesn't show a confusing error.
                cursor.execute(
                    """
                    SELECT u.full_name
                    FROM   appointments a
                    JOIN   users u ON u.id = a.professional_id
                    WHERE  a.student_id = %s
                    AND    a.status IN ('pending', 'accepted')
                    LIMIT  1
                    """,
                    (student_id,)
                )
                existing = cursor.fetchone()
                return {
                    'assigned': True,
                    'professional_name': existing['full_name'] if existing else 'a professional',
                }

            # ── Step 2: find the best-fit professional ────────────────
            cursor.execute(
                """
                SELECT  u.id,
                        u.full_name,
                        COUNT(a.id) AS active_count
                FROM    users u
                LEFT JOIN appointments a
                       ON a.professional_id = u.id
                       AND a.status = 'accepted'
                WHERE   u.role = 'professional'
                GROUP BY u.id, u.full_name
                HAVING  COUNT(a.id) < 12
                ORDER BY active_count ASC, u.id ASC
                LIMIT  1
                """
            )
            professional = cursor.fetchone()

            if not professional:
                return {'assigned': False}

            # ── Step 3: create the pending appointment ─────────────────
            cursor.execute(
                """
                INSERT INTO appointments
                    (student_id, professional_id, status)
                VALUES (%s, %s, 'pending')
                """,
                (student_id, professional['id'])
            )
            conn.commit()

            return {
                'assigned':          True,
                'professional_name': professional['full_name'],
            }

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()