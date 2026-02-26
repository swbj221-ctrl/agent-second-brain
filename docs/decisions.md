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
- Complete remaining OpenClaw-only Telegram UX migration beyond the centralized command and voice bridge paths
- Align legacy voice dispatch smoke scenarios with decode-first faster-whisper-only runtime path (valid media fixtures or explicit STT test doubles)

## Updates
- 2026-02-23 | Migration workflow using `scripts/migrate.py` + SQL files | Accepted | Simple, local SQLite-friendly baseline for Stage 1.
- 2026-02-23 | Stage 1 base schema tables | Accepted | Use `artifacts`, `artifact_summaries`, `notes`, `jobs`, `app_settings`, `app_feature_flags`.
- 2026-02-23 | Stage 12 uses provider-agnostic STT/TTS adapters with graceful fallback | Accepted | Keep Telegram thin while allowing provider swaps; missing providers return structured errors and fall back to text.
- 2026-02-24 | Stage 14 uses minimal `note_categories` link table | Accepted | Reuse `notes` and avoid a new knowledge schema while enabling categorization.
- 2026-02-23 | Lazy import for Telegram delivery dependencies | Accepted | Keep scheduler imports safe; delivery failures surface at runtime with traceability logs.
- 2026-02-23 | Reminder delivery traceability uses `heartbeat_logs` | Accepted | Avoid new tables; keep delivery attempts visible with minimal structured logging.
- 2026-02-24 | MSI install uses `requirements.txt` as canonical dependency manifest | Accepted | Simple, reliable pip path for Windows; `pyproject.toml` stays aligned for uv.
- 2026-02-24 | Canonical Windows venv folder is `.venv` | Accepted | Standardizes activation paths and reduces MSI setup confusion.
- 2026-02-24 | OpenClaw main skill lives under `vault/.claude/skills/openclaw-main` | Accepted | Uses the existing skill registry pattern and avoids a new top-level `skills/` folder.
- 2026-02-24 | OpenClaw gateway trusted proxies include loopback for dev tunnel | Accepted | Restores local client detection behind proxy without changing bind or auth.
- 2026-02-24 | OpenClaw workspace bootstrap/heartbeat files use lowercase filenames | Accepted | Ensures bootstrap/heartbeat detection on Windows.
- 2026-02-24 | Summarize CLI must be available on PATH for OpenClaw voice transcription | Accepted | Avoids CLI launch failures; use a PATH shim when needed.
- 2026-02-24 | OpenClaw is the only Telegram polling process (Variant 2) | Accepted | Prevents 409 conflicts and centralizes transport in OpenClaw.
- 2026-02-24 | OpenClaw command parsing for help/status/plan routes is centralized in `openclaw_bridge.dispatch_command` | Accepted | Keeps transport wrappers thin and avoids duplicated bridge logic across OpenClaw adapter and CLI.
- 2026-02-24 | OpenClaw voice/text mode routing is centralized in `openclaw_bridge.dispatch_voice` with RU default STT and EN tutor-only STT | Accepted | Keeps transport wrappers thin, preserves d_brain transport agnosticism, and prevents duplicated STT/TTS mode logic.
- 2026-02-24 | Strict model routing policy is centralized in `d_brain.services.model_routing` | Accepted | Enforces OpenAI-first reasoning, local utility-only defaults, explicit fallback flags, and routing diagnostics across bridge + periodic sidecar paths.
- 2026-02-24 | Unified OpenClaw-first outbound delivery is centralized in `d_brain.integrations.openclaw_outbound` | Accepted | Provides one transport-agnostic send API with structured safe results while preserving compatibility via a legacy adapter shim.
- 2026-02-24 | Unified memory ingestion is centralized in `d_brain.memory.ingestion` and keeps indexing best-effort | Accepted | Normalizes text/voice/command/job events into one contract, writes to existing vault/session stores, and degrades to deferred index queue instead of failing runtime flows.
- 2026-02-24 | Transport-agnostic local health snapshot is centralized in `d_brain.integrations.health` | Accepted | Reuses one no-network health contract for bridge `/health`/`/diag`, CLI diagnostics, and smokes while keeping transport wrappers thin.
- 2026-02-24 | Windows OpenClaw operations use reuse-first wrappers under `ops/` | Accepted | Keeps recovery/startup UX stable and idempotent by wrapping existing `scripts/*` implementations instead of duplicating runtime logic.
- 2026-02-24 | Single-poller conflict detection is warning-only (health/diag) | Accepted | Preserves non-disruptive diagnostics and recovery hints in production without killing processes automatically from runtime code.
- 2026-02-24 | OpenClaw bridge duplicate-update protection uses a short process-local TTL cache | Accepted | Reuse-first hardening that suppresses short-window replays without schema changes or cross-process coordination complexity.
- 2026-02-24 | Voice reply enable/disable is a per-user bridge preference stored in the existing session store | Accepted | Adds explicit user control for TTS without introducing a new settings table or changing transport adapters.
- 2026-02-24 | Bridge-level user preferences use session JSONL `user_pref` entries (`language_mode`, `voice_reply`, `brevity`) | Accepted | Reuse existing session store, avoid schema changes, keep transport-agnostic behavior in the bridge layer.
- 2026-02-24 | Bridge runtime observability uses an in-memory error tracker and `/diag full` (no DB persistence) | Accepted | Lightweight operator diagnostics with safe reset-on-restart semantics and no schema/transport coupling.
- 2026-02-24 | Bridge degraded/error logs sanitize exception text and keep timeout-safe short RU fallbacks | Accepted | RC hardening to reduce secret leakage risk while preserving operator diagnostics and non-fatal behavior.
- 2026-02-24 | Telegram voice-note STT diagnostics use a stable fallback reason taxonomy + structured evidence fields | Accepted | Speeds operator triage for `message.voice` failures without logging secrets/raw transcripts; reuses existing in-memory observability counters.
- 2026-02-25 | Telegram audio normalization before STT is opt-in via `TELEGRAM_STT_NORMALIZE_AUDIO` | Accepted | Preserves current behavior by default (no ffmpeg requirement) while enabling deterministic ffmpeg-based normalization for live diagnosis/quality tuning.
- 2026-02-25 | Non-tutor Telegram bridge STT language can be overridden via `TELEGRAM_STT_LANGUAGE` | Accepted | Enables targeted language-detection troubleshooting without changing tutor-mode language routing or hardcoding provider settings.
- 2026-02-25 | Embedded audio bypass hard-enforcement uses a local OpenClaw runtime exec-guard hotfix first | Accepted (temporary local control) | Direct Deepgram `exec` bypass is formed in installed OpenClaw embedded runtime (outside repo), so the smallest effective control is a pre-exec guard in the installed `pi-embedded` bundle that rewrites embedded audio STT calls to the project redirect shim.
- 2026-02-25 | Embedded wrapper transcript transport should prefer UTF-8-safe payloads (`TranscriptB64`) and treat mojibake transcript text as untrusted fallback input | Accepted | Shell/PowerShell `exec` paths on Windows can corrupt transcript text into garbled token patterns, so the wrapper decodes UTF-8/base64 in Python, emits explicit transcript diagnostics, and suppresses corrupted transcript fallback text while preserving media STT as the primary source.
- 2026-02-25 | Voice-call streaming STT should pass explicit multilingual-safe transcription hints (language + anti-transliteration prompt) via config | Accepted (temporary local runtime patch) | The active OpenClaw `voice-call` Twilio media-stream -> OpenAI Realtime STT path was sending model-only transcription session updates, which produced English-biased transliteration for RU and mixed RU/EN telephony speech. Add config-backed `streaming.sttLanguage`/`streaming.sttPrompt`, default to `ru` + bilingual anti-transliteration hint, and log selected STT settings + raw transcript preview for operator diagnosis.
- 2026-02-26 | Telegram bridge voice STT runtime path is faster-whisper only | Accepted | Remove paid/provider dependency from runtime STT path and keep all Telegram voice STT execution local in `openclaw_bridge.dispatch_voice`, with explicit diagnostics and internal decode.
- 2026-02-26 | Prefer `FASTER_WHISPER_MODEL=medium` for mixed RU+EN quality on Telegram voice | Accepted | Local validation showed `small` can transliterate mixed English tokens, while `medium` reliably preserved mixed-script phrase fidelity (`How are you` in Latin) on the target sample.

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
- 2026-02-24 | Scheduled digest delivery uses per-user OpenClaw target mapping with unified outbound contract and safe deferred fallback | Accepted | Keeps OpenClaw-only transport while allowing runtime sender integration without changing bridge API.

- 2026-02-25 | Windows `gateway/ws` pretty-log file writes should use sanitized ASCII-safe messages while preserving pretty console output | Accepted (temporary local runtime patch) | The `gateway/ws` pretty formatter emits ANSI + unicode glyphs that can degrade into mojibake in Windows log/file viewing paths; sanitize file writes (`stripAnsi`, ASCII-safe tokens) and keep a separate `consoleMessage` until upstreamed.
- 2026-02-25 | Voice-call STT transliteration diagnostics should log provider/model/language and short transcript previews before agent processing | Accepted | Operator triage for language-bias/transliteration issues requires visibility into the exact STT branch and raw transcript output, but logs must stay short and avoid dumping full call content.
- 2026-02-25 | Embedded voice wrapper-first tracing requires same-requestId full-chain proof and fail-closed on missing requestId | Accepted | Strict live acceptance needs one request-scoped runtime->redirect->wrapper->adapter->bridge marker chain; missing requestId must not silently pass because it can create false-positive bridge confirmation.
- 2026-02-25 | Embedded audio runtime exec-guard blocks direct Deepgram by default; allow only explicit diagnostic override | Accepted (temporary local runtime patch) | Normal embedded Telegram audio prompts must use wrapper-first bridge routing to preserve observability and policy controls. Direct Deepgram exec is allowed only when explicitly enabled (`OPENCLAW_AUDIO_DIRECT_DEEPGRAM_DIAGNOSTIC`) for diagnostics.
- 2026-02-25 | Live voice verdict parser must support runtime-style request IDs and nested log payload markers without weakening strict chain rules | Accepted | OpenClaw runtime/request tool IDs may include separators like `|` and marker JSON may be embedded in `raw` fields; parser must still require a same-requestId full chain for bridge confirmation.
- 2026-02-26 | Telegram voice final transcript source is fail-closed for media/inferred-media; provider transcript is blocked in that case | Accepted | Prevents partial English-tail transcript leakage (`how are you`) when media STT path is expected; diagnostics now emit `final_transcript_source_used` (`bridge_stt|provider_transcript|none`) and `final_transcript_source_block_reason` on blocked fallback.
- 2026-02-26 | Telegram `dispatch_voice` backend-switch STT runtime (`deepgram|faster_whisper|auto`) | Superseded | Replaced by strict faster-whisper-only Telegram media STT runtime policy (no Deepgram STT runtime branch in normal voice flow).
- 2026-02-26 | Telegram media STT runtime policy is strict faster-whisper-only with fail-closed behavior | Accepted | Supersedes backend-switch STT runtime behavior for Telegram voice path: Deepgram STT is disabled in normal runtime flow, `TELEGRAM_STT_BACKEND` resolves to `faster_whisper`, and failures do not silently fallback to Deepgram STT.
- 2026-02-26 | Telegram runtime TTS policy is local-only piper with fail-closed behavior | Accepted | Normal OpenClaw Telegram runtime does not use Deepgram TTS; `TELEGRAM_TTS_BACKEND` resolves to local piper unless explicit diagnostic override is enabled, and local TTS failures do not silently fallback to Deepgram.
- 2026-02-26 | Installed OpenClaw relay preflight transcript generation is diagnostic-only for audio media | Accepted (local runtime hotfix) | Prevents provider preflight transcription calls from running in normal mode for embedded Telegram audio; preflight transcript generation remains behind explicit `OPENCLAW_TELEGRAM_PROVIDER_TRANSCRIPT_DIAG`.
