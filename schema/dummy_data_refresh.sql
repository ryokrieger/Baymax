-- Baymax seed refresh.
-- Run AFTER dummy_data.sql (and schema_additions.sql).
-- Safe to run more than once: dates are recalculated
-- from today's date each time.
--
-- Why: dummy_data.sql was written for Spring 2026 and its events are dated
-- March-May 2026. Past events are hidden by design, so without this script
-- the events pages would be empty.

BEGIN;

-- 1. Make Fall 2026 the current semester and move the seed responses into it.
UPDATE semester_schedule SET is_current = FALSE;
UPDATE semester_schedule SET is_current = TRUE WHERE semester = 'Fall 2026';

UPDATE questionnaire_responses SET semester = 'Fall 2026'
WHERE semester = 'Spring 2026';

-- 2. Events: spread the seven seed events over the next ~9 weeks.
UPDATE events SET date = CURRENT_DATE + (id * 9);

-- 3. Appointments: accepted ones become upcoming (keeping their time of day);
--    completed ones stay in the past. Only pending requests are "new".
UPDATE appointments
SET scheduled_at = (CURRENT_DATE + ((id % 5) + 1))::timestamp + scheduled_at::time
WHERE status = 'accepted';

UPDATE appointments SET is_new = (status = 'pending');

COMMIT;