# Context Pack

## Short Summary
OpenClaw-based system with reuse-first philosophy: one main skill and a sidecar backend. Local LLM is a utility layer; Codex handles reasoning/dialog/final synthesis. Focus: minimal context, operational clarity, and stable interfaces.

## Architecture Snapshot
- Reuse-tested solutions first (OpenClaw core, marketplace skills, stable libraries)
- One primary skill orchestrating flow
- One sidecar backend for integrations, state, and I/O
- Local LLM for utility tasks (classification, extraction, formatting)
- Codex for reasoning, dialog, and final synthesis
- Anti-context-bloat memory design (structured retrieval, summaries over raw transcripts, top-k context)
- Anti-hardcode policy (configs/adapters/feature flags and explicit migrations)
- Voice priority: human-like output and low latency
- Documentation is English-only (no Cyrillic)

## Project Constraints
- Reuse-tested solutions first
- One main skill + one sidecar backend
- Anti-context-bloat memory design
- Local LLM for utility tasks; Codex for reasoning/final synthesis
- Documentation is English-only (no Cyrillic)

## Current Session Goal
- Deliver v1.3 operator readiness for the OpenClaw-first production path: bridge-level user preferences (`/prefs`), reliability guardrails (timeout-safe sidecar degrade), and transport-agnostic diagnostics/admin quick controls (`/diag`, `/diag full`, `/ping`, `/version`) without changing the transport architecture.
- v1.4 RC hardening pass: unify/sanitize bridge timeout/fallback behavior, tighten command safety, finalize offline voice/command/diag no-polling smoke coverage, and add a single RC smoke suite command.

## Known Blockers
- MSI network TLS inspection blocks `summarize` URL fetches until corporate root CA is installed and provided to Node via `NODE_EXTRA_CA_CERTS`.

## Goals
- Ship a stable, minimal core pipeline
- Keep skills small and composable
- Make integration points explicit and testable

## Non-Goals
- Multiple parallel skills
- Heavy context dumping in prompts
- LLM as business logic

## Current Status
- Stage 1 foundation complete
- Stage 2 ingestion + summary pipeline complete with smoke test
- Stage 3 plans/reminders complete with smoke tests (default + parse)
- Stage 4 English MVP completed and validated by local smoke test on MSI
- Stage 5 Reflection MVP completed and validated by local smoke test on MSI
- Stage 6 News MVP second pass implemented; MSI validation pending
- Stage 7 Digest + Heartbeat first pass completed and validated by local smoke test on MSI
- Stage 8 Codex limits indicator + economy mode first pass completed and validated by local smoke test on MSI
- Stage 9 Health MVP first pass completed and validated by local smoke test on MSI
- Stage 10 Idea Research first pass completed and validated by local smoke test on MSI
- Stage 11 Telegram UX wiring MVP completed; manual Telegram verification on MSI pending
- Stage 12 Voice English Tutor MVP first pass implemented; MSI manual Telegram verification completed
- Stage 13 Reflection Voice Loop MVP first pass implemented; MSI manual Telegram verification completed
- Stage 14 Books / Philosophy / Knowledge UX MVP first pass implemented; manual Telegram verification on MSI pending
- Stage 16B Backup & Restore MVP implemented; weekly backups configured on MSI; restore verification pending
- Stage 18 Projects & Tasks MVP first pass implemented; MSI validated
- Deepgram TTS adapter added with config-driven fallback; TTS smoke script added.
- MSI venv standardized on `.venv`; gitignore tightened for venv variants.
- OpenClaw main adapter Phase 3 Batches A-D bridged (read-only, low-risk writes, medium workflows, and command-only voice/delivery).
- OpenClaw gateway trusted proxies set for dev tunnel; workspace bootstrap/heartbeat filenames normalized to lowercase.
- Variant 2 migration started: d_brain polling can be disabled via env flag; OpenClaw should be the only Telegram poller.
- Reusable UX helpers and a small CLI entry were added to prepare OpenClaw integration.
- Transport-agnostic command dispatcher is now centralized in `d_brain.integrations.openclaw_bridge.dispatch_command` with OpenClaw adapter + CLI smoke coverage.
- Transport-agnostic voice/text dispatcher is now centralized in `d_brain.integrations.openclaw_bridge.dispatch_voice` and wired to the OpenClaw main adapter entrypoint.
- Voice smoke checks (`openclaw_voice_dispatch_smoke.py`, `voice_media_preference_check.py`) passed locally via `.venv`.
- Unified outbound delivery module is now available at `d_brain.integrations.openclaw_outbound` with compatibility shim support for legacy adapter imports.
- Digest outbound smoke now covers `no_target`, `text_only`, and `tts_requested_but_empty` cases without aiogram polling.
- Transport-agnostic memory ingestion is now available at `d_brain.memory.ingestion` with unified contracts (`ingest_record`, `ingest_message_event`, `ingest_job_result`) and safe index deferral to `vault/.index_queue.jsonl`.
- OpenClaw bridge command/voice paths and OpenClaw job runner now call ingestion entrypoints with non-fatal behavior.
- Memory ingestion smoke coverage (`scripts/memory_ingestion_smoke.py`) validates text, voice transcript, job summary, empty-content skip, and indexer-unavailable fallback.
- Unified no-network E2E smoke coverage is available via `scripts/openclaw_e2e_smoke.py` for command/voice/job routing plus ingestion/indexer non-fatal fallback cases.
- Production diagnostics and fallback reliability smokes are available via `scripts/openclaw_prod_diag.py` and `scripts/openclaw_fallback_smoke.py`.
- Transport-agnostic health snapshot (`d_brain.integrations.health.get_health_snapshot`) now powers bridge `/health`/`/diag` and CLI `health`/`diag`, including single-poller conflict risk hints for OpenClaw-first production mode.
- Windows `ops/` scripts now provide one-command OpenClaw start/stop/restart/status, PATH session repair, duplicate poller cleanup, and ACL quick-fix wrappers.
- OpenClaw bridge command MVP is now polished with `/ping`, `/version`, and `/voice on|off|status` in addition to `/help`, `/status`, `/mode`, and `/plan *`.
- Bridge entrypoints now use a short TTL duplicate-update guard (`duplicate_skipped=true` in structured logs/meta) to suppress repeated processing of the same command/voice payload within one process.
- Per-user voice reply preference is stored via the existing session store (reuse-first, no schema changes); voice requests can be force-disabled (`/voice off`) while keeping text responses available.
- TTS send path observability is hardened with structured logging for provider/output file/send method/size and explicit text fallback reasons.
- Bridge-level per-user preferences are available via session-store-backed `/prefs` (`language_mode`, `voice_reply`, `brevity`) with `/voice on|off|status` alias compatibility; bridge voice dispatch applies these preferences.
- Bridge diagnostics/admin quick controls are available via `/diag` and `/diag full` (OpenClaw mode, prefs summary, STT/TTS flags, sidecar probe, uptime, runtime error counters/recent failures, commit hash fallback), plus improved `/ping` timing and `/version` commit hash fallback.
- Bridge runtime observability now includes lightweight in-memory error counters + recent failure ring buffer and normalized structured bridge/handler logs (`handler`, `source`, `action`, `status`, `error_type`, `duration_ms`).
- Bridge RC hardening adds sanitized degraded/exception logging for sidecar/STT/TTS paths, `/diag full` timeout visibility, and command safety guards for oversized input + invalid extra args on strict commands.
- Unified no-polling RC smoke suite is available via `scripts/openclaw_rc_smoke.py` (no-polling, readiness, command/prefs/diag/voice/media-priority checks).
- Telegram voice-note STT hardening/observability follow-up is implemented in the OpenClaw bridge: stable fallback taxonomy, expanded structured evidence fields (`telegram_stt_source_select` / `telegram_voice_ingest`), lightweight voice source/fallback counters, and operator helper `scripts/openclaw_voice_log_summary.py`.

## Key Paths
- `docs/` operational documentation
- `docs/agent/` agent profile (USER/IDENTITY/TOOLS/SOUL)
- `skills/` main skill (single source of truth)
- `backend/` sidecar service (if present)

## Contacts / Owners
- Owner: TBD
- On-call: TBD
