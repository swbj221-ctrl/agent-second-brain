-- +migrate Up
CREATE TABLE IF NOT EXISTS news_item_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_item_id INTEGER NOT NULL UNIQUE,
    summary_text TEXT NOT NULL,
    summary_format TEXT NOT NULL,
    model_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (news_item_id) REFERENCES news_items(id)
);

CREATE TABLE IF NOT EXISTS news_briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    briefing_mode TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_briefing_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    briefing_id INTEGER NOT NULL,
    news_item_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    title TEXT,
    url TEXT,
    published_at TEXT,
    summary_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (briefing_id) REFERENCES news_briefings(id),
    FOREIGN KEY (news_item_id) REFERENCES news_items(id),
    FOREIGN KEY (source_id) REFERENCES news_sources(id),
    UNIQUE (briefing_id, news_item_id)
);

CREATE INDEX IF NOT EXISTS idx_news_item_summaries_item_id
    ON news_item_summaries(news_item_id);

CREATE INDEX IF NOT EXISTS idx_news_briefing_items_briefing_id
    ON news_briefing_items(briefing_id);

-- +migrate Down
DROP INDEX IF EXISTS idx_news_briefing_items_briefing_id;
DROP INDEX IF EXISTS idx_news_item_summaries_item_id;
DROP TABLE IF EXISTS news_briefing_items;
DROP TABLE IF EXISTS news_briefings;
DROP TABLE IF EXISTS news_item_summaries;
