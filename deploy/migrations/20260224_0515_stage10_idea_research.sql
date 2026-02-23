-- +migrate Up
CREATE TABLE IF NOT EXISTS idea_research_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idea_research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    summary_text TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES idea_research_jobs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS idea_research_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    finding_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    evidence_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES idea_research_runs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS idea_research_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    report_text TEXT NOT NULL,
    report_format TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES idea_research_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_idea_research_jobs_created_at
    ON idea_research_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_idea_research_jobs_status
    ON idea_research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_idea_research_runs_created_at
    ON idea_research_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_idea_research_runs_status
    ON idea_research_runs(status);
CREATE INDEX IF NOT EXISTS idx_idea_research_runs_job_id
    ON idea_research_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_idea_research_findings_run_id
    ON idea_research_findings(run_id);
CREATE INDEX IF NOT EXISTS idx_idea_research_findings_created_at
    ON idea_research_findings(created_at);
CREATE INDEX IF NOT EXISTS idx_idea_research_reports_run_id
    ON idea_research_reports(run_id);

-- +migrate Down
DROP INDEX IF EXISTS idx_idea_research_reports_run_id;
DROP INDEX IF EXISTS idx_idea_research_findings_created_at;
DROP INDEX IF EXISTS idx_idea_research_findings_run_id;
DROP INDEX IF EXISTS idx_idea_research_runs_job_id;
DROP INDEX IF EXISTS idx_idea_research_runs_status;
DROP INDEX IF EXISTS idx_idea_research_runs_created_at;
DROP INDEX IF EXISTS idx_idea_research_jobs_status;
DROP INDEX IF EXISTS idx_idea_research_jobs_created_at;

DROP TABLE IF EXISTS idea_research_reports;
DROP TABLE IF EXISTS idea_research_findings;
DROP TABLE IF EXISTS idea_research_runs;
DROP TABLE IF EXISTS idea_research_jobs;
