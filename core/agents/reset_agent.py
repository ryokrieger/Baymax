import logging
from datetime import date

from core.db import connect_db
from core.agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── System-role prompt for semester summary ───────────────────────────
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


class ResetAgent:
    """
    AI Reset Agent — monitors semester state and autonomously compiles
    end-of-semester statistics with an LLM-generated narrative summary.
    """

    def __init__(self) -> None:
        self._llm = LLMClient()

    # ─────────────────────────────────────────────────────────────────
    #  MAIN ENTRY POINT
    # ─────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Autonomously check system state and perform the semester
        transition if conditions are met.

        State checks (all must pass before any action is taken):
          • A current semester is configured.
          • today > semester end_date.
          • stats_compiled is FALSE (idempotent guard).
        """
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
                    COUNT(*)                                                   AS total,
                    COUNT(*) FILTER (WHERE final_status = 'Stable')           AS stable,
                    COUNT(*) FILTER (WHERE final_status = 'Challenged')        AS challenged,
                    COUNT(*) FILTER (WHERE final_status = 'Critical')          AS critical
                FROM questionnaire_responses
                WHERE semester     = %s
                AND   final_status IS NOT NULL
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

            # ── 2. Generate LLM semester summary ─────────────────────
            llm_summary = self._generate_semester_summary(
                semester    = semester,
                total       = total,
                stable      = stable,
                challenged  = challenged,
                critical    = critical,
                at_risk_pct = at_risk_pct,
            )

            # ── 3. Persist compiled stats + summary ───────────────────
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
                (semester, total, stable, challenged, critical,
                 at_risk_pct, llm_summary)
            )

            # ── 4. Delete all questionnaire responses ─────────────────
            cursor.execute('DELETE FROM questionnaire_responses')

            # ── 5. Delete all appointments ────────────────────────────
            cursor.execute('DELETE FROM appointments')

            # ── 6. Delete all events ──────────────────────────────────
            cursor.execute('DELETE FROM events')

            # ── 7. Mark stats compiled on outgoing semester ───────────
            cursor.execute(
                'UPDATE semester_schedule SET stats_compiled = TRUE '
                'WHERE semester = %s',
                (semester,)
            )

            # ── 8. Transition to the next semester ────────────────────
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
                    'UPDATE semester_schedule SET is_current = FALSE'
                )
                cursor.execute(
                    """
                    UPDATE semester_schedule
                    SET    is_current           = TRUE,
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

    # ─────────────────────────────────────────────────────────────────
    #  PRIVATE — LLM semester summary generator
    # ─────────────────────────────────────────────────────────────────

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

        Returns the summary string, or None if the LLM is unavailable
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
                f'ResetAgent: LLM unavailable for {semester} summary '
                f'— llm_summary will be NULL.'
            )

        return summary