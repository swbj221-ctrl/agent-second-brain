-- +migrate Up
CREATE TABLE IF NOT EXISTS english_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS english_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS english_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER,
    status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    summary_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (topic_id) REFERENCES english_topics(id)
);

CREATE TABLE IF NOT EXISTS english_session_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES english_sessions(id)
);

CREATE TABLE IF NOT EXISTS english_session_word_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    word_id INTEGER NOT NULL,
    usage_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, word_id),
    FOREIGN KEY (session_id) REFERENCES english_sessions(id),
    FOREIGN KEY (word_id) REFERENCES english_words(id)
);

-- +migrate Down
DROP TABLE IF EXISTS english_session_word_usage;
DROP TABLE IF EXISTS english_session_turns;
DROP TABLE IF EXISTS english_sessions;
DROP TABLE IF EXISTS english_topics;
DROP TABLE IF EXISTS english_words;
