"""Smoke checks for OpenClaw-first memory ingestion pipeline."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

from d_brain.memory.ingestion import ingest_job_result, ingest_message_event, ingest_record  # noqa: E402


def emit(case: str, ok: bool, result: dict[str, object]) -> None:
    print(json.dumps({"case": case, "ok": ok, "result": result}, ensure_ascii=True))


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory(prefix="memory-ingest-smoke-") as tmp:
        vault_dir = Path(tmp) / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        os.environ["VAULT_PATH"] = str(vault_dir)
        os.environ["TELEGRAM_BOT_TOKEN"] = "smoke-token"

        # case=text_message_basic
        text_result = ingest_message_event(
            {
                "source_type": "text",
                "user_id": "123",
                "channel": "openclaw",
                "source_ref": "smoke:text:1",
                "text": "hello memory ingestion",
                "language": "en",
                "tags": ["smoke", "text"],
                "importance": "normal",
                "needs_indexing": True,
            }
        )
        text_ok = bool(text_result.get("ok") and text_result.get("stored"))
        emit("text_message_basic", text_ok, text_result)
        if not text_ok:
            failures += 1

        # case=voice_transcript_basic
        voice_result = ingest_message_event(
            {
                "source_type": "voice",
                "user_id": "123",
                "channel": "openclaw",
                "source_ref": "smoke:voice:1",
                "text": "voice transcript text",
                "language": "en",
                "tags": ["smoke", "voice"],
                "importance": "normal",
                "needs_indexing": False,
            }
        )
        voice_ok = bool(voice_result.get("ok") and voice_result.get("stored"))
        emit("voice_transcript_basic", voice_ok, voice_result)
        if not voice_ok:
            failures += 1

        # case=job_digest_ingest
        job_result = ingest_job_result(
            {
                "ok": True,
                "job_type": "daily_digest",
                "executed": True,
                "channel": "openclaw",
                "source_ref": "smoke:job:1",
                "outbound_result": {"delivery_state": "sent"},
                "metrics": {"items_count": 4},
                "error": "",
            }
        )
        job_ok = bool(job_result.get("ok") and job_result.get("stored"))
        emit("job_digest_ingest", job_ok, job_result)
        if not job_ok:
            failures += 1

        # case=empty_content_skip
        empty_result = ingest_message_event(
            {
                "source_type": "text",
                "user_id": "123",
                "channel": "openclaw",
                "source_ref": "smoke:empty:1",
                "text": "   ",
            }
        )
        empty_ok = bool(
            empty_result.get("ok")
            and not empty_result.get("stored")
            and str(empty_result.get("skipped_reason") or "") == "empty_content"
        )
        emit("empty_content_skip", empty_ok, empty_result)
        if not empty_ok:
            failures += 1

        # case=indexer_unavailable_fallback
        def bad_indexer(payload: dict[str, object]) -> bool:
            _ = payload
            raise RuntimeError("smoke_indexer_down")

        indexer_result = ingest_record(
            {
                "source_type": "text",
                "user_id": "123",
                "channel": "openclaw",
                "source_ref": "smoke:indexer:1",
                "text": "index me later",
                "needs_indexing": True,
            },
            indexer=bad_indexer,
        )
        indexer_ok = bool(
            indexer_result.get("ok")
            and indexer_result.get("stored")
            and str(indexer_result.get("indexed") or "") == "deferred"
        )
        emit("indexer_unavailable_fallback", indexer_ok, indexer_result)
        if not indexer_ok:
            failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

