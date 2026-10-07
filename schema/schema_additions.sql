-- Baymax schema additions.
-- Run AFTER schema.sql.
-- Safe to run more than once.

-- Sprint 6: "Deactivate user". Deactivated accounts cannot log in.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- Sprint 4: notification badge for new appointment requests.
-- TRUE when a request is created; set to FALSE when the professional views it.
ALTER TABLE appointments
    ADD COLUMN IF NOT EXISTS is_new BOOLEAN NOT NULL DEFAULT TRUE;