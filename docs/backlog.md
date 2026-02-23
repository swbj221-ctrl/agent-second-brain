# Backlog

## Scope and Planning Rules
- Keep scope minimal and implement in stages.
- Favor reuse-tested solutions: OpenClaw core, marketplace skills, stable libraries.
- Avoid hardcoding; use configs/adapters/feature flags and explicit migrations.
- Keep memory design anti-context-bloat: structured retrieval first, summaries over raw transcripts, top-k context only.
- Local LLM is a utility layer; Codex handles reasoning/dialog/final synthesis.
- Voice UX is a priority: human-like output and low latency.
- Documentation is English-only.

## Architecture Baseline
- One main OpenClaw skill (domain workflows + UX routing).
- One sidecar backend (storage, workers, schedulers, collectors, utility services).
- OpenClaw provides runtime/gateway/channel foundation.
- Minimize deep core modifications; use adapters/configs.

## Priority Levels
- P0: Must-have for usable foundation
- P1: Core features for MVP
- P2: Important enhancements
- P3: Nice-to-have or post-MVP

## Stages

### Stage 1: Foundation (P0)
Goals
- Scaffold core repo structure and docs discipline.
- Establish base DB schema and migrations.
- Create scheduler skeleton and sidecar service shell.

Tasks
- Define main skill boundaries and sidecar API contract.
- Add base DB tables: `artifacts`, `artifact_summaries`, `notes`, `jobs`, `app_settings`, `app_feature_flags`.
- Implement migration workflow (create/apply/rollback).
- Set up scheduler stub and job registry.
- Add payload limits and validation to prevent context bloat.

Acceptance Criteria
- Main skill + sidecar can exchange a validated request/response.
- DB migrations run locally with versioned files.
- Scheduler can register and execute a no-op job.
- Docs updated during implementation.

### Stage 2: Ingestion + Summary Pipeline (P1)
Goals
- Ingest inputs and produce summaries (summary != raw save).
- Store structured summaries and metadata.

Tasks
- Build ingestion endpoints in sidecar.
- Add summary pipeline using local LLM utility tasks.
- Store summary records and link to source artifacts.

Acceptance Criteria
- Ingestion creates a summary record with metadata and source link.
- Raw transcripts are not stored as primary context.
Status
- Completed (validated by local smoke test on MSI).

### Stage 3: Plans and Reminders (P1)
Goals
- Basic planning and reminders powered by structured data.

Tasks
- Add plan/reminder entities and scheduling hooks.
- Implement create/update/delete operations.

Acceptance Criteria
- Reminders can be created, listed, and triggered.
Status
- Completed (validated by local smoke tests on MSI: default + parse mode).

### Stage 4: English MVP (P1)
Goals
- English-only UX with consistent templates.

Tasks
- Normalize system prompts and templates in English.
- Add language enforcement checks for docs/templates.

Acceptance Criteria
- All user-facing templates and docs remain English-only.
Status
- Completed (validated by local smoke test on MSI).

### Stage 5: Reflection MVP (P2)
Goals
- Session-based reflection dialogue storage and close-summary flow.

Tasks
- Add reflection session storage (sessions + turns).
- Implement minimal sidecar actions to create sessions, append turns, close sessions, and list sessions.
- Add local smoke test for Stage 5.

Acceptance Criteria
- Reflection sessions can be created, appended, closed, and listed via sidecar actions.
- Close-summary is stored for retrieval without context bloat.
Status
- Completed (validated by local smoke test on MSI).

### Stage 6: News MVP (P2)
Goals
- Custom sections and sources (including Telegram channels).
- Exactly 5 key events per run.
- Persist news items to DB.

Tasks
- Add source registry (RSS/Telegram/etc.).
- Implement selector to output exactly 5 key events.
- Store news items with source metadata.

Acceptance Criteria
- Each run outputs exactly 5 key events.
- News entries persisted with sources.
Status
- In progress (first pass completed; second pass pending: summaries + briefing pipeline + exactly 5 key events).

### Stage 7: My Digest + Heartbeat + Local Utility Layer (P2)
Goals
- Personal digest and system heartbeat.
- Utility layer hardened for extraction/tagging.

Tasks
- Implement digest aggregation.
- Add heartbeat job and status reporting.
- Expand utility tasks library.

Acceptance Criteria
- Digest and heartbeat jobs execute on schedule.
Status
- Completed (validated by local smoke test on MSI).

### Stage 8: Codex Limits Indicator + Economy Mode (P2)
Goals
- Visibility into token/latency usage.
- Economy mode to reduce cost/latency.

Tasks
- Add usage metrics and budget thresholds.
- Implement economy mode routing policies.

Acceptance Criteria
- System can switch to economy mode with measurable savings.

### Stage 9: Health MVP (P3)
Goals
- Health tracking basics.

Tasks
- Add health entities and ingestion.
- Provide daily health summary.

Acceptance Criteria
- Health summary generated from structured inputs.

### Stage 10: Idea Research / Product Factory (P3)
Goals
- Research pipelines for ideas and product concepts.

Tasks
- Add research jobs and evidence collection.
- Store structured research outputs.

Acceptance Criteria
- Research outputs stored with sources and summaries.

### Stage 11: Universal Lists (P3)
Goals
- Wishlist/watchlist and other universal lists.

Tasks
- Add list entities and CRUD.
- Add list retrieval and summarization.

Acceptance Criteria
- Lists can be created, updated, and summarized.
