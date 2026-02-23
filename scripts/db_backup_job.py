"""Run database backup via scheduler or direct helper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from d_brain.config import get_settings
from d_brain.services.db_backup import run_backup
from d_brain.sidecar.scheduler import Scheduler, build_default_registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Run database backup")
    parser.add_argument(
        "--job",
        default="db_backup_weekly",
        help="Scheduler job name to run (default: db_backup_weekly).",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run backup directly (bypass scheduler registry).",
    )
    args = parser.parse_args()

    if args.run:
        settings = get_settings()
        result = run_backup(settings, project_root=Path(__file__).parent.parent)
        print(f"backup_path={result.backup_path}")
        if result.snapshot_path:
            print(f"snapshot_path={result.snapshot_path}")
        if result.integrity_check:
            print(f"integrity_check={result.integrity_check}")
        if result.rotated:
            print(f"rotated={len(result.rotated)}")
        return 0

    scheduler = Scheduler(build_default_registry())
    scheduler.run_once(args.job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
