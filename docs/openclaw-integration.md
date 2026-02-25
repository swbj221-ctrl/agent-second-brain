# OpenClaw Integration

## Strategy
- OpenClaw is the core runtime/gateway/channel foundation.
- Reuse-first: prefer stable OpenClaw components and marketplace skills.
- One main OpenClaw skill for domain workflows and Telegram UX.
- One sidecar backend for storage, workers, schedulers, collectors, and utility services.
- Local LLM is a utility layer; Codex handles reasoning/dialog/final synthesis.
- Anti-context-bloat: structured retrieval first, summaries over raw transcripts, top-k context.
- Production transport is OpenClaw-first only; aiogram polling is dev-only.

## Documentation Contract (Workflow Rule)
- Any code/logic/routing/behavior change implemented via Codex/OpenClaw must update docs in the same session.
- Must-update files:
  - `docs/progress.md`
  - `docs/runbook.md`
  - `docs/openclaw-integration.md`
  - `.openclaw/workspace/BOOTSTRAP.md` (workspace file currently `.openclaw/workspace/bootstrap.md`)
  - `.openclaw/workspace/HEARTBEAT.md` (workspace file currently `.openclaw/workspace/heartbeat.md`)
- Conditional updates (if impacted):
  - `docs/cutover-checklist.md`
  - `docs/release-notes-v1.0-draft.md`
  - skill docs under `vault/.claude/skills/...` or `docs/skills/...`
  - smoke checks in `scripts/*`

## Session Continuity (OpenClaw-first Workflow)
- Session close must record:
  - current status
  - next step
  - exact continuation command
- Session open must read:
  - workspace bootstrap + heartbeat
  - `docs/progress.md`
  - latest `docs/learnings.md` entries
- Purpose: preserve continuity across sessions while keeping context minimal and explicit.
- Keep the next exact operator command in workspace heartbeat for live cutover/sign-off continuation.

## Skills in Workflow (Internal)
- `skill-creator`: use when creating/updating skills; follow `docs/skill-contract.md`.
- `self-improving-agent`: if available in the active skill registry, use it for learning capture workflow; otherwise use `docs/learnings.md` fallback and document the same outcome.

## v1.0 Production Sign-off Gating (Live Telegram Path)
- Final verdict can be `GO` only if all are verified on the live OpenClaw Telegram transport path:
  - Telegram channel status verified via OpenClaw gateway
  - manual command acceptance verified
  - manual voice acceptance verified
- If any item is missing or unverified, verdict must be `GO WITH KNOWN LIMITATIONS` or `NO-GO`.
- Use `docs/cutover-checklist.md`, `docs/live-telegram-acceptance-template.md`, and `ops/capture-live-signoff.ps1`.

## Model Routing Policy (Strict)
- Single source of truth: `d_brain.services.model_routing.resolve_route(...)`.
- Task type defaults:
  - `MAIN_REASONING` -> `openai`
  - `VOICE_REPLY_REASONING` -> `openai`
  - `HEARTBEAT` -> `local`
  - `CRON_SUMMARY` -> `local`
  - `LIGHT_CLASSIFICATION` -> `local`
  - `COMMAND_STATUS` -> `deterministic`
- Command and voice routing paths apply policy in `d_brain.integrations.openclaw_bridge`.
- Sidecar heartbeat/cron paths apply policy in:
  - `d_brain.sidecar.dispatcher` (`heartbeat_tick`, `digest_generate`)
  - `d_brain.sidecar.jobs` (news/reminder delivery logging and daily briefing generation)
- Fallback rules:
  - Local unavailable -> optional fallback to OpenAI for utility tasks only (`MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK`).
  - OpenAI unavailable -> main reasoning fails gracefully by default.
  - OpenAI -> local fallback is disabled unless explicitly enabled (`MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK`).

## Skill Registry (OpenClaw Main)
- Main skill location: `vault/.claude/skills/openclaw-main`.
- Phase 1 is a bootstrap-only skill stub (no behavior changes).
- Phase 2 bridges a minimal command set via the OpenClaw adapter:
  - `/usage`
  - `/digest latest`
  - `/news latest`
  - `/word add <word>`
- Phase 3 Batch A (read-only/status) bridges:
  - `/word list`
  - `/topic list`
  - `/health list`
  - `/calendar today`
  - `/calendar upcoming [N]`
  - `/calendar date YYYY-MM-DD`
  - `/project list [status]`
  - `/task list [project_id] [status]`
- Phase 3 Batch B (low-risk writes) bridges:
  - `/topic add <name>`
  - `/health add <title>`
  - `/project add <name>`
  - `/task add <project_id> | <title>`
- Phase 3 Batch C (medium-risk workflows) bridges:
  - `/note <text or url>`
  - `/inbox add <text or url>`
  - `/inbox list`
  - `/inbox summarize <id>`
  - `/inbox save <id> [title]`
  - `/news generate`
  - `/news deliver`
- Phase 3 Batch D (voice/long-running/delivery) bridges:
  - `/tutor start [target_minutes]`
  - `/tutor stop`
  - `/tutor status`
  - `/reflect start`
  - `/reflect close <session_id> [summary]`
  - `/reminder deliver`
- OpenClaw bridge dispatch (transport-safe shared path):
  - `/help`, `/status`, `/plan list`, and `/plan add <title>` route through
    `d_brain.integrations.openclaw_bridge.dispatch_command`.
  - This keeps command behavior centralized in the d_brain bridge and avoids duplicate logic in the skill adapter.
  - Voice/text mode routing now also uses a shared bridge path:
    `d_brain.integrations.openclaw_bridge.dispatch_voice`.
  - STT language policy is centralized: default `ru`; `en` only for explicit tutor mode.
  - Transcript-only text does not override real media input when media is present.

## Production Command Contract (MVP, OpenClaw-first)
- Production Telegram transport remains OpenClaw-only (no aiogram polling in production mode).
- Bridge-owned command set (stable MVP):
  - `/help`
  - `/diag`
  - `/diag full`
  - `/ping`
  - `/version`
  - `/status`
  - `/mode`
  - `/prefs`
  - `/prefs brevity short|normal`
  - `/prefs lang ru|en_tutor`
  - `/prefs voice on|off`
  - `/voice on|off|status` (alias-compatible voice preference control)
  - `/plan add <title>`
  - `/plan list`
  - `/plan done <id>`
  - `/plan delete <id>` (soft-delete via `event_update_status status=canceled` to reuse existing plan lifecycle)
- Parsing rules:
  - Extra spaces are normalized.
  - Empty or malformed plan commands return short Russian usage errors.
  - Non-numeric IDs return a short Russian error (`ID must be a number` in RU UX).

### Per-User Bridge Preferences (v1.2)
- Storage: existing session JSONL store (`SessionStore`) via `user_pref` entries (no secrets, no Telegram SDK coupling).
- Keys:
  - `language_mode`: `ru` (default) | `en_tutor`
  - `voice_reply`: `on` (default) | `off`
  - `brevity`: `short` (default) | `normal`
- Applied behavior in bridge dispatch:
  - `language_mode=en_tutor` makes default bridge voice/text routing prefer tutor mode and English STT.
  - `voice_reply=off` skips TTS attempts and returns text replies with safe fallback behavior.
  - `brevity=short` returns shorter help/fallback/warning texts.

### Reliability Guard (Bridge -> Sidecar)
- Plan bridge handlers use a small timeout/exception guard around sidecar calls.
- On timeout/error the bridge returns a short safe fallback response and logs a structured degraded event (`degraded=true`) with handler/error type.
- Process should not crash due to sidecar/tool errors in bridge command handling.

### Observability and Admin Quick Controls (v1.3)
- `/diag` returns a short operator-friendly summary (transport mode, prefs summary, STT/TTS flags, sidecar probe, uptime, error counter summary).
- `/diag full` adds commit hash fallback, process start time, top error counters, and recent sanitized failures (no secrets, no API keys, no sensitive paths).
- `/ping` is a lightweight bridge response with route info and a small timing value.
- `/version` returns `d_brain` version + build + commit hash (fallback `unknown`).
- Runtime error tracker is in-memory only (resets on process restart) and is used for `/diag` plus structured logs.
- Bridge and key handler logs are normalized structured JSON entries with fields including `handler`, `source`, `action`, `status`, `error_type`, and `duration_ms`.

### RC Hardening Notes (v1.4)
- Bridge timeout handling is unified and timeout-safe for sidecar calls, STT, and TTS; `/diag full` reports effective timeout values for operator visibility.
- Degraded/error logs sanitize exception text to avoid leaking tokens/keys while preserving short diagnostic context.
- Command safety guards reject oversized command inputs and unsupported extra arguments for strict commands (`/help`, `/status`, `/ping`, `/version`, `/diag`) with short RU usage responses.
- OpenClaw adapter applies an early media payload guard before Telegram media send handoff: empty TTS bytes/zero-size files are downgraded to text fallback with structured warning `reason=empty_tts_output` (no media send attempt).
- OpenClaw bridge Telegram voice source selection now enforces explicit priority (`message.voice` -> `message.audio` -> audio `message.document` -> transcript/text fallback), attempts voice-note file download/STT before trusting auto-transcript text, and returns voice-note-safe retry text on download/STT/empty-transcript failures (no ".ogg/.m4a file" request for normal voice notes).
- Bridge emits structured diagnostics logs for voice source selection and ingest (`telegram_stt_source_select`, `telegram_voice_ingest`) with media flags, download outcome, STT source/outcome, and fallback reason fields.
- Voice-note diagnostics schema is now hardened for operator triage (no secrets): `requestId`, `userIdHash`, `messageKind`, Telegram file-id presence flags, downloader callback name/path, media bytes/path evidence, transcript shape hints (`transcriptLen`, `transcriptLooksAuto`), `finalInputSource`, `finalOutcome`, `fallbackReason` (stable enum), and `responseMode` when available.
- Bridge normalizes voice-note fallback reasons to a small stable taxonomy for logs/diagnostics (`voice_download_not_attempted`, `voice_download_failed`, `media_declared_without_bytes`, `stt_error`, `stt_empty`, `empty_transcript_voice_note`, `transcript_only_auto`, `transcript_only_no_media`, `no_voice_content`, `unsupported_media_shape`).
- Existing in-memory observability counters are reused for lightweight voice diagnostics counters (for example `telegram_voice_source.voice_file`, `telegram_voice_source.transcript`, `telegram_voice_fallback.voice_download_failed`, `telegram_voice_fallback.empty_transcript_voice_note`, `telegram_voice_fallback.transcript_only_auto`).
- Bridge API remains backward-compatible (normalized response contract + legacy keys preserved).

### Unified OpenClaw Bridge Response Contract
- Bridge responses are normalized to a shared contract (command + voice), while keeping legacy keys for compatibility:
  - `text` (`str | null`)
  - `audio_intent` (`sendVoice | sendAudio | null`)
  - `audio_path` (`str | null`) (optional path-based media handoff; may be null when legacy `audio_bytes` is used)
  - `meta` (`object`)
  - `ok` (`bool`)
  - `error_code` (`string`, optional)
- Legacy compatibility keys retained for current adapter/tests:
  - `handled`, `status`, `audio_bytes`, `mime_type`, `diagnostics`

### RU UX Examples (MVP)
- `/plan done 12` -> `Готово: #12 отмечен выполненным.`
- `/plan delete 12` -> `Удалено: #12.`
- `/plan done abc` -> short invalid ID error in RU
- `/mode` -> current mode + TTS on/off summary
- `/diag` is available as a transport-agnostic diagnostics command (MVP+ / operational, not required for the command MVP contract)

## Final Production Runtime Split
- OpenClaw owns Telegram transport (gateway/polling/channel integration).
- `d_brain` owns transport-agnostic bridge dispatch, business logic, sidecar actions, and service adapters.
- Model routing remains split:
  - OpenAI for main reasoning and voice reasoning replies
  - local providers for utility/search/cron tasks (with explicit fallback flags)

## E2E Stability Notes (OpenClaw-first)
- Non-command plain text in default mode is safe and non-fatal (bridge may ignore if no active tutor/reflection mode).
- Transcript-only warning remains short and does not override real media when media is present.
- Empty/missing TTS media falls back to text only; handler should not crash or loop on media retries.
- Single-poller guard remains active: `d_brain` should not start aiogram polling when `telegram_disabled=True`.

## What Stays Outside OpenClaw Core
- Domain logic and orchestration policies.
- SQLite schema and migrations.
- Vault organization and data retention.
- Custom collectors/workers and schedulers.
- Utility services (extraction, tagging, formatting).

## External Web/URL Skills
- `vault/.claude/skills/tavily-search` for web search and extraction via Tavily MCP tools.
- `vault/.claude/skills/summarize` for URL and YouTube summarization via the `summarize` CLI.
- `mcp-config.json` registers the `tavily` MCP server (`npx -y tavily-mcp@latest`).
- `TAVILY_API_KEY` must be set in the environment for Tavily.

### Minimal Contract Notes
Tavily search (MCP):
- Input: `query` (string), optional `search_depth`, `max_results`.
- Output: result list with `title`, `url`, and `content`/snippet fields.

Summarize (CLI):
- Input: URL or YouTube URL.
- Output: plain-text summary to stdout.

### Telegram Commands
- `/web search <query>` -> Tavily search (top 5).
- `/web summarize <url>` -> summarize CLI (plain output).
- `/youtube transcript <url>` -> summarize CLI transcript mode (plain output).

## Integration Interfaces
- Skill -> Sidecar: HTTP/RPC with explicit schemas and payload limits.
- Sidecar -> Skill: deterministic responses and error contracts.
- Logging/metrics: structured logs and trace IDs.

## Outbound Delivery Path (OpenClaw-first)
- Unified outbound module: `d_brain.integrations.openclaw_outbound`.
- Primary API:
  - `send_text(...)`
  - `send_tts(...)` (safe text fallback when TTS output is empty or media transport is unavailable)
  - `send_digest(...)`
  - `deliver(...)`
- Runtime sender registration:
  - `register_runtime_sender(...)` sets the process-local send callable used by bridge/scheduler paths.
  - When sender is not registered, outbound returns safe `delivery_state=deferred` (no exceptions).
- Structured result contract:
  - `ok`
  - `delivery_state` (`sent`, `deferred`, `no_target`, `failed`)
  - `channel`
  - `target`
  - `message_id`
  - `error`
  - `fallback_used` / `fallback_reason`
- Legacy shim remains at `d_brain.integrations.openclaw_outbound_adapter` for compatibility; production paths should use the unified outbound module.

## Job Runner Path (OpenClaw-first)
- Transport-agnostic jobs module: `d_brain.integrations.openclaw_jobs`.
- Integration entrypoint:
  - `run_job(job_type, context=..., runtime_sender=...)`
- Normalized job context fields:
  - `user_id`
  - `channel`
  - `target`
  - `source_ref`
  - `dry_run`
  - `trigger`
- Current job types:
  - `heartbeat_summary`
  - `daily_digest`
  - `plan_reminder_dispatch`
- Job result contract:
  - `ok`
  - `job_type`
  - `executed`
  - `skipped_reason`
  - `outbound_result`
  - `metrics` (`items_count`, `duration_ms`)
  - `error`
  - `payload`
- Fail-safe policy:
  - Typical delivery/runtime errors return structured safe results.
  - Exceptions are captured into `error` and do not crash caller paths.

## Memory Ingestion Path (OpenClaw-first)
- Unified ingestion module: `d_brain.memory.ingestion`.
- Entry points:
  - `ingest_record(...)`
  - `ingest_message_event(...)`
  - `ingest_job_result(...)`
- Normalized ingestion fields:
  - `source_type` (`text`, `voice`, `command`, `job`, `system`)
  - `user_id`, `channel`, `source_ref`
  - `text`, `language`, `tags`
  - `created_at`, `importance`, `needs_indexing`
- Storage reuse:
  - `VaultStorage.append_to_daily(...)`
  - `SessionStore.append(...)` when `user_id` is numeric
- Indexing behavior:
  - Optional indexer callable for lightweight immediate indexing.
  - If unavailable/fails, ingestion writes a deferred marker to `vault/.index_queue.jsonl`.
  - Ingestion/indexing failures are non-fatal and return structured safe results.

## Minimal Skill <-> Sidecar Contract (Draft)
Scope: Stage 1 only. Keep the surface small and avoid over-design.

### Request (Skill -> Sidecar)
- `request_id` (string, required): client-generated unique ID.
- `user_id` (string, required): stable caller identity.
- `action` (string, required): short verb, e.g. `ping`, `noop_job`.
- `payload` (object, optional): action-specific data (must be JSON-serializable).
- `metadata` (object, optional): trace IDs and client info.

### Response (Sidecar -> Skill)
- `request_id` (string, required): echo from request.
- `status` (string, required): `ok` or `error`.
- `data` (object, optional): action result.
- `error` (object, optional): `{ code, message }`.

### Validation Notes
- Reject unknown `action` values with `status=error`.
- Enforce JSON schema validation at the boundary.
- Validate `payload` per action and return structured errors.

### Payload Limits
- Default max payload size: 32 KB (configurable).
- Reject requests exceeding the limit with `status=error`.

## Stage 2: Ingestion Contract
Scope: ingestion + short summary pipeline. Reuse the Stage 1 request/response envelope.

### Action
- `action`: `ingest`

### Request Payload (action = ingest)
Required:
- `source_type` (string): e.g., `telegram`, `manual`, `import`.
- `content_type` (string): `text`, `audio`, `image`, `file`.
- `summary_format` (string): default `plain`.

Optional:
- `external_id` (string): client-side id for idempotency or tracking.
- `source_ref` (string): source message id, file id, or URL.
- `content` (string): inline content when `content_type=text`.
- `content_path` (string): path or URI to stored content (for non-text or large input).
- `content_hash` (string): hash of stored content for de-dupe.
- `metadata` (object): additional context (must be JSON-serializable).
  - `metadata.transcript` (string): required to summarize non-text inputs.

Validation rules:
- `source_type`, `content_type`, and `summary_format` are required.
- Provide exactly one of `content` or `content_path`.
- `content` is only allowed when `content_type=text`.
- `content_path` is required for non-text content types.
- Non-text content requires `metadata.transcript` for summarization.
- Reject payloads over 32 KB (configurable).

### Response Data (action = ingest)
- `artifact_id` (integer): created artifact record id.
- `summary_id` (integer): created summary record id.
- `summary_text` (string): short summary text.
- `summary_format` (string): echo input or default.
- `model_ref` (string): local utility model or heuristic identifier.

### Status Codes (app-level)
- `ok`: ingestion + summary created.
- `error`: validation failure, storage failure, or summarization failure.

Error object (when `status=error`):
- `code` (string): `invalid_payload`, `payload_too_large`, `unsupported_type`, `storage_error`, `summary_error`.
- `message` (string): human-readable summary.

## Stage 3: Plans and Reminders Contract
Scope: rule-first events, reminders, and minimal parsing. Reuse the Stage 1 request/response envelope.

### Actions
- `event_create`
- `event_list`
- `event_update_status`
- `event_parse`
- `reminder_list`
- `reminder_update_status`
- `reminder_trigger_due`

### Event Create Payload (action = event_create)
Required:
- `title` (string)

Optional:
- `body` (string)
- `start_at` (string, ISO 8601)
- `end_at` (string, ISO 8601)
- `remind_at` (string, ISO 8601)
- `source_type` (string)
- `source_ref` (string)

Behavior:
- If `remind_at` is omitted, default to `start_at` if provided, otherwise `now + 1 hour` (UTC).

### Event List Payload (action = event_list)
Optional:
- `status` (string): `planned`, `done`, `canceled`
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

### Event Update Status Payload (action = event_update_status)
Required:
- `event_id` (int)
- `status` (string): `planned`, `done`, `canceled`

### Event Parse Payload (action = event_parse)
Required:
- `text` (string)

Optional:
- `source_type` (string)
- `source_ref` (string)

Rule-first parse:
- Accepts only `title | <iso datetime>` format.
- Logs parse attempts to `event_parse_logs`.
- Fallback plan: keep parser rule-based for Stage 3; expand to richer parsing in Stage 4+.

### Reminder List Payload (action = reminder_list)
Optional:
- `status` (string): `pending`, `triggered`, `canceled`
- `due_before` (string, ISO 8601)
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

### Reminder Update Status Payload (action = reminder_update_status)
Required:
- `reminder_id` (int)
- `status` (string): `pending`, `triggered`, `canceled`

### Reminder Trigger (action = reminder_trigger_due)
No payload. Triggers due reminders and marks them as `triggered`.

## Stage 4: English MVP Contract (First Pass)
Scope: English learning storage and session lifecycle. Reuse the Stage 1 request/response envelope.

### Actions
- `english_word_add`
- `english_word_list`
- `english_topic_add`
- `english_topic_list`
- `english_session_create`
- `english_session_turn_append`
- `english_session_close`

### Word Add Payload (action = english_word_add)
Required:
- `word` (string)

Response Data:
- `word_id` (integer)

### Word List Payload (action = english_word_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `words` (array): each item includes `id`, `word`, `created_at`, `updated_at`.

### Topic Add Payload (action = english_topic_add)
Required:
- `name` (string)

Response Data:
- `topic_id` (integer)

### Topic List Payload (action = english_topic_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `topics` (array): each item includes `id`, `name`, `created_at`, `updated_at`.

### Session Create Payload (action = english_session_create)
Optional:
- `topic_id` (int)

Response Data:
- `session_id` (integer)

### Session Turn Append Payload (action = english_session_turn_append)
Required:
- `session_id` (int)
- `role` (string): `user`, `assistant`, or `system`
- `content` (string)

Response Data:
- `turn_id` (integer)

### Session Close Payload (action = english_session_close)
Required:
- `session_id` (int)

Optional:
- `summary_text` (string)

Response Data:
- `session_id` (integer)
- `summary_text` (string)

## Stage 5: Reflection MVP Contract (First Pass)
Scope: session-based reflection storage and close-summary flow. Reuse the Stage 1 request/response envelope.

### Actions
- `reflection_session_create`
- `reflection_turn_append`
- `reflection_session_close`
- `reflection_session_list`

### Session Create Payload (action = reflection_session_create)
No payload required.

Response Data:
- `session_id` (integer)

### Session Turn Append Payload (action = reflection_turn_append)
Required:
- `session_id` (int)
- `role` (string): `user`, `assistant`, or `system`
- `content` (string)

Response Data:
- `turn_id` (integer)

### Session Close Payload (action = reflection_session_close)
Required:
- `session_id` (int)

Optional:
- `summary_text` (string)

Response Data:
- `session_id` (integer)
- `summary_text` (string)

### Session List Payload (action = reflection_session_list)
Optional:
- `status` (string): `open` or `closed`
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `sessions` (array): each item includes `id`, `status`, `opened_at`, `closed_at`, `summary_text`, `created_at`, `updated_at`.

## Stage 6: News MVP Contract (First Pass)
Scope: sections, sources, and raw item ingestion with deterministic dedupe.

### Actions
- `news_section_create`
- `news_section_list`
- `news_section_update`
- `news_source_create`
- `news_source_list`
- `news_source_update`
- `news_item_ingest`

### Section Create Payload (action = news_section_create)
Required:
- `name` (string)

Optional:
- `description` (string)
- `status` (string): `active` or `inactive`

Response Data:
- `section_id` (integer)

### Section List Payload (action = news_section_list)
Optional:
- `status` (string): `active` or `inactive`
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `sections` (array): items include `id`, `name`, `description`, `status`, `created_at`, `updated_at`.

### Section Update Payload (action = news_section_update)
Required:
- `section_id` (int)

Optional (at least one):
- `name` (string)
- `description` (string)
- `status` (string): `active` or `inactive`

Response Data:
- `section_id` (integer)

### Source Create Payload (action = news_source_create)
Required:
- `section_id` (int)
- `name` (string)
- `source_type` (string) e.g., `rss`, `telegram`, `manual`

Optional:
- `source_ref` (string) e.g., url or channel handle
- `status` (string): `active` or `inactive`

Response Data:
- `source_id` (integer)

### Source List Payload (action = news_source_list)
Optional:
- `section_id` (int)
- `status` (string): `active` or `inactive`
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `sources` (array): items include `id`, `section_id`, `name`, `source_type`, `source_ref`,
  `status`, `created_at`, `updated_at`.

### Source Update Payload (action = news_source_update)
Required:
- `source_id` (int)

Optional (at least one):
- `section_id` (int)
- `name` (string)
- `source_type` (string)
- `source_ref` (string)
- `status` (string): `active` or `inactive`

Response Data:
- `source_id` (integer)

### News Item Ingest Payload (action = news_item_ingest)
Required:
- `section_id` (int)
- `source_id` (int)

Optional (at least one):
- `external_id` (string)
- `title` (string)
- `url` (string)
- `published_at` (string, ISO 8601)
- `content_text` (string)
- `raw_payload` (object)

Response Data:
- `news_item_id` (integer)
- `deduped` (boolean)

### Dedupe Hash Normalization
Deterministic dedupe uses a sha256 hash of a normalized JSON object:
- Normalize fields by trimming and collapsing internal whitespace.
- Lowercase `title`, `url`, and `content_text` for hash input.
- Include `published_at` and `external_id` after trimming (no lowercasing).
- Include `raw_payload` as a JSON object.
- Serialize with sorted keys and compact separators before hashing.

## Stage 6: News MVP Contract (Second Pass)
Scope: news summaries and manual briefing generation with exactly 5 key events.

### Actions
- `news_item_summarize`
- `news_briefing_generate`
- `news_briefing_get`
- `news_briefing_list`
- `news_item_save_to_db`

### News Item Summarize Payload (action = news_item_summarize)
Required:
- `news_item_id` (int)

Optional:
- `summary_format` (string, default `plain`)

Response Data:
- `summary_id` (integer)
- `news_item_id` (integer)
- `summary_text` (string)
- `summary_format` (string)
- `model_ref` (string)

### News Briefing Generate Payload (action = news_briefing_generate)
Optional:
- `section_id` (int)
- `source_id` (int)
- `limit` (int, default 50, min 5, max 500)

Behavior:
- Manual-only generation (no scheduler).
- Dedupe-aware selection uses normalized title/url/content_text.
- Exactly 5 unique items are required; generation fails if fewer than 5 exist.

Response Data:
- `briefing_id` (integer)
- `items` (array of briefed items with source fields and summaries)

### News Briefing Get Payload (action = news_briefing_get)
Optional:
- `briefing_id` (int, default latest)

Response Data:
- `id`, `briefing_mode`, `created_at`, `updated_at`
- `items` (array with `news_item_id`, `source_id`, `title`, `url`, `published_at`,
  `summary_text`, `source_name`, `source_type`, `source_ref`)

### News Briefing List Payload (action = news_briefing_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `briefings` (array of briefings)

### News Item Save Payload (action = news_item_save_to_db)
Required:
- `news_item_id` (int)

Optional:
- `note_title` (string)

Response Data:
- `note_id` (integer)

## Stage 7: Digest + Heartbeat Contract (First Pass)
Scope: system-state digest and heartbeat logging. Manual-only digest generation.

### Actions
- `heartbeat_tick`
- `digest_generate`
- `digest_get_latest`
- `digest_list`

### Heartbeat Tick Payload (action = heartbeat_tick)
Optional:
- `event_type` (string, default `heartbeat_tick`)
- `event_source` (string)
- `event_details` (object)

Response Data:
- `heartbeat_log_id` (integer)
- `event_type` (string)
- `event_source` (string)
- `created_at` (string, ISO 8601)

### Digest Generate Payload (action = digest_generate)
Optional:
- `digest_type` (string, default `system_state`)

Response Data:
- `digest_id` (integer)
- `digest_type` (string)
- `payload` (object)
- `created_at` (string, ISO 8601)
- `updated_at` (string, ISO 8601)

Digest payload (system_state):
- `payload_version` (int, `1`)
- `digest_type` (string, `system_state`)
- `generated_at` (string, ISO 8601)
- `counts` (object with entity counts)
- `latest` (object with latest timestamps)
- `status` (object with `db_path`)

### Digest Get Latest Payload (action = digest_get_latest)
No payload required.

Response Data:
- `id` (integer)
- `digest_type` (string)
- `payload` (object)
- `created_at` (string, ISO 8601)
- `updated_at` (string, ISO 8601)

### Digest List Payload (action = digest_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `digests` (array): each item includes `id`, `digest_type`, `created_at`, `updated_at`.

## Stage 8: Codex Limits Indicator + Economy Mode (First Pass)
Scope: usage logging, limits settings, and advisory status only. No automatic routing.

### Actions
- `codex_usage_log_add`
- `codex_usage_status_get`
- `codex_limits_settings_upsert`
- `codex_limits_settings_get`
- `codex_usage_list` (optional, first pass)

### Codex Usage Log Add Payload (action = codex_usage_log_add)
Optional:
- `scope_key` (string, default `global`)
- `request_id` (string)
- `user_id` (string)
- `model_ref` (string)
- `context` (string)
- `tokens_in` (int, default 0)
- `tokens_out` (int, default 0)
- `total_tokens` (int, default 0; if 0, uses tokens_in + tokens_out)
- `latency_ms` (int, default 0)
- `request_count` (int, default 1)
- `metadata` (object)

Response Data:
- `usage_log_id` (integer)
- `scope_key` (string)
- `created_at` (string, ISO 8601)
- `total_tokens` (int)

### Codex Limits Settings Upsert Payload (action = codex_limits_settings_upsert)
Optional:
- `scope_key` (string, default `global`)
- `window_hours` (int, default 24)
- `max_tokens` (int, default 0)
- `max_requests` (int, default 0)
- `max_latency_ms` (int, default 0)
- `warn_ratio` (float, default 0.70)
- `critical_ratio` (float, default 0.90)

Response Data:
- `settings_id` (integer)
- `scope_key` (string)
- `window_hours` (int)
- `max_tokens` (int)
- `max_requests` (int)
- `max_latency_ms` (int)
- `warn_ratio` (float)
- `critical_ratio` (float)
- `updated_at` (string, ISO 8601)

### Codex Limits Settings Get Payload (action = codex_limits_settings_get)
Optional:
- `scope_key` (string, default `global`)

Response Data:
- `settings_id` (integer)
- `scope_key` (string)
- `window_hours` (int)
- `max_tokens` (int)
- `max_requests` (int)
- `max_latency_ms` (int)
- `warn_ratio` (float)
- `critical_ratio` (float)
- `updated_at` (string, ISO 8601)

### Codex Usage Status Get Payload (action = codex_usage_status_get)
Optional:
- `scope_key` (string, default `global`)

Response Data:
- `scope_key` (string)
- `window_hours` (int, default 24)
- `window_start` / `window_end` (string, ISO 8601)
- `usage` (object: `total_tokens`, `total_requests`, `total_latency_ms`)
- `limits` (object: `max_tokens`, `max_requests`, `max_latency_ms`)
- `percent_used` (object: `tokens`, `requests`, `latency_ms`; null if limit is 0)
- `warn_ratio` (float, default 0.70)
- `critical_ratio` (float, default 0.90)
- `status_level` (string: `no_limits`, `ok`, `warn`, `critical`)
- `warnings` (array of strings)
- `economy_mode_consider` (boolean)
- `economy_mode_recommended` (boolean)

### Codex Usage List Payload (action = codex_usage_list)
Optional:
- `scope_key` (string, default `global`)
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `usage_logs` (array)

## Stage 9: Health MVP (First Pass)
Scope: structured health tracking and artifact linking only. No diagnosis or recommendations.

### Actions
- `health_record_add`
- `health_record_list`
- `health_medication_add`
- `health_medication_list`
- `health_treatment_add`
- `health_treatment_list`
- `health_observation_add`
- `health_observation_list`
- `health_lab_report_add`
- `health_lab_report_list` (optional)

### Health Record Add Payload (action = health_record_add)
Required:
- `title` (string)

Optional:
- `record_type` (string)
- `notes` (string)
- `occurred_at` (string, ISO 8601)
- `source_type` (string)
- `source_ref` (string)

Response Data:
- `record_id` (integer)

### Health Record List Payload (action = health_record_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `records` (array)

### Health Medication Add Payload (action = health_medication_add)
Required:
- `name` (string)

Optional:
- `dosage` (string)
- `schedule` (string)
- `started_at` (string, ISO 8601 or date)
- `ended_at` (string, ISO 8601 or date)
- `notes` (string)

Response Data:
- `medication_id` (integer)

### Health Medication List Payload (action = health_medication_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `medications` (array)

### Health Treatment Add Payload (action = health_treatment_add)
Required:
- `name` (string)

Optional:
- `description` (string)
- `started_at` (string, ISO 8601 or date)
- `ended_at` (string, ISO 8601 or date)
- `notes` (string)

Response Data:
- `treatment_id` (integer)

### Health Treatment List Payload (action = health_treatment_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `treatments` (array)

### Health Observation Add Payload (action = health_observation_add)
Required:
- `observation_type` (string)

Optional:
- `value` (string)
- `unit` (string)
- `observed_at` (string, ISO 8601)
- `notes` (string)

Response Data:
- `observation_id` (integer)

### Health Observation List Payload (action = health_observation_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `observations` (array)

### Health Lab Report Add Payload (action = health_lab_report_add)
Required:
- `artifact_id` (int)

Optional:
- `title` (string)
- `report_date` (string, ISO 8601 or date)
- `notes` (string)

Response Data:
- `lab_report_id` (integer)

### Health Lab Report List Payload (action = health_lab_report_list)
Optional:
- `artifact_id` (int)
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `lab_reports` (array)

## Stage 10: Idea Research / Product Factory (First Pass)
Scope: manual-only research runs with structured findings and short reports. No web crawling or automation.

### Actions
- `idea_research_job_create`
- `idea_research_job_list`
- `idea_research_job_update` (optional)
- `idea_research_run_start`
- `idea_research_run_get`
- `idea_research_report_get`

### Job Create Payload (action = idea_research_job_create)
Required:
- `title` (string)

Optional:
- `status` (string, default `active`)
- `notes` (string)

Response Data:
- `job_id` (integer)

### Job List Payload (action = idea_research_job_list)
Optional:
- `status` (string: `active`, `archived`)
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `jobs` (array): each item includes `id`, `title`, `status`, `notes`, `created_at`, `updated_at`.

### Job Update Payload (action = idea_research_job_update)
Required:
- `job_id` (int)

Optional (at least one):
- `title` (string)
- `status` (string: `active`, `archived`)
- `notes` (string)

Response Data:
- `job_id` (integer)

### Run Start Payload (action = idea_research_run_start)
Required:
- `job_id` (int)

Optional:
- `finding_types` (array of strings)
- `summary_text` (string)

Behavior:
- Manual-only run.
- Creates a run record, placeholder findings, and a short report.
- Updates `stage` and `status` for traceability.

Response Data:
- `job` (object)
- `run` (object)
- `findings` (array)
- `report` (object)

### Run Get Payload (action = idea_research_run_get)
Required:
- `run_id` (int)

Response Data:
- `job` (object)
- `run` (object)
- `findings` (array)
- `report` (object or null)

### Report Get Payload (action = idea_research_report_get)
Optional (one required):
- `report_id` (int)
- `run_id` (int)

Response Data:
- `id`, `run_id`, `report_text`, `report_format`, `created_at`, `updated_at`

## Stage 11: Telegram UX Wiring MVP (First Pass)
Scope: text-only Telegram commands wired to existing sidecar actions with a thin adapter.

### Command Map
- `/plan add <title>` -> `event_create`
- `/plan list` -> `event_list`
- `/reminder list` -> `reminder_list`
- `/note <text or url>` -> `ingest`
- `/word add <word>` -> `english_word_add`
- `/word list` -> `english_word_list`
- `/topic add <name>` -> `english_topic_add`
- `/topic list` -> `english_topic_list`
- `/news latest` -> `news_briefing_get`
- `/health add <title>` -> `health_record_add`
- `/health list` -> `health_record_list`
- `/reflect start` -> `reflection_session_create`
- `/reflect add <session_id> <text>` -> `reflection_turn_append`
- `/reflect close <session_id> [summary]` -> `reflection_session_close`
- `/digest latest` -> `digest_get_latest`
- `/usage` -> `codex_usage_status_get`

## Compatibility Goals
- Minimize deep core modifications.
- Use adapters/configs to preserve update compatibility.
- Keep APIs versioned and forward-compatible.

## Guardrails
- No hardcoding in skills or sidecar.
- Migrations are explicit and versioned.
- Context payloads are validated and size-limited.
- Documentation updates are mandatory for behavior/routing changes (see Documentation Contract above).

## Stage 12: Voice English Tutor MVP (First Pass)
Scope: message-based voice English tutor loop in Telegram using existing English session storage.

### Telegram Entry Points
- `/tutor start [target_minutes]` to open a tutor session.
- `/tutor stop` to close the session.
- `/tutor status` to check the current session.
- Voice messages route to the tutor flow only when a tutor session is active.
- Text messages follow the tutor flow only when a tutor session is active.

### STT/TTS Adapters
Provider-agnostic adapters are used for speech:
- STT adapter returns structured `STTResult` with errors when unavailable.
- TTS adapter returns structured `TTSResult`; missing provider falls back to text reply.

### Tutor Flow (Message-Based)
1. Voice or text input received.
2. For voice: STT transcript produced (English language).
3. Append user turn via `english_session_turn_append`.
4. Generate assistant reply via a reply generator boundary.
5. Append assistant turn via `english_session_turn_append`.
6. For voice: TTS output is returned if configured; otherwise send text reply.

## Stage 13: Reflection Voice Loop MVP (First Pass)
Scope: message-based reflection voice loop in Telegram using existing reflection session storage.

### Telegram Entry Points
- `/reflect start` opens a reflection session and activates reflection mode for the user.
- `/reflect close <session_id> [summary]` closes the session and exits reflection mode.
- While reflection mode is active, voice and text messages route to the reflection flow.

### STT/TTS Adapters
- Reuse the Stage 12 provider-agnostic STT adapter for transcript generation.
- Reuse the Stage 12 provider-agnostic TTS adapter for voice replies.
- Missing providers return structured errors; text fallback is always available.

### Reflection Flow (Message-Based)
1. Voice or text input received.
2. For voice: STT transcript produced (default language).
3. Append user turn via `reflection_turn_append`.
4. Generate assistant reply via a reply generator boundary.
5. Append assistant turn via `reflection_turn_append`.
6. For voice: TTS output is returned if configured; otherwise send text reply.

## Stage 14: Books / Philosophy / Knowledge UX MVP (First Pass)
Scope: text-only UX with reuse-first storage. No new heavy schema.

### Storage Strategy
- Knowledge inbox items use `artifacts` + `artifact_summaries` via the existing ingest pipeline.
- Durable saved entries use `notes`.
- Categorization uses a minimal `note_categories` link table.

### Telegram Entry Points
- `/book add <text or url>` -> `books_add`
- `/book list` -> `books_list`
- `/philosophy add <text or url>` -> `philosophy_add`
- `/philosophy list` -> `philosophy_list`
- `/inbox add <text or url>` -> `knowledge_inbox_add`
- `/inbox list` -> `knowledge_inbox_list`
- `/inbox summarize <id>` -> `knowledge_item_summarize`
- `/inbox save <id> [title]` -> `knowledge_item_save_to_db`

### Actions
- `books_add`
- `books_list`
- `philosophy_add`
- `philosophy_list`
- `knowledge_inbox_add`
- `knowledge_inbox_list`
- `knowledge_item_summarize`
- `knowledge_item_save_to_db`

### Books Add Payload (action = books_add)
Required:
- `content` (string)

Optional:
- `source_ref` (string)

Response Data:
- `note_id` (integer)

### Books List Payload (action = books_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `books` (array of notes)

### Philosophy Add Payload (action = philosophy_add)
Required:
- `content` (string)

Optional:
- `source_ref` (string)

Response Data:
- `note_id` (integer)

### Philosophy List Payload (action = philosophy_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `items` (array of notes)

### Knowledge Inbox Add Payload (action = knowledge_inbox_add)
Required:
- `content` (string)

Optional:
- `summary_format` (string, default `plain`)
- `source_ref` (string)
- `external_id` (string)

Response Data:
- `artifact_id` (integer)
- `summary_id` (integer)
- `summary_text` (string)
- `summary_format` (string)
- `model_ref` (string)

### Knowledge Inbox List Payload (action = knowledge_inbox_list)
Optional:
- `limit` (int, default 50, max 200)
- `offset` (int, default 0)

Response Data:
- `items` (array of artifacts with summaries)

### Knowledge Item Summarize Payload (action = knowledge_item_summarize)
Required:
- `artifact_id` (int)

Response Data:
- `artifact_id` (integer)
- `summary_id` (integer)
- `summary_text` (string)
- `summary_format` (string)
- `model_ref` (string)

### Knowledge Item Save Payload (action = knowledge_item_save_to_db)
Required:
- `artifact_id` (int)

Optional:
- `note_title` (string)

Response Data:
- `note_id` (integer)

## Stage 15: News Automation + Morning Briefing Delivery MVP (First Pass)
Scope: scheduler-triggerable daily briefing generation and Telegram delivery.

### Scheduler Jobs
- `news_briefing_generate_daily` (job): generates a daily briefing using the existing pipeline.
- `news_briefing_deliver_telegram` (job): delivers the latest briefing to Telegram.

### Telegram Commands
- `/news generate` -> `news_briefing_generate` (manual generation)
- `/news deliver` -> fetch latest briefing and deliver to current chat

### Delivery Traceability
- Uses `heartbeat_logs` with `event_type=news_delivery`.
- `event_details` includes `briefing_id`, `chat_id`, `status`, and optional `error`.

## Stage 16: Reminders Delivery + Calendar-style Telegram Views MVP (First Pass)
Scope: scheduled reminder delivery + text-only calendar views in Telegram.

### Scheduler Jobs
- `reminder_delivery_telegram` (job): deliver due reminders to allowed Telegram users.

### Telegram Commands
- `/reminder deliver` -> `reminder_delivery_run` (manual delivery to current chat)
- `/calendar today` -> `calendar_view` (`view=today`)
- `/calendar upcoming [N]` -> `calendar_view` (`view=upcoming`, optional limit)
- `/calendar date YYYY-MM-DD` -> `calendar_view` (`view=date`, date filter)

### Actions
- `reminder_delivery_run`
- `calendar_view`

### Reminder Delivery Run Payload (action = reminder_delivery_run)
Required:
- `chat_id` (int)

Optional:
- `mode` (string): `manual` or `scheduler` (default `manual`)

Response Data:
- `attempted` (int)
- `delivered` (int)
- `sent` (bool)
- `chat_ids` (array of ints)

### Calendar View Payload (action = calendar_view)
Required:
- `view` (string): `today`, `upcoming`, or `date`

Optional:
- `limit` (int, default 10, max 200)
- `date` (string, required only for `view=date`, format `YYYY-MM-DD`)

Response Data:
- `view` (string)
- `date` (string or null)
- `count` (int)
- `items` (array of reminders joined with event fields)

### Delivery Traceability
- Uses `heartbeat_logs` with `event_type=reminder_delivery`.
- `event_details` includes `status`, `reminder_id`, `event_id`, `chat_id`, optional `error`.

## Stage 18: Projects & Tasks MVP (First Pass)
Scope: minimal projects/tasks workflow with dedicated tables. No reminder integration.

### Telegram Command Map
- `/project add <name>` -> `project_create`
- `/project list [status]` -> `project_list`
- `/project archive <project_id>` -> `project_update_status` (`status=archived`)
- `/task add <project_id> | <title>` -> `task_create`
- `/task add <project_id> | <title> | due:YYYY-MM-DD` -> `task_create`
- `/task list [project_id] [status]` -> `task_list`
- `/task done <task_id>` -> `task_update_status` (`status=done`)
- `/task reopen <task_id>` -> `task_update_status` (`status=open`)
- `/task cancel <task_id>` -> `task_update_status` (`status=canceled`)
- `/task note <task_id> <text>` -> `task_note_add`
- `/task move <task_id> <project_id>` -> `task_update_project`

### Parsing Notes (MVP)
- Prefer delimiter-based parsing for add commands: `/task add <project_id> | <title>`.
- Optional due date uses a suffix: `/task add <project_id> | <title> | due:YYYY-MM-DD`.
- Use strict date format for due date parsing.

### Actions
- `project_create`
- `project_list`
- `project_update_status`
- `project_get` (optional)
- `task_create`
- `task_list`
- `task_update_status`
- `task_update_project`
- `task_note_add`
- `task_get` (optional)

### Payload Sketch (MVP)
- `project_create`: `{ "name": string }`
- `project_list`: `{ "status"?: "active" | "archived", "limit"?: int, "offset"?: int }`
- `project_update_status`: `{ "project_id": int, "status": "active" | "archived" }`
- `project_get`: `{ "project_id": int }`
- `task_create`: `{ "project_id": int, "title": string, "due_at"?: string (YYYY-MM-DD), "source_type"?: string, "source_ref"?: string }`
- `task_list`: `{ "project_id"?: int, "status"?: "open" | "done" | "canceled", "limit"?: int, "offset"?: int }`
- `task_update_status`: `{ "task_id": int, "status": "open" | "done" | "canceled" }`
- `task_update_project`: `{ "task_id": int, "project_id": int }`
- `task_note_add`: `{ "task_id": int, "text": string }`
- `task_get`: `{ "task_id": int }`

### Response Data (MVP)
- `project_create`: `{ "project_id": int }`
- `project_list`: `{ "projects": array }`
- `project_update_status`: `{ "project_id": int }`
- `project_get`: `{ "project": object }`
- `task_create`: `{ "task_id": int }`
- `task_list`: `{ "tasks": array }`
- `task_update_status`: `{ "task_id": int }`
- `task_update_project`: `{ "task_id": int, "project_id": int }`
- `task_note_add`: `{ "note_id": int, "task_id": int }`
- `task_get`: `{ "task": object }`
