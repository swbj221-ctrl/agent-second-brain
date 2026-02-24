# OpenClaw Bot (Agent Second Brain)

## Project Overview
OpenClaw-based personal assistant with one main skill and a sidecar backend for storage, schedulers, and integrations.

## Current Status
- Stage 17 (web dashboard MVP) is postponed.

## Architecture Principles
- One main skill + one sidecar backend.
- Anti-context-bloat by default.
- Adapter/config-first over hardcoding.
- Local LLM for utility-only tasks; Codex for reasoning and synthesis.

## Windows/MSI Quickstart
1. Create a Python 3.12 venv: `py -3.12 -m venv .venv`
2. Activate: `.\.venv\Scripts\Activate.ps1`
3. Install deps: `python -m pip install -r requirements.txt`
4. Configure: `Copy-Item .env.example .env` and set `TELEGRAM_BOT_TOKEN`, `ALLOWED_USER_IDS`
5. Apply migrations: `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
6. Run: `$env:PYTHONPATH="src"; python -m d_brain`

## Common Commands
- Migrations: `$env:PYTHONPATH="src"; python scripts/migrate.py apply`
- Stage 6 news smoke: `$env:PYTHONPATH="src"; python scripts/news_mvp_smoke.py`
- Stage 6 briefing smoke: `$env:PYTHONPATH="src"; python scripts/news_briefing_smoke.py`
- Backup job: `$env:PYTHONPATH="src"; python scripts/db_backup_job.py --run`

## Docs Map
- Runbook: `docs/runbook.md`
- Backlog: `docs/backlog.md`
- Progress: `docs/progress.md`
- Integration: `docs/openclaw-integration.md`
- DB schema: `docs/db-schema.md`

## Agent Docs Map
- `docs/agent/README.md`
- `docs/agent/USER.md`
- `docs/agent/IDENTITY.md`
- `docs/agent/TOOLS.md`
- `docs/agent/SOUL.md`

## Working Conventions
- English-only documentation.
- Update docs during work, not only at the end.
- Explicit verification status in outputs (code-complete vs MSI-validated vs docs-aligned).
