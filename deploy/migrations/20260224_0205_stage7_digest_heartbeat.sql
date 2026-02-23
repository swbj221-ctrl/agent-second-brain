-- +migrate Up
CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heartbeat_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    event_source TEXT,
    event_details TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_digests_created_at ON digests(created_at);
CREATE INDEX IF NOT EXISTS idx_heartbeat_logs_created_at ON heartbeat_logs(created_at);

-- +migrate Down
DROP INDEX IF EXISTS idx_heartbeat_logs_created_at;
DROP INDEX IF EXISTS idx_digests_created_at;

DROP TABLE IF EXISTS heartbeat_logs;
DROP TABLE IF EXISTS digests;
