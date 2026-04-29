import logging
from datetime import date

from core.db import connect_db
from core.agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── System-role prompt for semester summary ───────────────────────────────────
_SYSTEM_PROMPT = """\
You are Baymax, a university mental health analytics assistant writing \
for institutional records and mental health professionals.

Rules:
- Write exactly 3–4 sentences.
- Use third person and a professional, objective tone.
- Mention the overall at-risk percentage and the dominant status category.
- Note any significant concern or positive pattern in the data.
- End with a single, concrete institutional recommendation.
- No greeting, no sign-off, no bullet points.\
"""

# Valid semester name tokens
VALID_SEMESTER_NAMES = ('Spring', 'Summer', 'Fall')


class ResetAgent:
    """
    AI Reset Agent — performs admin-triggered semester transitions and
    compiles end-of-semester statistics with an LLM-generated narrative
    summary.

    Transition is fully manual: the Admin IT user selects the target
    semester (name + year) in the dashboard and presses the transition
    button.  There is no automatic date-based trigger.
    """

    def __init__(self) -> None:
        self._llm = LLMClient()

    # ─────────────────────────────────────────────────────────────────────────
    #  PUBLIC — Manual semester transition
    # ─────────────────────────────────────────────────────────────────────────

    def transition(self, target_semester: str) -> dict:
        """
        Perform a full semester transition to *target_semester*.

        Steps executed inside a single transaction:
          1. Read and validate the current semester.
          2. Guard: target must differ from the current semester.
          3. Compile final statistics for the outgoing semester.
          4. Generate an LLM narrative summary.
          5. Persist compiled stats to ``semester_stats``.
          6. Delete all questionnaire responses.
          7. Delete all appointments.
          8. Delete all events.
          9. Mark the outgoing semester ``stats_compiled = TRUE``,
             ``is_current = FALSE``.
         10. Upsert the target semester into ``semester_schedule`` and
             mark it ``is_current = TRUE``, ``notification_pending = TRUE``.

        Parameters
        ----------
        target_semester : str
            The full semester label to activate, e.g. ``"Spring 2026"``.

        Returns
        -------
        dict
            ``{'success': True, 'outgoing': str, 'incoming': str}``
            on success, or ``{'success': False, 'error': str}`` on failure.
        """
        if not target_semester or not target_semester.strip():
            return {'success': False, 'error': 'Target semester label is empty.'}

        target_semester = target_semester.strip()

        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── 1. Fetch the current semester ─────────────────────────────
            cursor.execute(
                """
                SELECT semester, stats_compiled
                FROM   semester_schedule
                WHERE  is_current = TRUE
                LIMIT  1
                """
            )
            current = cursor.fetchone()

            outgoing_semester = current['semester'] if current else None

            # ── 2. Guard: must not transition to the same semester ────────
            if outgoing_semester and outgoing_semester == target_semester:
                return {
                    'success': False,
                    'error':   (
                        f'"{target_semester}" is already the active semester. '
                        f'Please select a different semester.'
                    ),
                }

            # ── 3. Compile final stats for the outgoing semester ──────────
            if outgoing_semester:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*)                                                 AS total,
                        COUNT(*) FILTER (WHERE final_status = 'Stable')         AS stable,
                        COUNT(*) FILTER (WHERE final_status = 'Challenged')     AS challenged,
                        COUNT(*) FILTER (WHERE final_status = 'Critical')       AS critical
                    FROM  questionnaire_responses
                    WHERE semester     = %s
                    AND   final_status IS NOT NULL
                    """,
                    (outgoing_semester,)
                )
                stats      = cursor.fetchone()
                total      = stats['total']      or 0
                stable     = stats['stable']     or 0
                challenged = stats['challenged'] or 0
                critical   = stats['critical']   or 0
                at_risk_pct = (
                    round(((challenged + critical) / total) * 100, 2)
                    if total > 0 else 0.0
                )

                # ── 4. Generate LLM semester summary ──────────────────────
                llm_summary = self._generate_semester_summary(
                    semester    = outgoing_semester,
                    total       = total,
                    stable      = stable,
                    challenged  = challenged,
                    critical    = critical,
                    at_risk_pct = at_risk_pct,
                )

                # ── 5. Persist compiled stats ──────────────────────────────
                cursor.execute(
                    """
                    INSERT INTO semester_stats
                        (semester, total, stable, challenged, critical,
                         at_risk_pct, llm_summary)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (semester) DO UPDATE SET
                        total       = EXCLUDED.total,
                        stable      = EXCLUDED.stable,
                        challenged  = EXCLUDED.challenged,
                        critical    = EXCLUDED.critical,
                        at_risk_pct = EXCLUDED.at_risk_pct,
                        llm_summary = EXCLUDED.llm_summary,
                        compiled_at = NOW()
                    """,
                    (outgoing_semester, total, stable, challenged, critical,
                     at_risk_pct, llm_summary)
                )

            # ── 6. Delete all questionnaire responses ─────────────────────
            cursor.execute('DELETE FROM questionnaire_responses')

            # ── 7. Delete all appointments ────────────────────────────────
            cursor.execute('DELETE FROM appointments')

            # ── 8. Delete all events ──────────────────────────────────────
            cursor.execute('DELETE FROM events')

            # ── 9. Mark outgoing semester as compiled and inactive ────────
            if outgoing_semester:
                cursor.execute(
                    """
                    UPDATE semester_schedule
                    SET    is_current     = FALSE,
                           stats_compiled = TRUE
                    WHERE  semester = %s
                    """,
                    (outgoing_semester,)
                )
            else:
                # No current semester — deactivate everything as a safety net
                cursor.execute(
                    'UPDATE semester_schedule SET is_current = FALSE'
                )

            # ── 10. Upsert the target semester and activate it ────────────
            today = date.today()

            cursor.execute(
                """
                INSERT INTO semester_schedule
                    (semester, start_date, end_date,
                     is_current, stats_compiled, notification_pending)
                VALUES (%s, %s, %s, TRUE, FALSE, TRUE)
                ON CONFLICT (semester) DO UPDATE SET
                    is_current           = TRUE,
                    stats_compiled       = FALSE,
                    notification_pending = TRUE,
                    start_date           = EXCLUDED.start_date
                """,
                (target_semester, today, today)
            )

            # Ensure no other row is still flagged as current
            cursor.execute(
                """
                UPDATE semester_schedule
                SET    is_current = FALSE
                WHERE  semester  != %s
                """,
                (target_semester,)
            )

            conn.commit()

            logger.info(
                'ResetAgent.transition: "%s" -> "%s" completed successfully.',
                outgoing_semester,
                target_semester,
            )

            return {
                'success':  True,
                'outgoing': outgoing_semester,
                'incoming': target_semester,
            }

        except Exception as exc:
            conn.rollback()
            logger.exception(
                'ResetAgent.transition failed for target="%s": %s',
                target_semester,
                exc,
            )
            return {'success': False, 'error': str(exc)}

        finally:
            cursor.close()
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    #  PRIVATE — LLM semester summary generator
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_semester_summary(
        self,
        semester:    str,
        total:       int,
        stable:      int,
        challenged:  int,
        critical:    int,
        at_risk_pct: float,
    ) -> str | None:
        """
        Ask the LLM to write a professional narrative summary of the
        semester's mental health statistics.

        Returns the summary string, or ``None`` if the LLM is unavailable
        (the caller stores NULL and the UI shows a fallback notice).
        """
        if total == 0:
            return None

        stable_pct     = round((stable     / total) * 100, 1)
        challenged_pct = round((challenged / total) * 100, 1)
        critical_pct   = round((critical   / total) * 100, 1)

        user_prompt = (
            f'Semester: {semester}\n'
            f'Total students assessed: {total}\n\n'
            f'Status breakdown:\n'
            f'  • Stable     : {stable} students ({stable_pct}%)\n'
            f'  • Challenged : {challenged} students ({challenged_pct}%)\n'
            f'  • Critical   : {critical} students ({critical_pct}%)\n'
            f'  • At-risk (Challenged + Critical): {at_risk_pct}%\n\n'
            f'Write a 3–4 sentence professional semester mental health '
            f'summary for institutional records.'
        )

        summary = self._llm.chat(
            system     = _SYSTEM_PROMPT,
            user       = user_prompt,
            max_tokens = 220,
        )

        if not summary:
            logger.info(
                'ResetAgent: LLM unavailable for %s summary '
                '— llm_summary will be NULL.',
                semester,
            )

        return summary