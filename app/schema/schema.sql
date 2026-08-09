CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    role       VARCHAR(20) NOT NULL
                   CHECK (role IN ('student','professional','authority','admin_it')),
    full_name  VARCHAR(120) NOT NULL,
    email      VARCHAR(254) UNIQUE NOT NULL,
    password   VARCHAR(256) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS students (
    id         SERIAL PRIMARY KEY,
    user_id    INT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_id VARCHAR(30) NOT NULL,
    department VARCHAR(10) NOT NULL CHECK (department IN ('CSE','EEE','ENG','ECO','BBA'))
);

CREATE TABLE IF NOT EXISTS semester_schedule (
    id                   SERIAL PRIMARY KEY,
    semester             VARCHAR(20) UNIQUE NOT NULL,
    start_date           DATE NOT NULL,
    end_date             DATE NOT NULL,
    is_current           BOOLEAN DEFAULT FALSE,
    stats_compiled       BOOLEAN DEFAULT FALSE,
    notification_pending BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS semester_stats (
    id          SERIAL PRIMARY KEY,
    semester    VARCHAR(20) UNIQUE NOT NULL,
    total       INT DEFAULT 0,
    stable      INT DEFAULT 0,
    challenged  INT DEFAULT 0,
    critical    INT DEFAULT 0,
    at_risk_pct DECIMAL(5,2) DEFAULT 0,
    llm_summary TEXT,
    compiled_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS questionnaire_responses (
    id              SERIAL PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    semester        VARCHAR(20) NOT NULL,
    pss1  SMALLINT, pss2  SMALLINT, pss3  SMALLINT, pss4  SMALLINT,
    pss5  SMALLINT, pss6  SMALLINT, pss7  SMALLINT, pss8  SMALLINT,
    pss9  SMALLINT, pss10 SMALLINT,
    gad1  SMALLINT, gad2  SMALLINT, gad3  SMALLINT, gad4  SMALLINT,
    gad5  SMALLINT, gad6  SMALLINT, gad7  SMALLINT,
    phq1  SMALLINT, phq2  SMALLINT, phq3  SMALLINT, phq4  SMALLINT,
    phq5  SMALLINT, phq6  SMALLINT, phq7  SMALLINT, phq8  SMALLINT,
    phq9  SMALLINT,
    final_status       VARCHAR(20) CHECK (final_status IN ('Stable','Challenged','Critical')),
    status_description TEXT,
    submitted_at       TIMESTAMP DEFAULT NOW(),
    UNIQUE (student_id, semester)
);

CREATE TABLE IF NOT EXISTS appointments (
    id              SERIAL PRIMARY KEY,
    student_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    professional_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) DEFAULT 'pending'
                        CHECK (status IN ('pending','accepted','declined','completed')),
    scheduled_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    date        DATE NOT NULL,
    time        TIME NOT NULL,
    venue       VARCHAR(200) NOT NULL,
    description TEXT,
    rsvp_count  INT DEFAULT 0,
    created_by  INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS event_rsvps (
    id         SERIAL PRIMARY KEY,
    student_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id   INT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    rsvped_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (student_id, event_id)
);

CREATE TABLE IF NOT EXISTS analytics_alerts (
    id         SERIAL PRIMARY KEY,
    alert_type VARCHAR(30) NOT NULL
                   CHECK (alert_type IN ('critical_surge','symptom_spike','department_at_risk')),
    message    TEXT NOT NULL,
    semester   VARCHAR(20),
    department VARCHAR(10),
    dismissed  BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);