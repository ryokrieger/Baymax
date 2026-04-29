import logging
from typing import Optional

from core.db import connect_db
from core.components import QUESTIONS, QUESTION_COLS, SCALE_MAX
from core.agents.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Fallback descriptions used when the LLM is unavailable ───────────
_FALLBACK: dict[str, str] = {
    'Stable': (
        'You are managing academic stress well this semester. '
        'Your responses indicate a healthy balance across stress, '
        'anxiety, and mood — keep maintaining the routines that are '
        'working for you. Remember that support is always available '
        'if things change.'
    ),
    'Challenged': (
        'You are experiencing moderate levels of stress and/or anxiety '
        'this semester. Your responses suggest some areas that could '
        'benefit from additional support — consider reaching out to a '
        'Mental Health Professional through the '
        'Request Mental Health Help page on your dashboard.'
    ),
    'Critical': (
        'Your responses indicate high levels of distress across '
        'multiple areas this semester. We strongly recommend connecting '
        'with a Mental Health Professional as soon as possible — click '
        'the button below and we will assign you to an available '
        'professional right away.'
    ),
}

# ── System-role prompt shared across all description requests ─────────
_SYSTEM_PROMPT = """\
You are Baymax, a compassionate and professional university mental health \
assistant. Your role is to write a brief, personalised status description \
for a student based on their completed mental health assessment.

Rules:
- Write exactly 2–3 sentences.
- Use second person ("You / Your").
- Be empathetic, supportive, and constructive — never alarmist.
- Do NOT diagnose any condition.
- Do NOT include a greeting, sign-off, or the student's name.
- Do NOT repeat the classification label verbatim.
- Tailor the tone to the severity: calm reassurance for Stable, \
gentle encouragement for Challenged, urgent compassion for Critical.\
"""


class TriageAgent:
    """
    AI Triage Agent — monitors student state and takes autonomous action.
    """

    def __init__(self) -> None:
        self._llm = LLMClient()

    # ─────────────────────────────────────────────────────────────────
    #  RESPONSIBILITY 1 — LLM-generated status description
    # ─────────────────────────────────────────────────────────────────

    def describe_student_status(
        self,
        student_id: int,
        semester:   str,
    ) -> str:
        """
        Generate (or retrieve cached) personalised status description.

        Flow:
          1. Load the student's questionnaire row.
          2. If a description is already stored, return it immediately
             (idempotent — avoids duplicate LLM calls on page refresh).
          3. Build a compact score + symptom summary.
          4. Call the LLM → get description.
          5. Persist to questionnaire_responses.status_description.
          6. Return the description string.

        Always returns a non-empty string — uses fallback if LLM fails.
        """
        conn   = connect_db()
        cursor = conn.cursor()
        try:
            # ── Step 1: load the row ──────────────────────────────────
            cursor.execute(
                'SELECT * FROM questionnaire_responses '
                'WHERE student_id = %s AND semester = %s',
                (student_id, semester),
            )
            qr = cursor.fetchone()

            if not qr or not qr['final_status']:
                # Assessment not complete yet — nothing to describe
                return ''

            # ── Step 2: return cached description if present ──────────
            existing = (qr.get('status_description') or '').strip()
            if existing:
                return existing

            final_status = qr['final_status']

            # ── Step 3: build compact score summary ───────────────────
            user_prompt = self._build_user_prompt(qr, final_status)

            # ── Step 4: call LLM ──────────────────────────────────────
            description = self._llm.chat(
                system     = _SYSTEM_PROMPT,
                user       = user_prompt,
                max_tokens = 200,
            )

            # Fallback if LLM returned nothing
            if not description:
                logger.info(
                    f'TriageAgent: LLM unavailable for student {student_id} '
                    f'— using fallback description.'
                )
                description = _FALLBACK.get(final_status, _FALLBACK['Stable'])

            # ── Step 5: persist ───────────────────────────────────────
            cursor.execute(
                'UPDATE questionnaire_responses '
                'SET    status_description = %s '
                'WHERE  student_id = %s AND semester = %s',
                (description, student_id, semester),
            )
            conn.commit()

            return description

        except Exception as exc:
            conn.rollback()
            logger.error(f'TriageAgent.describe_student_status error: {exc}')
            # Return in-memory fallback so the page still renders
            final_status = 'Stable'
            try:
                final_status = qr['final_status'] if qr else 'Stable'
            except Exception:
                pass
            return _FALLBACK.get(final_status, _FALLBACK['Stable'])

        finally:
            cursor.close()
            conn.close()

    # ── Private: prompt builder ───────────────────────────────────────

    def _build_user_prompt(self, qr, final_status: str) -> str:
        """
        Assemble a compact, LLM-friendly description of the student's
        responses.  We send per-scale averages + top 3 worst symptoms
        rather than all 26 raw scores to keep the prompt concise.
        """
        # Per-scale groups (column → scale key)
        scale_groups: dict[str, list] = {'pss': [], 'gad': [], 'phq': []}
        for col, scale, _text, _symptom in QUESTIONS:
            val = qr[col]
            if val is not None:
                scale_groups[scale].append(val)

        def avg(vals):
            return round(sum(vals) / len(vals), 2) if vals else 0.0

        pss_avg = avg(scale_groups['pss'])
        gad_avg = avg(scale_groups['gad'])
        phq_avg = avg(scale_groups['phq'])

        # Top 3 symptoms by raw score (higher = worse)
        scored = []
        for col, _scale, _text, symptom in QUESTIONS:
            val = qr[col]
            if val is not None and val > 0:
                scored.append((symptom, val))
        scored.sort(key=lambda x: x[1], reverse=True)
        top_symptoms = ', '.join(s for s, _ in scored[:3]) if scored else 'none reported'

        return (
            f'Mental health classification: {final_status}\n\n'
            f'Assessment scale averages (higher = more severe):\n'
            f'  • PSS-10 Perceived Stress  : {pss_avg:.2f} / 4.00\n'
            f'  • GAD-7  Anxiety           : {gad_avg:.2f} / 3.00\n'
            f'  • PHQ-9  Depression        : {phq_avg:.2f} / 3.00\n\n'
            f'Top 3 most elevated symptoms: {top_symptoms}\n\n'
            f'Write a personalised status description for this student '
            f'(2–3 sentences, supportive tone, second person, '
            f'no greeting or sign-off).'
        )

    # ─────────────────────────────────────────────────────────────────
    #  RESPONSIBILITY 2 — Professional assignment (rule-based, unchanged)
    # ─────────────────────────────────────────────────────────────────

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
                    'professional_name': (
                        existing['full_name'] if existing else 'a professional'
                    ),
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