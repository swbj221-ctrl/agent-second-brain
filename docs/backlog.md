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
Status
- Completed (first pass: usage logs, limits settings, advisory status, smoke test; validated on MSI).

### Stage 9: Health MVP (P3)
Goals
- Health tracking basics.

Tasks
- Add health entities and ingestion.
- Provide daily health summary.

Acceptance Criteria
- Health summary generated from structured inputs.
Status
- Completed (first pass implemented and validated on MSI).

### Stage 10: Idea Research / Product Factory (P3)
Goals
- Research pipelines for ideas and product concepts.

Tasks
- Add research jobs and evidence collection.
- Store structured research outputs.

Acceptance Criteria
- Research outputs stored with sources and summaries.
Status
- Completed (manual pipeline skeleton + smoke test validated on MSI).

### Stage 11: Telegram UX Wiring MVP (P3)
Goals
- Text-only Telegram wiring for core sidecar actions.
- Thin adapter layer with no duplicated business logic.

Tasks
- Wire Telegram commands to existing sidecar actions.
- Add minimal command parsing and clear error responses.
- Document manual verification checklist in the runbook.

Acceptance Criteria
- Telegram layer can call existing sidecar actions for core MVP flows.
- Errors are surfaced clearly without crashing the bot loop.
- Minimal command mapping documented and verified manually.

### Stage 12: Voice English Tutor MVP (First Pass, Narrow Scope) (P1)
Goals
- Implement a message-based voice English tutor loop in Telegram that reuses existing English session storage and sidecar architecture.

Scope (first pass only)
- Telegram voice message intake path (message-based, not real-time call).
- STT adapter interface (provider-agnostic).
- TTS adapter interface (provider-agnostic).
- English tutor flow wiring to existing English session actions/tables.
- Basic assistant reply generation path (Codex/adapter boundary or placeholder integration if direct call is not wired yet).
- Text fallback path for the same tutor flow.

Behavior Requirements
- Voice in -> transcript -> append user turn -> generate assistant reply -> append assistant turn -> TTS out (or mocked TTS response path).
- Conversational practice style (not correcting every sentence).
- Assistant continues conversation and asks questions.
- Optional session metadata for target duration (10-20 min) if provided.
- No pronunciation scoring.
- No aggressive grammar correction engine.
- No spaced repetition logic.
- No real-time streaming/call mode yet.

Constraints
- Reuse existing English MVP tables/actions where possible.
- Keep Telegram layer thin.
- Use adapter pattern for STT/TTS (swap providers later).
- Local LLM remains utility-only.
- Codex handles dialog/reasoning reply generation.
- Graceful errors if STT/TTS credentials/provider are missing.
- Documentation remains English-only.
- Update docs during implementation.

Acceptance Criteria
- Telegram voice message flow creates/uses an English session, appends user and assistant turns, and returns TTS output (or mocked TTS) for the assistant reply.
- Text fallback uses the same tutor flow and session storage.
- STT/TTS adapters are provider-agnostic and return structured errors on missing config.
- Minimal manual verification checklist is documented.

### Stage 13: Reflection Voice Loop MVP (First Pass, Narrow Scope) (P1)
Goals
- Add a message-based reflection voice loop in Telegram that reuses Stage 12 voice plumbing and existing reflection storage.

Scope (first pass only)
- Telegram voice message intake path (message-based, not real-time call).
- Reuse STT adapter and TTS adapter interfaces.
- Reflection session wiring to existing `reflection_sessions` / `reflection_turns`.
- Assistant reply generation path via existing integration boundary (Codex/adapter or placeholder).
- Text fallback path for the same reflection flow.

Behavior Requirements
- Voice in -> transcript -> append user reflection turn -> generate assistant reply -> append assistant turn -> TTS out (or text fallback).
- Reflection style is objective, calm, and structured (no flattery or always-agreeing).
- No diagnosis/therapy claims.
- No crisis workflow automation.
- No advanced memory retrieval across reflections.
- No real-time streaming/call mode yet.

Constraints
- Reuse existing Reflection MVP tables/actions where possible.
- Keep Telegram layer thin.
- Reuse Stage 12 STT/TTS adapters and patterns.
- Local LLM remains utility-only.
- Codex handles reflective reply generation.
- Graceful errors if STT/TTS provider or credentials are missing.
- Documentation remains English-only.
- Update docs during implementation.

Acceptance Criteria
- Telegram can accept a voice message for Reflection MVP and route it through STT -> reflection session -> reply.
- Assistant reply is persisted in `reflection_turns`.
- TTS adapter interface is reused and text fallback works cleanly when unavailable.
- Missing provider/credential errors are handled gracefully.
- Manual verification checklist is documented in the runbook.

### Stage 14: Books / Philosophy / Knowledge UX MVP (First Pass, Narrow Scope) (P1)
Goals
- Provide text-only UX for books, philosophy notes, and a knowledge inbox.
- Reuse existing ingestion + summary pipeline and durable notes storage.
- Keep categorization minimal via a lightweight link table.

Tasks
- Add minimal `note_categories` link table for tags (`books`, `philosophy`, `knowledge`).
- Add sidecar actions for books/philosophy add/list and knowledge inbox add/list/summarize/save.
- Wire Telegram commands for the new actions with clear responses and IDs.
- Update runbook checklist and integration docs.

Acceptance Criteria
- Books, Philosophy, and Knowledge inbox are usable via Telegram text commands.
- Existing ingestion/summary pipeline is reused where appropriate.
- No heavy parallel knowledge schema is introduced.
- Manual verification checklist passes on MSI.
Status
- Implemented first pass; manual Telegram verification on MSI pending.

### Stage 15: News Automation + Morning Briefing Delivery MVP (First Pass, Narrow Scope) (P1)
Goals
- Add scheduler-triggerable generation and Telegram delivery for the existing news briefing pipeline.
- Keep delivery traceable with minimal persistence.

Scope (first pass only)
- Scheduler jobs: generate daily briefing + deliver latest briefing to Telegram.
- Manual trigger path via Telegram commands for generate and deliver.
- Global morning schedule only (no per-user timezones).
- Delivery traceability via `heartbeat_logs`.

Constraints
- Reuse existing news ingestion, summarization, and briefing storage.
- Do not rebuild selection or summarization logic.
- No personalization or section UI changes.
- No dashboard work.
- Documentation remains English-only.

Acceptance Criteria
- Scheduler-compatible path exists to generate and deliver a morning briefing.
- Telegram delivery sends latest briefing with 5 items and source links.
- Delivery attempts are traceable via `heartbeat_logs`.
- Existing news pipeline is reused without duplicated logic.
- Runbook and integration docs updated during implementation.
Status
- Implemented first pass; manual Telegram verification on MSI pending.

### Stage 16: Reminders Delivery + Calendar-style Telegram Views MVP (First Pass, Narrow Scope) (P1)
Goals
- Add scheduler-triggerable reminder delivery to Telegram using existing plans/reminders data.
- Provide text-only calendar-style views for reminders (today, upcoming, date).

Scope (first pass only)
- Reuse existing `events` / `event_reminders` tables and reminder trigger logic.
- Scheduler job for reminder delivery to Telegram.
- Manual trigger command for reminder delivery testing.
- Text-only calendar views: `today`, `upcoming [N]`, `date YYYY-MM-DD`.
- Delivery traceability via `heartbeat_logs` (no new tables).

Constraints
- No per-user timezone scheduling (single global UTC).
- No Google Calendar integration.
- No recurring rules beyond current reminders.
- No dashboard UI.
- No voice flows.
- Documentation remains English-only.

Acceptance Criteria
- Scheduler-compatible reminder delivery job exists and can deliver due reminders to Telegram.
- Telegram text commands show calendar-style views (today/upcoming/date).
- Delivery attempts are traceable in `heartbeat_logs` with reminder/event IDs.
- Existing plans/reminders storage and logic are reused (no duplicated business logic).
- Runbook and integration docs updated during implementation.
Status
- Implemented first pass; manual Telegram verification on MSI pending.

### Stage 17: Web Dashboard MVP (Postponed)
Status
- Postponed. Do not prioritize until Stage 16 is manually verified.
