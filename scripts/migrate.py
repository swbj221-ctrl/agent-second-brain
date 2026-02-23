#!/usr/bin/env python3
"""SQLite migration runner with simple up/down support."""

from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

UP_MARKER = "-- +migrate Up"
DOWN_MARKER = "-- +migrate Down"


@dataclass
class MigrationPaths:
    db_path: Path
    migrations_path: Path


def load_settings_paths() -> MigrationPaths | None:
    try:
        from d_brain.config import get_settings

        settings = get_settings()
        return MigrationPaths(
            db_path=Path(settings.db_path),
            migrations_path=Path(settings.migrations_path),
        )
    except Exception:
        return None


def resolve_paths(args: argparse.Namespace) -> MigrationPaths:
    settings_paths = load_settings_paths()
    db_path = (
        Path(args.db_path)
        if args.db_path
        else Path(os.getenv("DB_PATH", ""))
        if os.getenv("DB_PATH")
        else settings_paths.db_path
        if settings_paths
        else Path("./data/app.db")
    )
    migrations_path = (
        Path(args.migrations_path)
        if args.migrations_path
        else Path(os.getenv("MIGRATIONS_PATH", ""))
        if os.getenv("MIGRATIONS_PATH")
        else settings_paths.migrations_path
        if settings_paths
        else Path("./deploy/migrations")
    )
    return MigrationPaths(db_path=db_path, migrations_path=migrations_path)


def ensure_db_dir(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def list_migration_files(migrations_path: Path) -> list[Path]:
    if not migrations_path.exists():
        return []
    return sorted(p for p in migrations_path.iterdir() if p.suffix == ".sql")


def parse_migration(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    up_index = text.find(UP_MARKER)
    down_index = text.find(DOWN_MARKER)
    if up_index == -1 or down_index == -1 or down_index <= up_index:
        raise ValueError(
            f"Migration {path.name} must include '{UP_MARKER}' and '{DOWN_MARKER}'."
        )
    up_sql = text[up_index + len(UP_MARKER) : down_index].strip()
    down_sql = text[down_index + len(DOWN_MARKER) :].strip()
    if not up_sql:
        raise ValueError(f"Migration {path.name} has empty Up section.")
    if not down_sql:
        raise ValueError(f"Migration {path.name} has empty Down section.")
    return up_sql, down_sql


def applied_migrations(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT filename FROM schema_migrations ORDER BY id ASC;"
    ).fetchall()
    return [row[0] for row in rows]


def apply_migrations(paths: MigrationPaths) -> None:
    ensure_db_dir(paths.db_path)
    with connect_db(paths.db_path) as conn:
        ensure_schema_migrations(conn)
        applied = set(applied_migrations(conn))
        for path in list_migration_files(paths.migrations_path):
            if path.name in applied:
                continue
            up_sql, _ = parse_migration(path)
            conn.executescript(up_sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename, applied_at) VALUES (?, ?);",
                (path.name, datetime.utcnow().isoformat(timespec="seconds")),
            )
            conn.commit()
            print(f"Applied {path.name}")


def rollback_last(paths: MigrationPaths) -> None:
    ensure_db_dir(paths.db_path)
    with connect_db(paths.db_path) as conn:
        ensure_schema_migrations(conn)
        row = conn.execute(
            "SELECT id, filename FROM schema_migrations ORDER BY id DESC LIMIT 1;"
        ).fetchone()
        if not row:
            print("No migrations to rollback.")
            return
        _, filename = row
        migration_path = paths.migrations_path / filename
        if not migration_path.exists():
            raise FileNotFoundError(f"Missing migration file: {migration_path}")
        _, down_sql = parse_migration(migration_path)
        conn.executescript(down_sql)
        conn.execute("DELETE FROM schema_migrations WHERE filename = ?;", (filename,))
        conn.commit()
        print(f"Rolled back {filename}")


def show_status(paths: MigrationPaths) -> None:
    ensure_db_dir(paths.db_path)
    with connect_db(paths.db_path) as conn:
        ensure_schema_migrations(conn)
        applied = set(applied_migrations(conn))
        files = list_migration_files(paths.migrations_path)
        if not files:
            print("No migration files found.")
            return
        for path in files:
            status = "applied" if path.name in applied else "pending"
            print(f"{path.name}: {status}")


def create_migration(paths: MigrationPaths, name: str) -> None:
    paths.migrations_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
    safe_name = name.strip().replace(" ", "_")
    filename = f"{timestamp}_{safe_name}.sql"
    path = paths.migrations_path / filename
    template = f"{UP_MARKER}\n\n{DOWN_MARKER}\n"
    path.write_text(template, encoding="utf-8")
    print(f"Created {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite migration runner")
    parser.add_argument("--db-path", default="", help="Path to SQLite DB file")
    parser.add_argument(
        "--migrations-path", default="", help="Path to migrations folder"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("apply", help="Apply all pending migrations")
    sub.add_parser("rollback", help="Rollback the last applied migration")
    sub.add_parser("status", help="Show migration status")

    create_parser = sub.add_parser("create", help="Create a new migration file")
    create_parser.add_argument("name", help="Short migration name")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    paths = resolve_paths(args)

    if args.command == "apply":
        apply_migrations(paths)
    elif args.command == "rollback":
        rollback_last(paths)
    elif args.command == "status":
        show_status(paths)
    elif args.command == "create":
        create_migration(paths, args.name)


if __name__ == "__main__":
    main()
