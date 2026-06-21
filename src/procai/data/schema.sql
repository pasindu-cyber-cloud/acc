-- ProcAI local database schema (SQLite).
-- All data stays on the user's machine. No telemetry leaves the device.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Schema/version bookkeeping ------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Key/value user settings (mirror of settings.json) ------------------------
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);

-- Rolling process telemetry history ----------------------------------------
CREATE TABLE IF NOT EXISTS process_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              REAL    NOT NULL,
    pid             INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    exe_path        TEXT,
    username        TEXT,
    ppid            INTEGER,
    parent_name     TEXT,
    cpu_percent     REAL,
    memory_rss      INTEGER,
    memory_percent  REAL,
    num_threads     INTEGER,
    num_handles     INTEGER,
    num_connections INTEGER,
    is_signed       INTEGER,            -- 0/1/NULL(unknown)
    in_suspicious_dir INTEGER,
    risk_score      REAL,
    severity        INTEGER
);
CREATE INDEX IF NOT EXISTS idx_proc_hist_ts   ON process_history (ts);
CREATE INDEX IF NOT EXISTS idx_proc_hist_pid  ON process_history (pid);
CREATE INDEX IF NOT EXISTS idx_proc_hist_name ON process_history (name);

-- Alerts --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                REAL    NOT NULL,
    pid               INTEGER NOT NULL,
    process_name      TEXT    NOT NULL,
    exe_path          TEXT,
    username          TEXT,
    risk_score        REAL    NOT NULL,
    severity          INTEGER NOT NULL,
    confidence        REAL    NOT NULL,
    reasons_json      TEXT,               -- JSON list[str]
    rule_hits_json    TEXT,               -- JSON list[str]
    ml_probability    REAL,
    recommended_action TEXT,
    acknowledged      INTEGER NOT NULL DEFAULT 0,
    resolution        TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts       ON alerts (ts);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity);
CREATE INDEX IF NOT EXISTS idx_alerts_ack      ON alerts (acknowledged);

-- Per-executable baseline snapshots (Welford running stats) -----------------
CREATE TABLE IF NOT EXISTS baselines (
    identity_key  TEXT NOT NULL,
    metric        TEXT NOT NULL,
    count         INTEGER NOT NULL,
    mean          REAL NOT NULL,
    m2            REAL NOT NULL,          -- sum of squared deviations (for variance)
    min_value     REAL,
    max_value     REAL,
    updated_at    REAL NOT NULL,
    PRIMARY KEY (identity_key, metric)
);

-- Trained model metadata ----------------------------------------------------
CREATE TABLE IF NOT EXISTS model_metadata (
    name           TEXT PRIMARY KEY,
    algorithm      TEXT NOT NULL,
    trained_at     REAL NOT NULL,
    n_samples      INTEGER NOT NULL,
    n_features     INTEGER NOT NULL,
    feature_names_json TEXT NOT NULL,
    accuracy       REAL,
    precision_     REAL,
    recall         REAL,
    f1             REAL,
    notes          TEXT
);

-- Allow / block list --------------------------------------------------------
CREATE TABLE IF NOT EXISTS reputation_list (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    list_type  TEXT NOT NULL,             -- 'allow' | 'block'
    pattern    TEXT NOT NULL,             -- process name or exe path (lowercased)
    note       TEXT,
    created_at REAL NOT NULL,
    UNIQUE (list_type, pattern)
);

-- Labelled samples for ML retraining ----------------------------------------
CREATE TABLE IF NOT EXISTS labelled_samples (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    features_json TEXT NOT NULL,          -- JSON dict[str, float]
    label        INTEGER NOT NULL,        -- 0 normal, 1 suspicious
    source       TEXT NOT NULL DEFAULT 'user'  -- user|simulation|imported
);
