-- All times of day are stored as minutes since midnight in the user's time zone.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    work_start    INTEGER NOT NULL DEFAULT 540,
    work_end      INTEGER NOT NULL DEFAULT 1080,
    work_days     TEXT    NOT NULL DEFAULT '0,1,2,3,4',  -- Monday = 0
    timezone      TEXT    NOT NULL DEFAULT 'UTC',
    slot_minutes  INTEGER NOT NULL DEFAULT 30,
    rest_minutes  INTEGER NOT NULL DEFAULT 0,             -- break after a task
    rest_min_task INTEGER NOT NULL DEFAULT 0,             -- only after tasks at least this long
    review_prompt TEXT    NOT NULL DEFAULT 'eod',         -- slot | eod | off
    onboarded     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS fixed_breaks (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label     TEXT    NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reset_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS days (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date      TEXT    NOT NULL,
    locked_at TEXT,  -- set when the plan is committed; later tasks are unplanned
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date          TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    duration      INTEGER NOT NULL,
    priority      INTEGER NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',  -- pending | scheduled | cannot_do | moved
    cannot_reason TEXT,                                -- auto | manual
    unplanned     INTEGER NOT NULL DEFAULT 0,          -- added after the plan was locked
    start_min     INTEGER,                             -- when unplanned work happened
    moved_to      TEXT,
    created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meetings (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date      TEXT    NOT NULL,
    title     TEXT    NOT NULL,
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date      TEXT    NOT NULL,
    task_id   INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind      TEXT    NOT NULL DEFAULT 'task',  -- task | rest
    start_min INTEGER NOT NULL,
    end_min   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS actuals (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date       TEXT    NOT NULL,
    slot_start INTEGER NOT NULL,
    kind       TEXT    NOT NULL,  -- as_planned | other
    note       TEXT,
    PRIMARY KEY (user_id, date, slot_start)
);

CREATE INDEX IF NOT EXISTS idx_tasks_day    ON tasks(user_id, date);
CREATE INDEX IF NOT EXISTS idx_blocks_day   ON blocks(user_id, date);
CREATE INDEX IF NOT EXISTS idx_meetings_day ON meetings(user_id, date);
