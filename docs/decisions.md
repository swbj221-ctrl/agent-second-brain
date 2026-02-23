# Decisions

## Decision Log
Format: `YYYY-MM-DD | Decision | Status | Rationale`

- 2026-02-23 | One primary skill + sidecar backend | Accepted | Keeps orchestration centralized while isolating integrations.
- 2026-02-23 | Local LLM as utility layer | Accepted | Fast, cheap utility tasks; keep reasoning in Codex.
- 2026-02-23 | Anti-context-bloat | Accepted | Reduce prompt drift and cost.
- 2026-02-23 | English-only project documentation | Accepted | Cyrillic rendering issues in current environment.
- 2026-02-23 | Reflection voice loop uses in-memory active session state | Accepted | Matches Stage 12 pattern and keeps Telegram layer thin.
- 2026-02-23 | SQLite backups via stdlib backup API + paired snapshot ZIP rotation | Accepted | Consistent DB snapshots without new deps; snapshots removed when matching DB backup is rotated out.
- 2026-02-23 | Stage 18 Projects & Tasks use dedicated tables (`projects`, `tasks`) | Accepted | Avoids overloading events/reminders and keeps task status/due date semantics explicit.

Documentation Language Contract:
All docs and generated documentation must be in English only (no Cyrillic).
This includes markdown files, comments in documentation templates, progress notes, context packs, runbooks, and architecture notes.
Reason: Cyrillic rendering is unreliable in the current environment.

## Pending
- Persistence store selection
- Interface contract between skill and sidecar
- Stage 16 manual Telegram verification on MSI

## Updates
- 2026-02-23 | Migration workflow using `scripts/migrate.py` + SQL files | Accepted | Simple, local SQLite-friendly baseline for Stage 1.
- 2026-02-23 | Stage 1 base schema tables | Accepted | Use `artifacts`, `artifact_summaries`, `notes`, `jobs`, `app_settings`, `app_feature_flags`.
- 2026-02-23 | Stage 12 uses provider-agnostic STT/TTS adapters with graceful fallback | Accepted | Keep Telegram thin while allowing provider swaps; missing providers return structured errors and fall back to text.
- 2026-02-24 | Stage 14 uses minimal `note_categories` link table | Accepted | Reuse `notes` and avoid a new knowledge schema while enabling categorization.
- 2026-02-23 | Lazy import for Telegram delivery dependencies | Accepted | Keep scheduler imports safe; delivery failures surface at runtime with traceability logs.
- 2026-02-23 | Reminder delivery traceability uses `heartbeat_logs` | Accepted | Avoid new tables; keep delivery attempts visible with minimal structured logging.
- 2026-02-24 | MSI install uses `requirements.txt` as canonical dependency manifest | Accepted | Simple, reliable pip path for Windows; `pyproject.toml` stays aligned for uv.

# Architectural Decisions

## Decision: Reuse-tested solutions first
We prefer tested implementations from OpenClaw core, marketplace skills, or stable libraries before writing custom code.
Custom code is allowed only when necessary to preserve business logic of project sections.

## Decision: One main skill + sidecar backend
The project uses:
- one main OpenClaw skill for domain workflows and Telegram interaction
- one sidecar backend for storage, workers, scheduling, collectors, and utility services

This reduces maintenance complexity and improves compatibility with OpenClaw updates.

## Decision: Anti-hardcode policy
Avoid hardcoding when a config/adaptor/extension pattern is possible.
Prefer:
- config files
- feature flags
- adapters
- explicit migrations
over hardcoded logic and dynamic schema mutation.

## Decision: Anti-context-bloat memory design
Do not send full vault history or long transcripts into LLM prompts.
Use:
1. structured retrieval first (SQL / indexed lookup)
2. summaries over raw transcripts
3. top-k relevant chunks only
4. feature-specific context builders

If OpenClaw memory/FTS is better suited for retrieval, prefer it as the retrieval layer.

## Decision: LLM routing layers
- Local LLM = utility layer (heartbeat, light search, simple classification, preprocessing)
- Codex = reasoning/dialog/final synthesis (English tutor, reflection, final briefing assembly, deep summaries)

## Decision: Voice stack should prioritize human-like output and low latency
Voice integrations must be adapter-based (STT/TTS adapters) and should prioritize:
- natural sounding output
- low latency
- provider swap flexibility

## Decision: Documentation language is English-only
Documentation Language Contract:
All docs and generated documentation must be in English only (no Cyrillic).
This includes markdown files, comments in documentation templates, progress notes, context packs, runbooks, and architecture notes.
Reason: Cyrillic rendering is unreliable in the current environment.
