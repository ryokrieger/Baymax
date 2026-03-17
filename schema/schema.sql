CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    role          VARCHAR(20) NOT NULL
                      CHECK (role IN ('student','professional','authority','admin_it')),
    full_name     VARCHAR(150) NOT NULL,
    email         VARCHAR(254) NOT NULL UNIQUE,
    password      VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    user_id       INT PRIMARY KEY
                      REFERENCES users(id) ON DELETE CASCADE,
    student_id    VARCHAR(50)  NOT NULL,
    department    VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS questionnaire_responses (
    id               SERIAL PRIMARY KEY,
    student_id       INT NOT NULL
                         REFERENCES students(user_id) ON DELETE CASCADE,
    semester         VARCHAR(20) NOT NULL,

    pss1   INT, pss2  INT, pss3  INT, pss4  INT, pss5  INT,
    pss6   INT, pss7  INT, pss8  INT, pss9  INT, pss10 INT,

    gad1   INT, gad2  INT, gad3  INT, gad4  INT,
    gad5   INT, gad6  INT, gad7  INT,

    phq1   INT, phq2  INT, phq3  INT, phq4  INT, phq5  INT,
    phq6   INT, phq7  INT, phq8  INT, phq9  INT,

    final_status     VARCHAR(20),
    responses_reset  BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (student_id, semester)
);

CREATE TABLE IF NOT EXISTS appointments (
    id               SERIAL PRIMARY KEY,
    student_id       INT NOT NULL
                         REFERENCES students(user_id) ON DELETE CASCADE,
    professional_id  INT NOT NULL
                         REFERENCES users(id)         ON DELETE CASCADE,
    status           VARCHAR(20) NOT NULL
                         CHECK (status IN ('pending','accepted','declined','completed')),
    scheduled_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    date        DATE         NOT NULL,
    time        TIME         NOT NULL,
    venue       VARCHAR(200) NOT NULL,
    description TEXT,
    rsvp_count  INT          NOT NULL DEFAULT 0,
    created_by  INT          NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS event_rsvps (
    student_id  INT NOT NULL REFERENCES students(user_id) ON DELETE CASCADE,
    event_id    INT NOT NULL REFERENCES events(id)        ON DELETE CASCADE,
    PRIMARY KEY (student_id, event_id)
);

CREATE TABLE IF NOT EXISTS analytics_alerts (
    id          SERIAL PRIMARY KEY,
    alert_type  VARCHAR(30) NOT NULL
                    CHECK (alert_type IN ('critical_surge','symptom_spike','department_at_risk')),
    message     TEXT        NOT NULL,
    semester    VARCHAR(20) NOT NULL,
    department  VARCHAR(100),
    dismissed   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS semester_schedule (
    semester              VARCHAR(20) PRIMARY KEY,
    reset_date            DATE,
    bulk_reset_performed  BOOLEAN NOT NULL DEFAULT FALSE,
    is_current            BOOLEAN NOT NULL DEFAULT FALSE,
    notification_pending  BOOLEAN NOT NULL DEFAULT FALSE
);