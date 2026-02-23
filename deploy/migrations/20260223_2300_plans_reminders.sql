-- +migrate Up
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT,
    start_at TEXT,
    end_at TEXT,
    status TEXT NOT NULL,
    source_type TEXT,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    remind_at TEXT NOT NULL,
    status TEXT NOT NULL,
    triggered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS event_parse_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT,
    source_ref TEXT,
    input_excerpt TEXT,
    input_hash TEXT,
    input_length INTEGER,
    parse_status TEXT NOT NULL,
    error_message TEXT,
    event_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (event_id) REFERENCES events(id)
);

-- +migrate Down
DROP TABLE IF EXISTS event_parse_logs;
DROP TABLE IF EXISTS event_reminders;
DROP TABLE IF EXISTS events;
