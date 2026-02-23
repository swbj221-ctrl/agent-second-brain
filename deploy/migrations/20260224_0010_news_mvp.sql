-- +migrate Up
CREATE TABLE IF NOT EXISTS news_sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_ref TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (section_id) REFERENCES news_sections(id),
    UNIQUE (section_id, name)
);

CREATE TABLE IF NOT EXISTS news_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    external_id TEXT,
    title TEXT,
    url TEXT,
    published_at TEXT,
    content_text TEXT,
    content_hash TEXT NOT NULL,
    raw_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (section_id) REFERENCES news_sections(id),
    FOREIGN KEY (source_id) REFERENCES news_sources(id),
    UNIQUE (source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_news_items_source_published
    ON news_items(source_id, published_at);

CREATE INDEX IF NOT EXISTS idx_news_items_section_published
    ON news_items(section_id, published_at);

-- +migrate Down
DROP INDEX IF EXISTS idx_news_items_section_published;
DROP INDEX IF EXISTS idx_news_items_source_published;
DROP TABLE IF EXISTS news_items;
DROP TABLE IF EXISTS news_sources;
DROP TABLE IF EXISTS news_sections;
