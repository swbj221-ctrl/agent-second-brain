"""SQLite backup and project snapshot helpers (standard library only)."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from d_brain.config import Settings

logger = logging.getLogger(__name__)

BACKUP_TS_FORMAT = "%Y%m%d_%H%M%SZ"
BACKUP_NAME_RE = re.compile(r"^(?P<prefix>.+)_(?P<ts>\d{8}_\d{6}Z)\.sqlite$")
SNAPSHOT_SUFFIX = "_snapshot.zip"
DEFAULT_EXCLUDES = {".git", "venv", ".venv", "__pycache__", ".pytest_cache"}


@dataclass(frozen=True)
class BackupResult:
    """Result from a backup run."""

    backup_path: Path
    snapshot_path: Path | None
    rotated: list[Path]
    integrity_check: str | None


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(BACKUP_TS_FORMAT)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _parse_backup_timestamp(filename: str, prefix: str) -> datetime | None:
    match = BACKUP_NAME_RE.match(filename)
    if not match or match.group("prefix") != prefix:
        return None
    try:
        return datetime.strptime(match.group("ts"), BACKUP_TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _rotate_backups(backup_dir: Path, prefix: str, retention: int) -> list[Path]:
    if retention < 1:
        return []

    candidates: list[tuple[datetime, Path]] = []
    for entry in backup_dir.iterdir():
        if not entry.is_file():
            continue
        ts = _parse_backup_timestamp(entry.name, prefix)
        if ts is None:
            continue
        candidates.append((ts, entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    keep = candidates[:retention]
    remove = candidates[retention:]
    removed_paths: list[Path] = []
    removed_backups: list[Path] = []

    for _, path in remove:
        try:
            path.unlink()
            removed_paths.append(path)
            removed_backups.append(path)
        except OSError as exc:
            logger.warning("Failed to remove old backup %s: %s", path, exc)

    for backup_path in removed_backups:
        snapshot_path = backup_path.with_name(backup_path.stem + SNAPSHOT_SUFFIX)
        if snapshot_path.exists():
            try:
                snapshot_path.unlink()
                removed_paths.append(snapshot_path)
            except OSError as exc:
                logger.warning("Failed to remove old snapshot %s: %s", snapshot_path, exc)

    return removed_paths


def _iter_snapshot_files(root: Path, excludes: set[str]) -> list[Path]:
    files: list[Path] = []
    for current_root, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in excludes]
        for name in filenames:
            if name in excludes:
                continue
            if name.endswith(".pyc"):
                continue
            files.append(Path(current_root) / name)
    return files


def _create_snapshot_zip(
    project_root: Path,
    backup_dir: Path,
    prefix: str,
    timestamp: str,
    paths: list[str],
) -> Path | None:
    if not paths:
        return None

    snapshot_path = backup_dir / f"{prefix}_{timestamp}{SNAPSHOT_SUFFIX}"
    excludes = set(DEFAULT_EXCLUDES)

    with ZipFile(snapshot_path, "w", compression=ZIP_DEFLATED) as archive:
        for rel_path in paths:
            target = (project_root / rel_path).resolve()
            if not target.exists():
                continue
            if target.is_file():
                archive.write(target, arcname=Path(rel_path))
                continue
            for file_path in _iter_snapshot_files(target, excludes):
                arcname = file_path.relative_to(project_root)
                archive.write(file_path, arcname=arcname)

    return snapshot_path


def _integrity_check(path: Path) -> str | None:
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
        if row:
            return str(row[0])
    except sqlite3.Error as exc:
        logger.warning("Integrity check failed for %s: %s", path, exc)
    return None


def run_backup(settings: Settings, project_root: Path | None = None) -> BackupResult:
    """Create a SQLite backup and optional project snapshot, then rotate old backups."""
    backup_dir = settings.backup_dir
    _ensure_dir(backup_dir)
    timestamp = _utc_timestamp()
    backup_path = backup_dir / f"{settings.backup_prefix}_{timestamp}.sqlite"

    db_path = settings.db_path
    logger.info("Starting backup for %s", db_path)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as dest:
        source.backup(dest)
    integrity = _integrity_check(backup_path)

    snapshot_path = None
    if settings.backup_snapshot_enabled:
        root = project_root or Path.cwd()
        snapshot_path = _create_snapshot_zip(
            root, backup_dir, settings.backup_prefix, timestamp, settings.backup_snapshot_paths
        )

    rotated = _rotate_backups(backup_dir, settings.backup_prefix, settings.backup_retention)
    return BackupResult(
        backup_path=backup_path,
        snapshot_path=snapshot_path,
        rotated=rotated,
        integrity_check=integrity,
    )
