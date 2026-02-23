-- +migrate Up
CREATE TABLE IF NOT EXISTS health_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT,
    title TEXT NOT NULL,
    notes TEXT,
    occurred_at TEXT,
    source_type TEXT,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dosage TEXT,
    schedule TEXT,
    started_at TEXT,
    ended_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_treatments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    started_at TEXT,
    ended_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_type TEXT NOT NULL,
    value TEXT,
    unit TEXT,
    observed_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_lab_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artifact_id INTEGER NOT NULL,
    title TEXT,
    report_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_health_records_created_at
    ON health_records(created_at);
CREATE INDEX IF NOT EXISTS idx_health_medications_created_at
    ON health_medications(created_at);
CREATE INDEX IF NOT EXISTS idx_health_treatments_created_at
    ON health_treatments(created_at);
CREATE INDEX IF NOT EXISTS idx_health_observations_created_at
    ON health_observations(created_at);
CREATE INDEX IF NOT EXISTS idx_health_lab_reports_created_at
    ON health_lab_reports(created_at);
CREATE INDEX IF NOT EXISTS idx_health_lab_reports_artifact_id
    ON health_lab_reports(artifact_id);

-- +migrate Down
DROP INDEX IF EXISTS idx_health_lab_reports_artifact_id;
DROP INDEX IF EXISTS idx_health_lab_reports_created_at;
DROP INDEX IF EXISTS idx_health_observations_created_at;
DROP INDEX IF EXISTS idx_health_treatments_created_at;
DROP INDEX IF EXISTS idx_health_medications_created_at;
DROP INDEX IF EXISTS idx_health_records_created_at;

DROP TABLE IF EXISTS health_lab_reports;
DROP TABLE IF EXISTS health_observations;
DROP TABLE IF EXISTS health_treatments;
DROP TABLE IF EXISTS health_medications;
DROP TABLE IF EXISTS health_records;
