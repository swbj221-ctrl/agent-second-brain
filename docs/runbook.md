# Runbook

## Session Workflow (Codex)
- Use `docs/commands/open-session.md` to start every session.
- Use `docs/commands/close-session.md` to end every session.
- Update docs during implementation, not only at the end.
- Documentation must be English-only (no Cyrillic).

## Local Development
TODO: steps to start local services, env vars, and health checks.

## Dependencies
- Install (pip): `python -m pip install -r requirements.txt`
- Install (uv): `uv sync`

## Migrations
- Create: `python scripts/migrate.py create <name>`
- Apply: `python scripts/migrate.py apply`
- Rollback: `python scripts/migrate.py rollback`
- Status: `python scripts/migrate.py status`

## Verification
- Scheduler smoke test (no-op): run a short script or REPL and call
  `Scheduler(build_default_registry()).run_once("noop")`.
- Reminders trigger smoke test (no-op DB state):
  `Scheduler(build_default_registry()).run_once("reminder_tick")`.
- Stage 3 plans/reminders smoke test (local):
  0. Apply migrations (PowerShell):
     `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
  1. Apply migrations (bash):
     `PYTHONPATH=src python scripts/migrate.py apply`
  2. Run Stage 3 smoke (PowerShell):
     `$env:PYTHONPATH="src"; python scripts/plan_reminder_smoke.py`
  3. Run Stage 3 smoke (bash):
     `PYTHONPATH=src python scripts/plan_reminder_smoke.py`
  3a. Run Stage 3 parse-only smoke (PowerShell):
     `$env:PYTHONPATH="src"; $env:STAGE3_SMOKE_MODE="parse"; python scripts/plan_reminder_smoke.py`
  3b. Run Stage 3 parse-only smoke (bash):
     `PYTHONPATH=src STAGE3_SMOKE_MODE=parse python scripts/plan_reminder_smoke.py`
  3c. Expected output (parse-only):
     `stage3_parse_smoke_ok`
     `parsed_title=Stage 3 parse smoke`
     `parsed_start_at=2026-02-23T23:00:00+00:00`
     `parsed_remind_at=2026-02-23T23:00:00+00:00`
     `parsed_event_id=1`
     `parsed_reminder_id=1`
     `parse_logs=1`
  4. Verify rows (PowerShell):
     `$env:PYTHONPATH="src"; python - <<'PY'\nimport sqlite3\nfrom d_brain.config import get_settings\ns = get_settings()\nwith sqlite3.connect(s.db_path) as c:\n    events = c.execute(\"SELECT COUNT(*) FROM events;\").fetchone()[0]\n    reminders = c.execute(\"SELECT COUNT(*) FROM event_reminders;\").fetchone()[0]\n    logs = c.execute(\"SELECT COUNT(*) FROM event_parse_logs;\").fetchone()[0]\n    print(f\"events={events}\")\n    print(f\"event_reminders={reminders}\")\n    print(f\"event_parse_logs={logs}\")\nPY`
  5. Verify rows (bash):
     `PYTHONPATH=src python - <<'PY'\nimport sqlite3\nfrom d_brain.config import get_settings\ns = get_settings()\nwith sqlite3.connect(s.db_path) as c:\n    events = c.execute(\"SELECT COUNT(*) FROM events;\").fetchone()[0]\n    reminders = c.execute(\"SELECT COUNT(*) FROM event_reminders;\").fetchone()[0]\n    logs = c.execute(\"SELECT COUNT(*) FROM event_parse_logs;\").fetchone()[0]\n    print(f\"events={events}\")\n    print(f\"event_reminders={reminders}\")\n    print(f\"event_parse_logs={logs}\")\nPY`
- Stage 2 ingestion smoke test (local):
  Note: `ModuleNotFoundError` happens with a `src/` layout when `d_brain` is not on
  `PYTHONPATH` or installed in the environment. Use the commands below or run
  the script which adds `src/` to `sys.path`.
  Minimal env vars for Stage 2 smoke tests:
  - `DB_PATH` (optional, defaults to `./data/app.db`)
  - `MIGRATIONS_PATH` (optional, defaults to `./deploy/migrations`)
  - `DEEPGRAM_API_KEY` is not required unless voice/STT features are used.
  0. Install dependencies:
     - `python -m pip install -r requirements.txt`
     - `uv sync`
  1. Apply migrations (PowerShell):
     `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
  2. Apply migrations (bash):
     `PYTHONPATH=src python scripts/migrate.py apply`
  3. Run ingest smoke (PowerShell):
     `$env:PYTHONPATH="src"; python scripts/ingest_smoke.py`
  4. Run ingest smoke (bash):
     `PYTHONPATH=src python scripts/ingest_smoke.py`
  5. Verify rows (PowerShell):
     `$env:PYTHONPATH="src"; python - <<'PY'\nimport sqlite3\nfrom d_brain.config import get_settings\ns = get_settings()\nwith sqlite3.connect(s.db_path) as c:\n    a = c.execute(\"SELECT COUNT(*) FROM artifacts;\").fetchone()[0]\n    b = c.execute(\"SELECT COUNT(*) FROM artifact_summaries;\").fetchone()[0]\n    print(f\"artifacts={a}\")\n    print(f\"artifact_summaries={b}\")\nPY`
  6. Verify rows (bash):
     `PYTHONPATH=src python - <<'PY'\nimport sqlite3\nfrom d_brain.config import get_settings\ns = get_settings()\nwith sqlite3.connect(s.db_path) as c:\n    a = c.execute(\"SELECT COUNT(*) FROM artifacts;\").fetchone()[0]\n    b = c.execute(\"SELECT COUNT(*) FROM artifact_summaries;\").fetchone()[0]\n    print(f\"artifacts={a}\")\n    print(f\"artifact_summaries={b}\")\nPY`
  7. Verify rows (alt, no PYTHONPATH):
     ```bash
     python - <<'PY'
     import sqlite3
     import sys
     from pathlib import Path
     root = Path(".").resolve()
     src = root / "src"
     if src.exists() and str(src) not in sys.path:
         sys.path.insert(0, str(src))
     from d_brain.config import get_settings
     s = get_settings()
     with sqlite3.connect(s.db_path) as c:
         a = c.execute("SELECT COUNT(*) FROM artifacts;").fetchone()[0]
         b = c.execute("SELECT COUNT(*) FROM artifact_summaries;").fetchone()[0]
         print(f"artifacts={a}")
         print(f"artifact_summaries={b}")
     PY
     ```
- Stage 4 English MVP smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 4 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/english_mvp_smoke.py`
   3. Run Stage 4 smoke (bash):
      `PYTHONPATH=src python scripts/english_mvp_smoke.py`
 - Stage 5 Reflection MVP smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 5 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/reflection_smoke.py`
   3. Run Stage 5 smoke (bash):
      `PYTHONPATH=src python scripts/reflection_smoke.py`
 - Stage 6 News MVP smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 6 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/news_mvp_smoke.py`
   3. Run Stage 6 smoke (bash):
      `PYTHONPATH=src python scripts/news_mvp_smoke.py`
 - Stage 6 News Briefing smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 6 briefing smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/news_briefing_smoke.py`
   3. Run Stage 6 briefing smoke (bash):
      `PYTHONPATH=src python scripts/news_briefing_smoke.py`
 - Stage 7 Digest + Heartbeat smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 7 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/digest_smoke.py`
   3. Run Stage 7 smoke (bash):
      `PYTHONPATH=src python scripts/digest_smoke.py`
 - Stage 8 Codex limits smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 8 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/codex_limits_smoke.py`
   3. Run Stage 8 smoke (bash):
      `PYTHONPATH=src python scripts/codex_limits_smoke.py`
 - Stage 9 Health MVP smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 9 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/health_mvp_smoke.py`
   3. Run Stage 9 smoke (bash):
      `PYTHONPATH=src python scripts/health_mvp_smoke.py`
- Stage 10 Idea Research smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 10 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/idea_research_smoke.py`
   3. Run Stage 10 smoke (bash):
      `PYTHONPATH=src python scripts/idea_research_smoke.py`
- Stage 11 Telegram UX wiring checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Start the bot (same as current run flow).
   2. Plans/reminders:
      `/plan add Test plan`
      `/plan list`
      `/reminder list`
   3. Notes/ingest:
      `/note This is a test note`
      `/note https://example.com`
   4. English:
      `/word add hello`
      `/word list`
      `/topic add Travel`
      `/topic list`
   5. News:
      `/news latest` (expect “No records found.” if empty)
   6. Health:
      `/health add Headache`
      `/health list`
   7. Reflection:
      `/reflect start` (capture session id)
      `/reflect add <session_id> Feeling focused today`
      `/reflect close <session_id>`
   8. Digest:
      `/digest latest` (expect “No records found.” if empty)
   9. Codex usage:
      `/usage`

- Stage 12 Voice English Tutor MVP checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Start the bot (same as current run flow).
   2. Start tutor session:
      `/tutor start 15`
   3. Send a short text message and verify a reply is returned.
   4. Send a voice message and verify:
      - STT produces a transcript (or a clear STT error if not configured).
      - Both user and assistant turns are stored in `english_session_turns`.
      - If TTS is configured, a voice reply is returned; otherwise text fallback is returned.
   5. Check tutor status:
      `/tutor status`
   6. Stop tutor session:
      `/tutor stop`

## Debugging
TODO: logs, tracing, and common failure modes.
