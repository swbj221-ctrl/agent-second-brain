-- +migrate Up
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    content_type TEXT NOT NULL,
    content_path TEXT,
    content_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id INTEGER NOT NULL,
    summary_text TEXT NOT NULL,
    summary_format TEXT NOT NULL,
    model_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    body TEXT NOT NULL,
    source_type TEXT,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    schedule_spec TEXT NOT NULL,
    status TEXT NOT NULL,
    last_run_at TEXT,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_feature_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- +migrate Down
DROP TABLE IF EXISTS app_feature_flags;
DROP TABLE IF EXISTS app_settings;
DROP TABLE IF EXISTS jobs;
DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS artifact_summaries;
DROP TABLE IF EXISTS artifacts;
DROP TABLE IF EXISTS schema_migrations;
