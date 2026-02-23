-- +migrate Up
CREATE TABLE IF NOT EXISTS note_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(note_id, category),
    FOREIGN KEY (note_id) REFERENCES notes(id)
);

CREATE INDEX IF NOT EXISTS idx_note_categories_category ON note_categories(category);
CREATE INDEX IF NOT EXISTS idx_note_categories_note_id ON note_categories(note_id);

-- +migrate Down
DROP INDEX IF EXISTS idx_note_categories_note_id;
DROP INDEX IF EXISTS idx_note_categories_category;
DROP TABLE IF EXISTS note_categories;
