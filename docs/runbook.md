# Runbook

## Session Workflow (Codex)
- Use `docs/commands/open-session.md` to start every session.
- Use `docs/commands/close-session.md` to end every session.
- Update docs during implementation, not only at the end.
- Documentation must be English-only (no Cyrillic).

## Local Development
TODO: steps to start local services, env vars, and health checks.

## Windows MSI Quickstart
1. Create a Python 3.12 virtual environment:
   `py -3.12 -m venv .venv`
2. Activate the environment:
   `.\.venv\Scripts\Activate.ps1`
3. Install dependencies (canonical manifest for MSI):
   `python -m pip install -r requirements.txt`
4. Configure environment:
   `Copy-Item .env.example .env`
   Set `TELEGRAM_BOT_TOKEN` and `ALLOWED_USER_IDS` in `.env`.
5. Run the bot:
   `$env:PYTHONPATH="src"; python -m d_brain`

Notes:
- STT requires `deepgram-sdk` and `DEEPGRAM_API_KEY`. If missing, STT falls back with a clear error.
- TTS defaults to `none` and will fall back to text replies.
- Deepgram TTS requires `DEEPGRAM_API_KEY` and `TTS_PROVIDER=deepgram`.
- For Telegram voice replies, use `TTS_DEEPGRAM_ENCODING=opus` and `TTS_DEEPGRAM_CONTAINER=ogg`.

## Dependencies
- Install (pip): `python -m pip install -r requirements.txt`
- Install (uv): `uv sync`

## Web/URL Skills (Tavily + Summarize)
Prereqs:
- Node.js (for `npx`)
- `TAVILY_API_KEY` set in `.env`
- Summarize config at `~/.summarize/config.json`
- Skills live under `vault/.claude/skills/` and are loaded by the OpenClaw runtime.
Notes:
- Windows fallback: if `npx` is not in PATH, the bot will attempt `C:\Program Files\nodejs\npx.cmd`.

Install (one-time):
- `npm i -g @steipete/summarize`

Smoke Tests (PowerShell):
1. Tavily MCP server (sanity):
   `npx -y tavily-mcp@latest --help`
2. URL summary:
   `summarize "https://example.com" --extract --plain`
3. YouTube transcript:
   `summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract --plain`
4. Windows fallback (no PATH `npx`):
   `& "C:\Program Files\nodejs\npx.cmd" -y @steipete/summarize "https://example.com" --extract --plain`

Telegram Manual Checks:
- `/web search latest ai coding tools`
- `/web summarize https://example.com`
- `/youtube transcript https://youtu.be/dQw4w9WgXcQ`

Expected behavior:
- `/youtube transcript` returns transcript text (possibly truncated) with a source suffix.
- If summarize is missing, it should return a safe error message and not crash.

Failure notes:
- Missing `TAVILY_API_KEY` should return an MCP error; the server should not crash.
- Missing summarize config will print an auth/provider error and exit non-zero.

## Migrations
- Create: `python scripts/migrate.py create <name>`
- Apply: `python scripts/migrate.py apply`
- Rollback: `python scripts/migrate.py rollback`
- Status: `python scripts/migrate.py status`

## Backup & Restore (SQLite)
### Backup (manual, Windows PowerShell)
1. Create a backup (direct helper):
   `$env:PYTHONPATH="src"; python scripts/db_backup_job.py --run`
2. Create a backup (scheduler job):
   `$env:PYTHONPATH="src"; python scripts/db_backup_job.py --job db_backup_weekly`

Output includes:
- `backup_path=...`
- `snapshot_path=...` (if enabled)
- `integrity_check=ok` (if check ran)

### Backup Configuration (env)
- `BACKUP_DIR` (default: `./data/backups`)
- `BACKUP_PREFIX` (default: `db_backup`)
- `BACKUP_RETENTION` (default: `6`)
- `BACKUP_SNAPSHOT_ENABLED` (default: `true`)
- `BACKUP_SNAPSHOT_PATHS` (default: `["docs"]`)

### Rotation Policy
- Rotation keeps the newest `BACKUP_RETENTION` DB backups.
- When a DB backup is rotated out, its paired snapshot ZIP (same timestamp) is removed as well.

### Restore Verification (manual, Windows PowerShell)
1. Stop the bot/sidecar process.
2. Copy the backup file to a restore target:
   `Copy-Item .\data\backups\db_backup_YYYYMMDD_HHMMSSZ.sqlite .\data\app_restored.db`
3. Run integrity check on the restored DB:
   `$env:PYTHONPATH="src"; python - <<'PY'\nimport sqlite3\nwith sqlite3.connect(\"data/app_restored.db\") as conn:\n    row = conn.execute(\"PRAGMA integrity_check;\").fetchone()\n    print(row[0])\nPY`
   Expected output: `ok`
4. Optional sanity query:
   `$env:PYTHONPATH="src"; python - <<'PY'\nimport sqlite3\nwith sqlite3.connect(\"data/app_restored.db\") as conn:\n    print(conn.execute(\"SELECT COUNT(*) FROM artifacts;\").fetchone()[0])\nPY`
5. If you want to restore in place:
   - Stop all processes using the DB.
   - Replace `data/app.db` with `data/app_restored.db`.

### Scheduling (Windows Task Scheduler)
- Program/script: `python`
- Arguments:
  `scripts/db_backup_job.py --run`
- Start in: `D:\openclaw_bot\agent-second-brain`

### Windows Task Scheduler Setup (Weekly Backups)
1. Open Task Scheduler.
2. Click `Create Task...` (not "Create Basic Task").
3. **General** tab:
   - Name: `OpenClaw Weekly SQLite Backup`
   - Description: `Weekly local SQLite backup via db_backup_job.py`
   - Security options: select `Run whether user is logged on or not`.
   - Check `Run with highest privileges`.
4. **Triggers** tab:
   - Click `New...`
   - Begin the task: `On a schedule`
   - Settings: `Weekly`
   - Select the desired day and time
   - Enabled: checked
5. **Actions** tab:
   - Click `New...`
   - Action: `Start a program`
   - Program/script: `D:\openclaw_bot\agent-second-brain\scripts\run_weekly_backup.bat`
   - Add arguments: (leave empty)
   - Start in: `D:\openclaw_bot\agent-second-brain`
6. **Conditions** tab:
   - Optional: uncheck `Start the task only if the computer is on AC power` (if you want it to run on battery).
7. **Settings** tab:
   - Check `Allow task to be run on demand`.
   - Check `If the task fails, restart every` and set `5 minutes` for `3` attempts.
   - Check `Stop the task if it runs longer than` and set `1 hour`.

### Task Scheduler Verification
1. Right-click the task -> `Run`.
2. Confirm a new backup appears in `data\backups`.
3. Check the log file:
   - `logs\backup_weekly.log`
4. If it fails, review:
   - `logs\backup_weekly.log`
   - Task History tab (enable `All Tasks History` if disabled)

## Troubleshooting (MSI)
- OpenClaw Dashboard shows "pairing required" or "Disconnected from gateway" behind a dev tunnel:
  - Gateway logs show "Proxy headers detected from untrusted address".
  - Fix: set `gateway.trustedProxies` to `["127.0.0.1", "::1"]` in `C:\Users\User\.openclaw\openclaw.json`.
  - Restart gateway after change: `openclaw gateway`.
- OpenClaw status shows "no bootstrap files":
  - Confirm workspace path in `C:\Users\User\.openclaw\openclaw.json` matches project workspace.
  - Ensure files exist and are lowercase: `bootstrap.md` and `heartbeat.md`.
  - Place them in the active workspace directory.
- `ModuleNotFoundError: aiogram` or other packages:
  - Ensure the venv is activated and run `python -m pip install -r requirements.txt`.
- `ModuleNotFoundError: deepgram`:
  - Install `deepgram-sdk` or set `STT_PROVIDER=none` to disable STT.
- `summarize` fetch fails with TLS error (`unable to get local issuer certificate`):
  - The MSI network likely uses TLS inspection. You must obtain the corporate root CA from IT and provide it to Node:
    - Place the root CA file at `C:\certs\corp-root.cer`.
    - Import and convert to PEM:
      - `Import-Certificate -FilePath "C:\certs\corp-root.cer" -CertStoreLocation Cert:\LocalMachine\Root | Out-Null`
      - `certutil -encode "C:\certs\corp-root.cer" "C:\certs\corp-root.pem"`
    - Set the Node trust path and retry:
      - `$env:NODE_EXTRA_CA_CERTS="C:\certs\corp-root.pem"`
      - `& "C:\Program Files\nodejs\npx.cmd" -y @steipete/summarize "https://example.com" --extract --plain`
    - If `corp-root.cer` does not exist, the above commands will fail. You must obtain the root CA file first.
- `summarize` CLI not found:
  - Ensure `summarize` is in PATH (Windows user installs typically place it in `%APPDATA%\\npm`).
  - Option A: add `%APPDATA%\\npm` to PATH.
  - Option B: copy `summarize.cmd` to `%LOCALAPPDATA%\\Microsoft\\WindowsApps` (already on PATH).
  - Ensure config exists at `%USERPROFILE%\\.summarize\\config.json`.
- PowerShell activation path mismatch:
  - If `.\venv\Scripts\Activate.ps1` fails, the canonical path is `.\.venv\Scripts\Activate.ps1`.
- `TELEGRAM_BOT_TOKEN is required`:
  - Set `TELEGRAM_BOT_TOKEN` in `.env` before starting the bot.
- `No ALLOWED_USER_IDS configured`:
  - Set `ALLOWED_USER_IDS=[123456789]` in `.env` or set `ALLOW_ALL_USERS=true` for local testing.
- `Temporary error. Please try again.` in Telegram:
  - Indicates a transient failure or internal error; check logs for details.
- Telegram delivery failures:
  - Delivery uses bounded retries for transient errors (timeouts, 5xx, 429). Verify network access and bot token.
- `ModuleNotFoundError: d_brain` or `PYTHONPATH` issues:
  - Run with `$env:PYTHONPATH="src"; python -m d_brain` from repo root.
- Task Scheduler job fails:
  - Confirm `Start in` is `D:\openclaw_bot\agent-second-brain`.
  - Confirm the venv path and `python` executable used by the task.
  - Check `logs\backup_weekly.log` and Task History.

## Hardening Phase B QA (MSI)
Checklist (run from repo root):
1. Validation error path (clean user-facing message):
   - In Telegram: `/inbox summarize abc`
   - Expect: "Invalid input. Use /help for examples."
2. Sidecar internal error path (structured error + safe message):
   - PowerShell:
     `$env:PYTHONPATH="src"; $env:DB_PATH="Z:\nonexistent\app.db"; python - <<'PY'\nfrom d_brain.sidecar.dispatcher import handle_request\nprint(handle_request({\"request_id\": \"qa-1\", \"user_id\": \"1\", \"action\": \"event_list\", \"payload\": {\"status\": \"planned\", \"limit\": 1, \"offset\": 0}}))\nPY`
   - Expect: `status=error` with `code=internal_error` and a safe message.
3. Telegram delivery retry/timeout with bogus token:
   - PowerShell:
     `$env:PYTHONPATH="src"; python - <<'PY'\nfrom d_brain.services.telegram_delivery import send_telegram_message\nprint(send_telegram_message(\"BAD_TOKEN\", 123456789, \"test\").__dict__)\nPY`
   - Expect: retry attempts in logs and a clean error result (no crash).
4. STT missing dependency (graceful failure):
   - Uninstall: `python -m pip uninstall -y deepgram-sdk`
   - Send a voice message in Telegram.
   - Expect: "STT is unavailable" or "deepgram-sdk is not installed." and no crash.
5. No raw exceptions to Telegram users:
   - Trigger any internal failure and confirm user sees "Temporary error. Please try again."
6. Log severity expectations:
   - Validation/user input errors should log at INFO/WARN without stack traces.
   - Internal failures should log ERROR with stack traces.

Troubleshooting note:
- If results differ, verify `.env` values (token, allowed users, STT provider), the active venv, and that you are running from `D:\openclaw_bot\agent-second-brain`.

## Verification
- Scheduler smoke test (no-op): run a short script or REPL and call
  `Scheduler(build_default_registry()).run_once("noop")`.
- Reminders trigger smoke test (no-op DB state):
  `Scheduler(build_default_registry()).run_once("reminder_tick")`.
 - OpenClaw Phase 2 (MSI manual):
   1. Start OpenClaw runtime with `vault/.claude/skills/openclaw-main` enabled.
   2. Telegram check: `/usage`.
   3. Telegram check: `/digest latest`.
   4. Telegram check: `/news latest`.
   5. Telegram check: `/word add hello`.
   6. Negative check: `/usage extra`.
   7. Negative check: `/word add`.
   8. Negative check: `/word add hello world`.
   9. Rollback: disable the OpenClaw adapter routing and verify standalone `python -m d_brain` still works.
 - OpenClaw Phase 3 Batch A (MSI manual):
   1. Start OpenClaw runtime with `vault/.claude/skills/openclaw-main` enabled.
   2. Telegram check: `/word list`.
   3. Telegram check: `/topic list`.
   4. Telegram check: `/health list`.
   5. Telegram check: `/calendar today`.
   6. Telegram check: `/calendar upcoming 5`.
   7. Telegram check: `/calendar date 2026-02-23`.
   8. Telegram check: `/project list`.
   9. Telegram check: `/task list`.
   10. Rollback: disable the OpenClaw adapter routing and verify standalone `python -m d_brain` still works.
 - OpenClaw Phase 3 Batch B (MSI manual, deferred until post-transfer):
   1. Telegram check: `/topic add Travel`.
   2. Telegram check: `/health add Headache`.
   3. Telegram check: `/project add Alpha`.
   4. Telegram check: `/task add <project_id> | First task`.
   5. Rollback: disable the OpenClaw adapter routing and verify standalone `python -m d_brain` still works.
 - OpenClaw Phase 3 Batch C (MSI manual, deferred until post-transfer):
   1. Telegram check: `/note test note from openclaw`.
   2. Telegram check: `/inbox add https://example.com`.
   3. Telegram check: `/inbox list`.
   4. Telegram check: `/inbox summarize <id>`.
   5. Telegram check: `/inbox save <id>`.
   6. Telegram check: `/news generate`.
   7. Telegram check: `/news deliver`.
   8. Rollback: disable the OpenClaw adapter routing and verify standalone `python -m d_brain` still works.
 - OpenClaw Phase 3 Batch D (MSI manual, deferred until post-transfer):
   1. Telegram check: `/tutor status`.
   2. Telegram check: `/tutor start 15`.
   3. Telegram check: `/tutor status`.
   4. Telegram check: `/tutor stop`.
   5. Telegram check: `/reflect start`.
   6. Telegram check: `/reflect close <session_id>`.
   7. Telegram check: `/reminder deliver`.
   8. Negative check: `/tutor start abc`.
   9. Negative check: `/reflect close`.
   10. Negative check: `/reflect close abc`.
   11. Rollback: disable the OpenClaw adapter routing and verify standalone `python -m d_brain` still works.
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
   Notes:
   - The script is repeat-safe. It prints `run_mode=fresh_insert` on first insert and `run_mode=repeat_dedupe` on subsequent runs.
   - Expected `items_delta=2` on a fresh run; `items_delta=0` on repeat runs.
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
- Stage 12/13 TTS smoke test (local):
   0. Run TTS smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/tts_smoke.py`
   1. Run TTS smoke (bash):
      `PYTHONPATH=src python scripts/tts_smoke.py`
   2. Empty output check (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/tts_empty_file_check.py`
   3. Media preference check (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/voice_media_preference_check.py`

## iPhone Voice Note Tips (Telegram)
- Telegram in-app voice messages are supported directly; no need to send `.ogg` as a document.
- Auto-transcripts may be inaccurate; the bot prioritizes real voice/audio media when available.
- Stage 18 Projects & Tasks smoke test (local):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Apply migrations (bash):
      `PYTHONPATH=src python scripts/migrate.py apply`
   2. Run Stage 18 smoke (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/projects_tasks_smoke.py`
   3. Run Stage 18 smoke (bash):
      `PYTHONPATH=src python scripts/projects_tasks_smoke.py`
   4. Expected output includes:
      `stage18_projects_tasks_smoke_ok`
- Stage 18 Projects & Tasks Telegram checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Start the bot (same as current run flow).
   2. Projects:
      `/project add Alpha`
      `/project list`
      `/project archive <project_id>`
      `/project list archived`
   3. Tasks:
      `/task add <project_id> | First task`
      `/task add <project_id> | Second task | due:2026-03-01`
      `/task list`
      `/task list <project_id> open`
      `/task done <task_id>`
      `/task reopen <task_id>`
      `/task cancel <task_id>`
      `/task note <task_id> Add a short note`
      `/task move <task_id> <project_id>`
   4. Expect:
      - Clean success responses with created IDs.
      - Lists reflect updated statuses.
      - Due date parsed only for strict `YYYY-MM-DD` format.
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
      `/news latest` (expect "No records found." if empty)
   6. Health:
      `/health add Headache`
      `/health list`
   7. Reflection:
      `/reflect start` (capture session id)
      `/reflect add <session_id> Feeling focused today`
      `/reflect close <session_id>`
   8. Digest:
      `/digest latest` (expect "No records found." if empty)
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

- Stage 13 Reflection Voice Loop MVP checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Start the bot (same as current run flow).
   2. Start reflection session:
      `/reflect start`
   3. Send a short text message and verify a reply is returned.
   4. Send a voice message and verify:
      - STT produces a transcript (or a clear STT error if not configured).
      - Both user and assistant turns are stored in `reflection_turns`.
      - If TTS is configured, a voice reply is returned; otherwise text fallback is returned.
   5. Close reflection session:
      `/reflect close <session_id> [summary]`

- Stage 14 Books / Philosophy / Knowledge UX MVP checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Start the bot (same as current run flow).
   2. Books:
      `/book add Deep Work by Cal Newport`
      `/book list`
   3. Philosophy:
      `/philosophy add https://example.com/stoicism`
      `/philosophy list`
   4. Knowledge inbox:
      `/inbox add https://example.com/interesting.pdf`
      `/inbox list`
   5. Summarize:
      `/inbox summarize <artifact_id>`
   6. Save:
      `/inbox save <artifact_id> [Optional title]`
   7. Verify persistence in SQLite:
      - `artifacts`, `artifact_summaries`, `notes`, `note_categories`

- Stage 15 News Automation + Morning Briefing Delivery MVP checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   0a. Dependency note:
      - Telegram delivery uses `httpx`. Install with `python -m pip install httpx` if missing.
   1. Generate a briefing (Telegram):
      `/news generate`
   2. Deliver latest briefing (Telegram):
      `/news deliver`
   3. Validate message formatting:
      - header shows "Morning Briefing"
      - exactly 5 items
      - each item includes a source link when available
   4. Scheduler job sanity (local):
      `PYTHONPATH=src python scripts/news_briefing_job.py --all`
   5. Verify delivery traceability:
      - Check `heartbeat_logs` for `event_type=news_delivery`

- Stage 16 Reminders Delivery + Calendar Views MVP checklist (manual):
   0. Apply migrations (PowerShell):
      `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
   1. Create a plan/reminder:
      `/plan add Test reminder`
   2. Force due reminder (update remind_at to now or past via DB or use rule-based input).
   3. Manual delivery trigger:
      `/reminder deliver`
   4. Verify Telegram receives reminder message.
   5. Calendar views:
      `/calendar today`
      `/calendar upcoming 5`
      `/calendar date 2026-02-23`
   6. Verify delivery traceability:
      - Check `heartbeat_logs` for `event_type=reminder_delivery` with `reminder_id` and `event_id`.

## Debugging
TODO: logs, tracing, and common failure modes.
