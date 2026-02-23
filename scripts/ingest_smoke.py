#!/usr/bin/env python3
"""Smoke test for Stage 2 ingestion pipeline."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = REPO_ROOT / "src"
if SRC_PATH.exists() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from d_brain.config import get_settings
from d_brain.sidecar.dispatcher import handle_request


def main() -> None:
    settings = get_settings()
    request = {
        "request_id": "smoke-001",
        "user_id": "smoke-user",
        "action": "ingest",
        "payload": {
            "source_type": "manual",
            "content_type": "text",
            "summary_format": "plain",
            "external_id": "smoke-001",
            "content": "Quick smoke test note for Stage 2 ingestion.",
            "metadata": {"topic": "smoke-test"},
        },
    }

    response = handle_request(request, settings=settings)
    print(json.dumps(response, indent=2))

    with sqlite3.connect(settings.db_path) as conn:
        artifacts = conn.execute("SELECT COUNT(*) FROM artifacts;").fetchone()[0]
        summaries = conn.execute(
            "SELECT COUNT(*) FROM artifact_summaries;"
        ).fetchone()[0]
        print(f"artifacts_count={artifacts}")
        print(f"summaries_count={summaries}")


if __name__ == "__main__":
    main()
