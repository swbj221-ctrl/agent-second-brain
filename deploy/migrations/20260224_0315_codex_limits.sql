-- +migrate Up
CREATE TABLE IF NOT EXISTS codex_usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key TEXT NOT NULL DEFAULT 'global',
    request_id TEXT,
    user_id TEXT,
    model_ref TEXT,
    context TEXT,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 1,
    metadata TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_codex_usage_logs_created_at
    ON codex_usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_codex_usage_logs_scope_key
    ON codex_usage_logs(scope_key);
CREATE INDEX IF NOT EXISTS idx_codex_usage_logs_request_id
    ON codex_usage_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_codex_usage_logs_user_id
    ON codex_usage_logs(user_id);

CREATE TABLE IF NOT EXISTS codex_limits_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key TEXT NOT NULL UNIQUE,
    window_hours INTEGER NOT NULL DEFAULT 24,
    max_tokens INTEGER NOT NULL DEFAULT 0,
    max_requests INTEGER NOT NULL DEFAULT 0,
    max_latency_ms INTEGER NOT NULL DEFAULT 0,
    warn_ratio REAL NOT NULL DEFAULT 0.70,
    critical_ratio REAL NOT NULL DEFAULT 0.90,
    updated_at TEXT NOT NULL
);

-- +migrate Down
DROP INDEX IF EXISTS idx_codex_usage_logs_user_id;
DROP INDEX IF EXISTS idx_codex_usage_logs_request_id;
DROP INDEX IF EXISTS idx_codex_usage_logs_scope_key;
DROP INDEX IF EXISTS idx_codex_usage_logs_created_at;

DROP TABLE IF EXISTS codex_limits_settings;
DROP TABLE IF EXISTS codex_usage_logs;
