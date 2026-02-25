# Runbook

## Session Workflow (Codex)
- Use `docs/commands/open-session.md` to start every session.
- Use `docs/commands/close-session.md` to end every session.
- Update docs during implementation, not only at the end.
- Documentation must be English-only (no Cyrillic).

### Session Continuity Protocol (Required)
Before closing a session:
- Update required docs for any behavior/routing/workflow changes (see Documentation Contract below).
- Write current status, exact next step, and one exact continuation command.
- Update `.openclaw/workspace/heartbeat.md` with current state and next action if the workflow changed.
- Add a learnings entry to `docs/learnings.md` if there was a failure, user correction, workaround, or repeated-error fix.

On new session start:
- Read `.openclaw/workspace/bootstrap.md`.
- Read `.openclaw/workspace/heartbeat.md`.
- Read `docs/progress.md`.
- Read the latest entries in `docs/learnings.md`.
- Confirm current step and immediate next action before changing code/docs.

### Documentation Contract (Required for Code / Logic / Routing / Behavior Changes)
If code or behavior changes through Codex/OpenClaw work, update docs in the same session (not end-only).

Must-update files:
- `docs/progress.md`
- `docs/runbook.md`
- `docs/openclaw-integration.md`
- `.openclaw/workspace/BOOTSTRAP.md` (workspace file currently uses lowercase filename)
- `.openclaw/workspace/HEARTBEAT.md` (workspace file currently uses lowercase filename)

Conditional updates (if impacted):
- `docs/cutover-checklist.md`
- `docs/release-notes-v1.0-draft.md`
- skill docs (`vault/.claude/skills/...` or `docs/skills/...`)
- smoke checks in `scripts/*`

### Self-Improvement Log (Required Workflow)
- Use `docs/learnings.md` as the lightweight self-improvement log.
- Required entry triggers:
  - failed command/operation with identified cause
  - user correction to agent behavior/assumption
  - confirmed workaround/fix
  - recurring error prevented
- Entry format: `timestamp`, `symptom`, `root cause`, `fix`, `prevention`, plus short verification/reference notes.

### Skill Creation / Update Workflow (Internal)
- Use the `skill-creator` process when creating or updating skills.
- Follow the project skill contract in `docs/skill-contract.md`.
- If `self-improving-agent` is requested but unavailable in the current skill registry, use `docs/learnings.md` + this runbook workflow as the fallback and document the gap.

## OpenClaw Local Bootstrap (Windows, SSH-friendly)
Run from repo root:
- Start (foreground):
  - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`
- Start (detached):
  - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1 -Detached`
- Stop:
  - `powershell -ExecutionPolicy Bypass -File scripts/stop_openclaw_stack.ps1`
- Doctor checks:
  - `powershell -ExecutionPolicy Bypass -File scripts/openclaw_doctor.ps1`

Behavior:
- Adds `C:\Program Files\nodejs` and `%APPDATA%\npm` to PATH for the current shell.
- Normalizes process PATH segments (strips stray quotes) before command resolution to avoid Windows wrapper launch failures (for example `""node"" is not recognized`).
- Activates `.venv` when available.
- Sets `PYTHONPATH=src`.
- Enforces OpenClaw-only transport by setting `D_BRAIN_TELEGRAM_DISABLED=1` for the shell.
- Checks for port conflicts on `18789`.
- Prints the resolved `node.exe` path and the OpenClaw command path before launch.

Troubleshooting (startup wrapper):
- If foreground startup fails with `""node"" is not recognized`, run:
  - `Get-Command node`
  - `Get-Command openclaw`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\start_openclaw_stack.ps1`
- The script now fails early with a clear error if `node` or `openclaw` is not found in PATH.

## OpenClaw ACL Hardening (Windows)
Target paths:
- `C:\Users\User\.openclaw`
- `C:\Users\User\.openclaw\openclaw.json`
- `C:\Users\User\.openclaw\credentials`
- `C:\Users\User\.openclaw\agents\main\agent\auth-profiles.json`
- `C:\Users\User\.openclaw\agents\main\sessions\sessions.json`

Script:
- Dry run:
  - `powershell -ExecutionPolicy Bypass -File scripts/harden_openclaw_acl.ps1 -DryRun`
- Apply:
  - `powershell -ExecutionPolicy Bypass -File scripts/harden_openclaw_acl.ps1`

Recommended elevated apply:
- Open elevated PowerShell and run:
  - `cd D:\openclaw_bot\agent-second-brain`
  - `powershell -ExecutionPolicy Bypass -File scripts/harden_openclaw_acl.ps1`

Verify:
- `openclaw status`
- `icacls "C:\Users\User\.openclaw\openclaw.json"`
- `icacls "C:\Users\User\.openclaw\credentials"`

## Local Development
TODO: steps to start local services, env vars, and health checks.

## Telegram Polling (Conflict Prevention)
- Run only one polling process at a time.
- Option A: OpenClaw gateway polls Telegram (disable local polling).
- Option B: `python -m d_brain` polls Telegram (stop the gateway polling).
- Never run both simultaneously or you will get `getUpdates` conflicts (409).
- To disable local polling: set `D_BRAIN_TELEGRAM_DISABLED=1`.
- Production mode: OpenClaw is the only Telegram transport. Do not run `python -m d_brain` alongside `openclaw gateway`.
- If you see `409 Conflict`, it means two pollers are running. Stop the extra process and run only one OpenClaw gateway.

Windows PowerShell (recovery):
- `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
- `Stop-Process -Name python -Force`
- `Stop-Process -Name openclaw -Force`

## OpenClaw UX CLI (Phase 1)
- Use `scripts/ux_cli.py` to invoke reusable d_brain UX helpers without Telegram polling.
- Examples:
  - `python scripts/ux_cli.py status --user-id 123`
  - `python scripts/ux_cli.py help`
  - `python scripts/ux_cli.py command --user-id 123 --text "/plan list"`

## OpenClaw Command Dispatch Smoke (No Telegram Polling)
Run from repo root:
- `python scripts/openclaw_command_dispatch_smoke.py --user-id 123 --chat-id 123 --plan-title "Smoke plan"`
- `python scripts/openclaw_e2e_command_smoke.py`
- The transport-agnostic dispatcher entrypoint is `d_brain.integrations.openclaw_bridge.dispatch_command`.

Expected behavior:
- `/help` returns command help text.
- `/status` returns day status text.
- `/plan list` returns either records or `No records found.`.
- `/plan add <title>` returns created IDs and the next `/plan list` includes the new plan.

Production command MVP (OpenClaw bridge):
- `/help`, `/ping`, `/version`, `/status`, `/mode`
- `/prefs`
- `/prefs brevity short|normal`
- `/prefs lang ru|en_tutor`
- `/prefs voice on|off`
- `/voice on|off|status`
- `/plan add <title>`, `/plan list`, `/plan done <id>`, `/plan delete <id>`
- `/plan delete <id>` is implemented as a soft-delete (`canceled`) to reuse existing sidecar plan lifecycle.

New smoke coverage (`openclaw_command_dispatch_smoke.py`) also checks:
- `/prefs` show/set flows and `/voice` alias compatibility
- `/plan done <id>` and `/plan delete <id>`
- invalid inputs:
  - `/plan done`
  - `/plan done abc`
  - `/plan delete`
  - `/plan delete qwe`

CLI quick checks (PowerShell, from repo root):
- `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/mode"`
- `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/plan list"`
- `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/diag"` (MVP+ diagnostics)
- `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/diag full"` (extended diagnostics)

Response normalization note:
- Bridge command/voice outputs are normalized to a shared contract (`text`, `audio_intent`, `audio_path`, `meta`, `ok`, optional `error_code`) while legacy adapter-compatible fields remain available.
- Duplicate guard note:
  - Bridge entrypoints (`dispatch_command_response`, `dispatch_voice_sync`) use a short TTL duplicate cache to skip repeated processing of the same message/update payload.
  - Structured bridge logs include `duplicate_skipped=true` when a duplicate is skipped.

## Production Readiness Check (Offline)
Run from repo root:
- `.\.venv\Scripts\python.exe scripts\prod_readiness_check.py`

Checks (no network where possible):
- OpenClaw-first transport mode (`D_BRAIN_TELEGRAM_DISABLED` / effective config)
- bridge import and command/voice dispatcher callables
- workspace bootstrap/heartbeat files
- warn-only env readiness hints (OpenAI/Deepgram keys)

Expected summary:
- `PASS` or `WARN` is acceptable for offline local verification.
- `FAIL` requires fixing before production use.

## OpenClaw Voice Dispatch Smoke (No Telegram Polling)
Run from repo root:
- `python scripts/openclaw_voice_dispatch_smoke.py`
- `python scripts/openclaw_e2e_voice_smoke.py`
- Voice routing entrypoint: `d_brain.integrations.openclaw_bridge.dispatch_voice`.

Expected behavior:
- Default STT language is Russian (`ru`) for normal voice flow.
- English STT (`en`) is used only in tutor mode.
- Preference `language_mode=en_tutor` routes default voice flow through tutor mode with English STT.
- Preference `voice_reply=off` disables TTS attempts and returns text safely.
- Preference `brevity=short` returns shorter fallback/warning text.
- Transcript-only text warning path is returned when no media is present.
- Empty TTS output falls back to text and does not crash.
- Optional audio normalization before STT (disabled by default):
  - Set `TELEGRAM_STT_NORMALIZE_AUDIO=1` to convert compressed Telegram audio (for example OGG/OPUS/M4A/MP3) to mono 16k PCM WAV via `ffmpeg` before STT.
  - If enabled and `ffmpeg` is missing or conversion fails, bridge logs detailed pipeline diagnostics and returns a safe fallback response.
- Optional non-tutor Telegram STT language override:
  - Set `TELEGRAM_STT_LANGUAGE=ru` (or another provider-supported code) to override the default non-tutor bridge STT language.
- Optional non-tutor Telegram STT multipass (mixed RU+EN troubleshooting, opt-in):
  - `TELEGRAM_STT_MULTIPASS=1` enables multi-pass decode attempts for non-tutor voice/audio STT.
  - `TELEGRAM_STT_MULTIPASS_LANGS=auto,ru,en` controls pass order (`auto` = current default path language; duplicates are removed).
  - `TELEGRAM_STT_MIXED_HEURISTIC=1` enables lightweight candidate scoring (length/tokens/script mix) to prefer mixed-script transcripts when present.
  - Safety/compatibility: if `TELEGRAM_STT_LANGUAGE` is explicitly set, multipass is skipped and the explicit language override is used (logged as `stt_multipass_skip`).

Preference smoke:
- `python scripts/openclaw_prefs_smoke.py`
- Verifies bridge-level `/prefs` set/get and `/voice` alias compatibility using the JSONL session-backed store (no Telegram).

Diagnostics and observability smoke:
- `python scripts/openclaw_diag_smoke.py`
- `python scripts/openclaw_error_counter_smoke.py`
- Verifies `/diag` short/full output shape (no secrets) and runtime in-memory error counters.
- `python scripts/openclaw_voice_source_select_smoke.py`
- Verifies Telegram media source priority (`voice` -> `audio` -> audio `document` -> transcript`), voice-note download/STT fallback behavior, and no bad file-format UX fallback for normal `message.voice`.
- `python scripts/openclaw_voice_dispatch_smoke.py`
- Includes `TELEGRAM_STT_LANGUAGE` override coverage and a synthetic `audio_conversion_failed` fallback case (no `ffmpeg` dependency required for the smoke).
- Also includes a deterministic `ffmpeg_missing` fallback case (`TELEGRAM_STT_NORMALIZE_AUDIO=1` + monkeypatched `shutil.which`) with exact `pipeline_error_code=ffmpeg_missing` and preprocess stage log assertions.
- `python scripts/openclaw_voice_log_summary.py --file <logfile> --lines 200`
- Operator helper: extracts `telegram_stt_source_select` / `telegram_voice_ingest` and prints a per-`requestId` summary (`finalInputSource`, download/STT outcome, `finalOutcome`, `fallbackReason`, `responseMode`).
- Runtime patch marker (live verification):
  - On first bridge voice dispatch, the bridge logs `event=openclaw_bridge_voice_fix_loaded` with `bridgeFile` and `voiceFixRev`.
  - Use this once per process to confirm the patched bridge module is actually loaded before analyzing voice-note fallback behavior.
- Runtime import-path diagnostics (live verification):
  - Bridge logs once per process: `event=openclaw_bridge_runtime_module_path` with `moduleFile`, `cwd`, `sysPathHead`, `pid`.
  - Adapter logs at Telegram voice dispatch entry: `event=openclaw_bridge_runtime_dispatch_entry` with `moduleFile`, `hasVoice`, `hasAudio`, `hasDocument`.
  - If `moduleFile` is not under the repo `src\\d_brain\\integrations\\openclaw_bridge.py`, the runtime is loading a different module copy.
- Embedded OpenClaw audio bypass diagnostic (important):
  - If `openclaw logs` / gateway log shows Telegram activity but no `telegram_voice_pipeline` / `stt_multipass_*`, inspect OpenClaw session JSONL (`%USERPROFILE%\\.openclaw\\agents\\main\\sessions\\*.jsonl`) for tool calls.
  - If you see ad-hoc `exec` commands calling Deepgram directly, the message used the embedded direct STT path (`embedded_direct_stt`) instead of the `d_brain` bridge.
- Embedded audio bridge wrapper (diagnostic + restore path):
  - Redirect shim (workspace glue, wrapper-first):
    - `scripts/openclaw_embedded_media_redirect_cli.py`
    - Use this as the embedded-agent entry for Telegram embedded prompts with media.
    - It detects audio vs non-audio media, emits redirect proof/error markers, and invokes the wrapper CLI only for audio/voice/audio-document payloads.
    - Redirect proof marker (audio path): `event=openclaw_voice_dispatch_path_select`, `selectedPath=wrapper_cli_bridge`
    - Redirect skip marker (non-audio/text): `event=openclaw_voice_dispatch_path_select`, `selectedPath=embedded_default_flow`
    - Redirect anti-silent-bypass error marker: `event=openclaw_voice_dispatch_path_error`, `selectedPath=none`, `intendedPath=wrapper_cli_bridge`
  - Wrapper: `scripts/openclaw_live_voice_bridge_cli.py`
  - Input: full OpenClaw embedded Telegram message text (the message containing `[media attached ...]` / `<media:audio>` / optional `Transcript:`).
  - Encoding hardening:
    - Wrapper supports `TranscriptB64` / `TranscriptBase64` and decodes UTF-8 in Python (preferred over raw shell transcript text when available).
    - Wrapper normalizes empty embedded transcript to `EMPTY_TRANSCRIPT` (diagnostics only) and detects common mojibake patterns (garbled token patterns, replacement char).
    - If embedded transcript looks mojibake-corrupted, wrapper suppresses it before adapter handoff and relies on media STT instead of forwarding corrupted text as fallback input.
  - Output: JSON with proof marker `event=openclaw_voice_dispatch_path_select`, selected path, branch reason, `messageKind`, `isAudioDocument`, and adapter response summary or safe fallback.
  - Expected `selectedPath` for audio media: `d_brain_openclaw_bridge`
  - Diagnostic skip for non-audio documents: `selectedPath=embedded_direct_stt`, `error_code=non_audio_media`
  - Anti-silent-bypass guard:
    - If audio media is detected but the wrapper cannot dispatch to the bridge, it returns `error_code=bridge_dispatch_unavailable`
    - Wrapper emits `error_marker.event=openclaw_voice_dispatch_path_error` with `selectedPath=none` and `intendedPath=d_brain_openclaw_bridge`
    - Use `user_safe_text` and do not silently fall back to direct `exec` STT.
  - Wrapper transcript diagnostics (safe, no secrets):
    - `embedded_transcript_status` (`OK` | `EMPTY_TRANSCRIPT`)
    - `embedded_transcript_decode_mode` (`raw_utf8` | `base64_utf8` | `base64_invalid`)
    - `embedded_transcript_len`
    - `embedded_transcript_base64_decoded`
    - `embedded_transcript_mojibake_suspected`
- Voice pipeline debug logs (bridge):
  - `event=telegram_voice_pipeline` with stages such as `download_start`, `download_result`, `stt_preprocess_start|skip|ok|error`, `stt_request_start|error`, `stt_result`.
  - Multipass debug stages (opt-in): `stt_multipass_start`, `stt_multipass_candidate`, `stt_multipass_selected`, `stt_multipass_skip`.
  - Logs include sanitized metadata only (message kind, MIME, download result, ffmpeg args/exit, STT provider/model/language, transcript preview, fallback/pipeline error code).
  - Preprocess stage diagnostics now include `normalizeAudioEnabled`, `ffmpegPathFound`, `inputMimeType`, and `inputExt` (when available).
  - Multipass stages also include candidate/selection fields such as pass language, token count, script flags (Cyrillic/Latin), heuristic score, and selection/skip reason.
  - After embedded audio wrapper routing is used, expect this sequence for audio media:
    - proof marker JSON from wrapper: `openclaw_voice_dispatch_path_select` (`d_brain_openclaw_bridge`)
    - adapter proof marker: `openclaw_voice_dispatch_path_select` (`d_brain_openclaw_bridge`)
    - bridge stages: `telegram_voice_pipeline` and (if enabled) `stt_multipass_*`

Live bridge path confirmation (single mixed RU+EN voice test, PowerShell):
- Restart with multipass env:
  - `cd D:\openclaw_bot\agent-second-brain`
  - `$env:TELEGRAM_STT_MULTIPASS='1'`
  - `$env:TELEGRAM_STT_MULTIPASS_LANGS='auto,ru,en'`
  - `$env:TELEGRAM_STT_MIXED_HEURISTIC='1'`
  - `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
- Capture live logs to file (keep one terminal open):
  - `openclaw logs --follow --json --plain | Tee-Object -FilePath .\artifacts\openclaw_live_voice_bridge_verify.log`
- Send one Telegram mixed RU+EN voice/audio message through the wrapper-first embedded path.
- Verify expected markers in log file:
  - `Select-String -Path .\artifacts\openclaw_live_voice_bridge_verify.log -Pattern 'openclaw_voice_dispatch_path_select','openclaw_bridge_runtime_module_path','openclaw_bridge_runtime_dispatch_entry','telegram_voice_pipeline','stt_multipass_'`
- Verify the loaded bridge module path points to repo source:
  - `Select-String -Path .\artifacts\openclaw_live_voice_bridge_verify.log -Pattern 'openclaw_bridge_runtime_module_path','src\\\\d_brain\\\\integrations\\\\openclaw_bridge.py'`
- Check active OpenClaw session JSONL tail for bypass evidence (`exec` + direct Deepgram):
  - `$s=(Get-ChildItem "$env:USERPROFILE\.openclaw\agents\main\sessions" -Filter *.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName`
  - `Get-Content $s -Tail 200 | Select-String -Pattern 'openclaw_voice_dispatch_path_select','telegram_voice_pipeline','exec','deepgram'`
- Success sequence (audio media):
  1. runtime exec-guard `openclaw_voice_dispatch_path_select` (`selectedPath=wrapper_cli_bridge`, `sourceModule=pi-embedded.before_tool_call.exec_audio_guard`)
  2. redirect shim `openclaw_voice_dispatch_path_select` (`selectedPath=wrapper_cli_bridge`)
  3. wrapper `openclaw_voice_dispatch_path_select` (`selectedPath=d_brain_openclaw_bridge`)
  4. adapter `openclaw_voice_dispatch_path_select` (`selectedPath=d_brain_openclaw_bridge`)
  5. bridge `telegram_voice_pipeline`
  6. bridge `stt_multipass_start/candidate/selected` (when multipass envs are enabled)
- Bypass indicators:
  - Session JSONL shows ad-hoc `exec` + direct Deepgram STT tool calls
  - Wrapper/adapter proof markers are missing
  - `telegram_voice_pipeline` and `stt_multipass_*` are missing for the same test message
- Core runtime patch-point hypothesis (minimal, outside this repo):
  - Priority 1: embedded tool dispatcher / exec-tool guard, immediately before executing `toolCall exec`.
    - If the current embedded message contains `<media:audio>` or audio media attachment metadata, redirect to `scripts/openclaw_embedded_media_redirect_cli.py --message-text "<embedded prompt>"` instead of allowing ad-hoc direct STT `exec`.
    - Add runtime proof/error markers (`openclaw_voice_dispatch_path_select` / `openclaw_voice_dispatch_path_error`) with `selectedPath=wrapper_cli_bridge` and `intendedPath=wrapper_cli_bridge`.
  - Priority 2: embedded planner tool-policy/prompt template (fallback only if dispatcher guard is not patchable).
    - Enforce wrapper-first for audio media and block direct Deepgram STT `exec` generation.
    - Lower confidence than a dispatcher guard because prompt/policy rules can drift.
- Applied local runtime hotfix (MSI/OpenClaw npm install, bundled `pi-embedded`):
  - Patched `runBeforeToolCallHook(...)` in both installed `pi-embedded-*.js` bundles to intercept direct Deepgram STT `exec`/`bash` calls when the latest `chat.history` user message contains embedded audio media markup.
  - The guard rewrites the `exec` command to the repo redirect shim (`scripts/openclaw_embedded_media_redirect_cli.py --message-file <tmp>`) and emits runtime proof marker `openclaw_voice_dispatch_path_select` with `selectedPath=wrapper_cli_bridge`.
  - The rewritten PowerShell command now also sets UTF-8 console/input/output encoding and `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8` before invoking the Python shim to reduce Windows shell mojibake risk.
  - If shim/python path cannot be resolved, it emits `openclaw_voice_dispatch_path_error` (`intendedPath=wrapper_cli_bridge`) and blocks with a safe diagnostic error (no silent direct Deepgram fallback).
  - Optional runtime env overrides for local paths:
    - `OPENCLAW_AUDIO_REDIRECT_SHIM`
    - `OPENCLAW_AUDIO_REDIRECT_PY`
    - `OPENCLAW_AUDIO_REDIRECT_REPO`

One-shot live proof (copy/paste, PowerShell):
```powershell
cd D:\openclaw_bot\agent-second-brain
$env:TELEGRAM_STT_MULTIPASS='1'
$env:TELEGRAM_STT_MULTIPASS_LANGS='auto,ru,en'
$env:TELEGRAM_STT_MIXED_HEURISTIC='1'
powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1
$log='.\artifacts\openclaw_live_voice_path_proof.jsonl'
openclaw logs --follow --json --plain | Tee-Object -FilePath $log
# send one mixed RU+EN Telegram voice/audio message through wrapper-first embedded path, then stop follow
Select-String -Path $log -Pattern 'openclaw_voice_dispatch_path_select','openclaw_voice_dispatch_path_error','telegram_voice_pipeline','stt_multipass_'
$s=(Get-ChildItem "$env:USERPROFILE\.openclaw\agents\main\sessions" -Filter *.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
Get-Content $s -Tail 250 | Select-String -Pattern 'toolCall','exec','deepgram','openclaw_voice_dispatch_path_select','openclaw_voice_dispatch_path_error','telegram_voice_pipeline'
.\.venv\Scripts\python.exe .\scripts\openclaw_live_voice_path_verdict.py --log-capture $log --session-jsonl $s
```

Verdict helper:
- `scripts/openclaw_live_voice_path_verdict.py` summarizes evidence from log capture + session JSONL and prints:
  - `LIVE_PATH_CONFIRMED_BRIDGE`
  - `LIVE_PATH_BYPASS_EXEC_DEEPGRAM`
  - `INCONCLUSIVE`
- Temporary repo hardening workaround (no core patch):
  - Keep redirect-shim-first workflow (`scripts/openclaw_embedded_media_redirect_cli.py` -> wrapper -> adapter -> bridge).
  - If `openclaw_live_voice_path_verdict.py` returns `LIVE_PATH_BYPASS_EXEC_DEEPGRAM`, treat the response as bypassed/unsupported for bridge verification and return an explicit diagnostic message to the operator/user instead of trusting transcript quality.
  - Suggested safe diagnostic text:
    - `Live audio request bypassed the bridge path (direct exec STT was used). Please retry with the wrapper-first embedded media path.`

Single poller reminder:
- Keep OpenClaw as the only Telegram poller in production.
- Do not run `python -m d_brain` polling alongside `openclaw gateway`.

## OpenClaw E2E Smoke (No Telegram Polling / No Network)
Run from repo root:
- `python scripts/openclaw_e2e_smoke.py`

Output format:
- JSONL (one JSON object per case).
- Each line includes `case`, `ok`, `route`, `bridge_handler_used`, ingestion/outbound fields, and a safe `error` string (no raw traceback dump).

PASS / FAIL reading:
- `PASS`: line has `"ok": true` and `"error": null`.
- `FAIL`: line has `"ok": false`; inspect `error`, `route`, `action_called`, and ingestion/outbound fields to see where routing or fallback behavior diverged.

Scope covered (MVP):
- Command bridge E2E (`/help`, `/plan add`, `/plan list`)
- Voice bridge E2E (RU reflection voice -> text/TTS reply, transcript-only warning)
- Job path E2E (`heartbeat_summary`, `daily_digest`) with runtime sender mock
- Non-fatal ingestion fallback (`ingestion` exception swallowed)
- Non-fatal indexer fallback (`indexed=deferred`)

## Model Routing Policy Smoke (No Telegram Polling)
Run from repo root:
- `python scripts/model_routing_smoke.py`

Expected behavior:
- `/status` uses `deterministic` route (or OpenAI if configured that way).
- Voice tutor/reflection reasoning routes to OpenAI.
- Heartbeat and cron summary routes default to local.
- Local-unavailable utility fallback can route to OpenAI when enabled.
- OpenAI-unavailable main reasoning fails with `reasoning_provider_unavailable` unless explicit OpenAI->local fallback is enabled.

Relevant env overrides:
- `MODEL_ROUTE_MAIN_REASONING_PROVIDER`
- `MODEL_ROUTE_VOICE_REASONING_PROVIDER`
- `MODEL_ROUTE_HEARTBEAT_PROVIDER`
- `MODEL_ROUTE_CRON_SUMMARY_PROVIDER`
- `MODEL_ROUTE_LIGHT_CLASSIFICATION_PROVIDER`
- `MODEL_ROUTE_COMMAND_STATUS_PROVIDER`
- `MODEL_ROUTE_ALLOW_LOCAL_TO_OPENAI_FALLBACK`
- `MODEL_ROUTE_ALLOW_OPENAI_TO_LOCAL_FALLBACK`
- `MODEL_ROUTE_FORCE_OPENAI_UNAVAILABLE`
- `MODEL_ROUTE_FORCE_LOCAL_UNAVAILABLE`
- `OPENAI_API_KEY`

## Heartbeat/Cron Smokes (OpenClaw-only)
Run from repo root:
- `python scripts/openclaw_heartbeat_smoke.py`
- `python scripts/openclaw_cron_smoke.py`
- `python scripts/openclaw_scheduler_bridge_smoke.py`
- `python scripts/openclaw_scheduler_config_smoke.py`
- `python scripts/openclaw_digest_smoke.py`
- `python scripts/openclaw_digest_target_smoke.py`
- `python scripts/openclaw_jobs_smoke.py`
- `python scripts/memory_ingestion_smoke.py`

Scheduler control commands:
- `/hb interval <minutes>` (range `5..240`)
- `/hb on` / `/hb off`
- `/digest on` / `/digest off`
- `/digest time HH:MM`
- `/digest now` / `/digest preview` / `/digest status`
- `/digest target here|show|on|off|clear|test`
- `/cron sync`

Expected behavior:
- Main chat and voice reasoning stay on OpenAI routes (no silent switch to local).
- Heartbeat and cron utility tasks route to local by default.
- If local is unavailable and fallback is enabled, heartbeat/cron utility tasks can route to OpenAI with `fallback_used=true`.
- `/hb now`, `/hb status`, `/cron list`, and `/cron run <job>` are handled through the OpenClaw bridge command path.
- `/hb now` and cron `heartbeat.tick` run the same heartbeat runner path (single execution path).
- `digest.daily` is scheduler-wired and uses the cron utility provider role.
- Scheduled digest delivery requires target binding via `/digest target here`.
- Delivery states: `sent`, `no_target`, `failed`, `deferred`.
- `/digest target show` returns a short "not configured" message when no mapping exists.
- Delivery state meaning:
  - `sent`: outbound send succeeded to mapped target.
  - `no_target`: no enabled digest target mapping for the user.
  - `failed`: outbound adapter attempted send and returned an error.
  - `deferred`: runtime outbound sender is unavailable (stub fallback).
- Adapter behavior: `scheduled_openclaw` when runtime API is wired, otherwise `stub_fallback`.
- Production transport reminder: keep OpenClaw as the only Telegram transport (no aiogram polling).

Outbound smoke expectations (`openclaw_digest_target_smoke.py`):
- `case=no_target`: `/cron run digest.daily` and `/digest status` report `delivery=no_target`.
- `case=text_only`: unified outbound `send_text(...)` returns `delivery_state=sent` with a runtime sender stub.
- `case=runtime_sent`: runtime sender is registered, `/cron run digest.daily` reports `delivery=sent`, and `/digest status` shows `delivery=sent`.
- `case=tts_requested_but_empty`: unified outbound `send_tts(...)` falls back to text and returns a safe structured result.

Runtime sender wiring note:
- Unified outbound defaults to a safe `deferred` state when no runtime sender is registered.
- OpenClaw runtime integration should register a sender via `d_brain.integrations.openclaw_outbound.register_runtime_sender(...)`.
- Registration is process-local and must be re-applied on runtime startup.

Transport-agnostic jobs smoke expectations (`openclaw_jobs_smoke.py`):
- `case=heartbeat_no_target`: safe skip with outbound `delivery_state=no_target`.
- `case=digest_dry_run`: digest payload is generated with safe `dry_run` deferred outbound result.
- `case=plan_reminder_no_items`: no crash; job returns `skipped_reason=no_items`.
- `case=outbound_fail_fallback`: outbound sender failure returns safe `delivery_state=failed` without uncaught exceptions.

Memory ingestion smoke expectations (`memory_ingestion_smoke.py`):
- `case=text_message_basic`: normalized text event is stored with `ok=true`.
- `case=voice_transcript_basic`: voice transcript event is stored with `ok=true`.
- `case=job_digest_ingest`: job summary ingestion is stored with `ok=true`.
- `case=empty_content_skip`: empty content returns `skipped_reason=empty_content`.
- `case=indexer_unavailable_fallback`: record is stored and indexing is `deferred` without crashing.

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

## Internal Skill Creation / Update (Workflow)
Use this when adding or changing skills (OpenClaw-first workflow).

Steps:
1. Confirm the skill request and scope (trigger conditions, expected outputs, compatibility constraints).
2. Use the `skill-creator` process to structure the skill work.
3. Follow `docs/skill-contract.md` for required structure/docs/smokes/examples/rollback notes.
4. Implement or update the skill (`vault/.claude/skills/<skill-name>/...`) with a lean `SKILL.md` and optional `references/` and `scripts/`.
5. Add or update smoke checks (prefer no-network) and document commands + expected results in this runbook.
6. Update docs affected by behavior/workflow changes per the Documentation Contract.
7. Record any failures/corrections/workarounds in `docs/learnings.md`.

Notes:
- If `self-improving-agent` is not available in the active skill registry, use `docs/learnings.md` as the fallback self-improvement mechanism.
- Keep OpenClaw as the only Telegram transport in production; aiogram polling remains dev-only.

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
### Fast Triage (OpenClaw-first)
Run from repo root (`D:\openclaw_bot\agent-second-brain`):
- Quick health (bridge command via CLI):
  - `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/health"`
- Quick health JSON (automation-friendly):
  - `.\.venv\Scripts\python.exe scripts\ux_cli.py health --json`
- Gateway diagnostics (no network calls):
  - `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`
- Fallback stability smoke:
  - `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`

If something fails:
- `409 conflict`: stop duplicate pollers, keep OpenClaw as the only Telegram transport.
  - `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
  - `Stop-Process -Name python -Force`
  - `Stop-Process -Name openclaw -Force`
  - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`
- `TTS empty` / voice reply lost audio:
  - `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`
  - Check logs for `tts_empty_output` and confirm text fallback is returned.
- Command handler exception:
  - `.\.venv\Scripts\python.exe scripts\ux_cli.py command --user-id 123 --text "/diag"`
  - `.\.venv\Scripts\python.exe scripts\openclaw_e2e_smoke.py`
- Bridge import error:
  - `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`
  - `.\.venv\Scripts\python.exe -m compileall src\d_brain\integrations\openclaw_bridge.py vault\.claude\skills\openclaw-main\adapter.py`

### OpenClaw Stopped Responding
Expected result:
- Port `18789` listens again and `ux_cli.py diag` reports `mode: openclaw`.

Commands (PowerShell, from repo root):
- `powershell -ExecutionPolicy Bypass -File .\ops\status-openclaw.ps1`
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
- `powershell -ExecutionPolicy Bypass -File .\ops\status-openclaw.ps1`

### Telegram 409 Conflict
Expected result:
- Duplicate poller processes stopped; only OpenClaw gateway remains.

Commands:
- `powershell -ExecutionPolicy Bypass -File .\ops\kill-telegram-conflicts.ps1 -StopAllOpenClawGateways`
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
- `.\.venv\Scripts\python.exe scripts\ux_cli.py diag`

Quick recovery (manual, PowerShell):
- `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
- `Stop-Process -Name python -Force`
- `Stop-Process -Name openclaw -Force`
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`

### openclaw Command Not Found
Expected result:
- `openclaw` resolves in current terminal session, or you get a clear install/PATH hint.

Commands:
- `powershell -ExecutionPolicy Bypass -File .\ops\fix-path-node-openclaw.ps1`
- `Get-Command openclaw -ErrorAction SilentlyContinue`
- `powershell -ExecutionPolicy Bypass -File .\ops\status-openclaw.ps1`

### node/npm Not Found In New Terminal
Expected result:
- `node` and `npm` are available in current shell; permanent PATH command is shown.

Commands:
- `powershell -ExecutionPolicy Bypass -File .\ops\fix-path-node-openclaw.ps1`
- `Get-Command node -ErrorAction SilentlyContinue`
- `Get-Command npm -ErrorAction SilentlyContinue`

### TTS Empty-File Fallback
Expected result:
- Fallback smoke passes and voice path returns text fallback instead of crashing.

Commands:
- `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_e2e_smoke.py`
- `.\.venv\Scripts\python.exe scripts\ux_cli.py diag`

Behavior note:
- If generated audio is missing/empty, the adapter returns text fallback only (no repeated media send attempts).
- Audio payload checks log `audio_intent`, `audio_path`, file existence/size, and `fallback_reason`.
- Common `fallback_reason` values include:
  - `tts_empty_output`
  - `tts_tts_failed` / `tts_tts_timeout` (provider generation failure/timeout)
  - `audio_path_missing_or_empty`
  - `audio_path_unreadable`

### Transcript-Only Warning (Voice/Text)
Expected result:
- Transcript-looking text without real media returns a short warning and does not override real voice media.

Quick check:
- `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`

### Duplicate Messages / Replayed Updates
Expected result:
- Replayed command/voice updates in a short window are skipped once and do not create duplicate side effects.

Quick check:
- `.\.venv\Scripts\python.exe scripts\openclaw_duplicate_guard_smoke.py`

- OpenClaw Recovery (PowerShell, quick actions):
  - Stop likely duplicate pollers:
    - `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
    - `Stop-Process -Name python -Force`
    - `Stop-Process -Name openclaw -Force`
  - Start OpenClaw stack again:
    - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`
  - Stop OpenClaw stack:
    - `powershell -ExecutionPolicy Bypass -File scripts/stop_openclaw_stack.ps1`
- `409 Conflict` (`getUpdates`) / duplicate poller:
  - Cause: two Telegram pollers are running (OpenClaw + local aiogram).
  - Fix: keep OpenClaw as the only Telegram transport; ensure `D_BRAIN_TELEGRAM_DISABLED=1`.
  - Recovery commands:
    - `Stop-Process -Name python -Force`
    - `Stop-Process -Name openclaw -Force`
    - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`
- `openclaw` not in PATH:
  - Check: `Get-Command openclaw -ErrorAction SilentlyContinue`
  - Use the local bootstrap script (it prepares PATH for the shell):
    - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`
- Empty TTS file / missing voice payload:
  - Verify fallback behavior:
    - `python scripts/openclaw_fallback_smoke.py`
  - Voice replies should fall back to text; if not, check `tts_empty_output` diagnostics in logs.
- Gateway already running / port busy (`18789`):
  - Check port owner:
    - `Get-NetTCPConnection -LocalPort 18789 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess`
  - Check process:
    - `Get-Process -Id <PID>`
  - Stop and restart:
    - `Stop-Process -Id <PID> -Force`
    - `powershell -ExecutionPolicy Bypass -File scripts/start_openclaw_stack.ps1`

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
   Behavior:
   - If the TTS output file is empty or missing, Telegram reply falls back to plain text.
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

## Final Prod Architecture (Short)
- OpenClaw handles Telegram transport and polling in production.
- `d_brain` provides bridge dispatch, business logic, sidecar actions, and services.
- OpenAI remains the main reasoning provider; local providers remain utility/search/cron providers.
- aiogram polling is dev-only and must not be enabled in production OpenClaw-first runs.

## Safe Restart + Quick Verify (Windows PowerShell)
Safe restart:
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`

Quick verify (2-3 commands):
- `.\.venv\Scripts\python.exe scripts\prod_readiness_check.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_command_dispatch_smoke.py --user-id 123 --chat-id 123 --plan-title "Smoke plan"`
- `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`

## Production Start (OpenClaw Only)
Run from repo root (`D:\openclaw_bot\agent-second-brain`):
- `powershell -ExecutionPolicy Bypass -File .\ops\start-openclaw.ps1`
- Verify OpenClaw-only transport mode:
  - `.\.venv\Scripts\python.exe scripts\prod_readiness_check.py`
  - `.\.venv\Scripts\python.exe scripts\no_polling_when_disabled_check.py`
- Run RC smoke suite (no Telegram polling):
  - `.\.venv\Scripts\python.exe scripts\openclaw_rc_smoke.py`
- Import-path sanity (optional, before live Telegram voice tests):
  - `openclaw logs --tail 200` and look for:
    - `openclaw_bridge_runtime_module_path`
    - `openclaw_bridge_voice_fix_loaded`
    - `openclaw_bridge_runtime_dispatch_entry` (after one voice message)

## v1.0 Cutover Execution (Production Sign-off)
Use `docs/cutover-checklist.md` as the canonical checklist for final cutover execution and sign-off evidence.

Minimum local verification set (before manual Telegram checks):
- `.\.venv\Scripts\python.exe scripts\prod_readiness_check.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_rc_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_diag_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`

Manual Telegram acceptance (OpenClaw transport path) is still required for final production sign-off:
- Commands: `/help`, `/status`, `/plan list`, `/plan add ...`, `/diag`, `/ping`, `/version`
- Voice: RU voice note, transcript-only warning, valid TTS media send, empty/invalid TTS fallback
- Use `docs/live-telegram-acceptance-template.md` for operator step-by-step marking.
- Capture gateway/channel/log evidence before manual checks:
  - `powershell -ExecutionPolicy Bypass -File .\ops\capture-live-signoff.ps1`

Windows CLI note (verification only):
- If CLI command output fails with `UnicodeEncodeError` in `cp1251`, run:
  - `chcp 65001`
  - `$env:PYTHONIOENCODING='utf-8'`

Final GO gating rule:
- `GO` is allowed only when all three are verified on the live OpenClaw Telegram transport path:
  - live Telegram channel status via OpenClaw gateway
  - manual command acceptance
  - manual voice acceptance
- Otherwise return `GO WITH KNOWN LIMITATIONS` or `NO-GO`.

## Recovery After Conflict / Timeout
- `409 getUpdates` conflict or duplicate pollers:
  - `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
  - `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`
- Bridge/sidecar timeout degradation observed in `/diag`:
  - `.\.venv\Scripts\python.exe scripts\openclaw_diag_smoke.py`
  - `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`
  - `.\.venv\Scripts\python.exe scripts\openclaw_rc_smoke.py`
 - For full cutover recovery/rollback sequence, use `docs/cutover-checklist.md`.

## Quick Health Checklist (RC)
- `/diag` returns transport/prefs/sidecar/uptime summary.
- `/diag full` shows commit hash, timeout values, error counters, and recent sanitized errors (no secrets).
- `scripts/prod_readiness_check.py` returns `PASS` or `WARN` only (no `FAIL`).
- `scripts/openclaw_rc_smoke.py` returns summary `PASS`.

## Known Degraded Modes (Expected Safe Fallbacks)
- TTS provider unavailable / timeout / empty output:
  - Voice reply falls back to text, bridge stays responsive.
- STT timeout or provider error:
  - Short RU error is returned; process does not crash.
- Sidecar timeout/error for bridge plan handlers:
  - Short RU degraded response is returned; structured degraded log is emitted.
- Runtime sender unavailable:
  - Unified outbound may return `deferred` instead of `sent` until runtime sender is registered.

## Troubleshooting: Telegram TTS Empty Media (`file must be non-empty`)
- Symptom:
  - `telegram sendAudio/sendVoice failed ... 400 Bad Request: file must be non-empty`
- Cause:
  - Empty TTS output (empty bytes or zero-size file path) reached the transport media send path.
- Current behavior (guarded):
  - The OpenClaw adapter applies an early media payload guard, clears `audio_intent`, logs `reason=empty_tts_output`, and returns text fallback instead of attempting media send.
- If it repeats, check in order:
  1. Confirm `tool=tts` (or bridge TTS diagnostics) appears in logs for the message.
  2. Check audio payload/file size (`audio_bytes` length or `audio_path` file size).
  3. Confirm media send was skipped and text fallback was returned (no `sendAudio/sendVoice` attempt for that response).
  4. Check for regression in the adapter/channel path if a media send is still attempted with empty payload.

## Troubleshooting: Telegram Voice Note Falls Back to Auto-Transcript Too Early
- Symptom:
  - Short/medium Telegram voice notes (`message.voice`) often produce poor transcript text, `EMPTY_TRANSCRIPT`, or a fallback path that ignores the real voice file.
- Expected behavior (current bridge):
  - Source priority is `voice` -> `audio` -> audio `document` -> transcript/text fallback.
  - If `message.voice.file_id` exists, the bridge should attempt file download/STT before treating transcript text as primary.
  - Voice-note failures should return a retry message (no ".ogg/.m4a file" request for normal voice notes).
  - Final voice-note safety override blocks generic "resend as file/.ogg/.m4a" UX on all `message.voice` fallback paths (download missing/fail, STT empty/error, malformed shape, transcript-only auto fallback).
- Check logs (structured, no secrets):
  - `event=telegram_stt_source_select`
  - `event=telegram_voice_ingest`
  - `event=telegram_voice_pipeline`
  - Key fields: `requestId`, `userIdHash`, `messageKind`, `telegramFileIdPresent`, `telegramFileUniqueIdPresent`, `downloaderName`, `downloaderPath`, `mediaBytesPresent`, `mediaBytesLen`, `mediaPathPresent`, `mediaPathExists`, `mediaPathSize`, `transcriptLen`, `transcriptLooksAuto`, `finalInputSource`, `downloadAttempted`, `downloadOk`, `sttAttempted`, `sttOk`, `finalOutcome`, `fallbackReason`, `responseMode`
  - Additional fields for live verification: `isVoiceNote`, `sttProvider`, `sttModel`
  - If `TELEGRAM_STT_NORMALIZE_AUDIO=1`, check `telegram_voice_pipeline` for ffmpeg conversion stages and `pipelineErrorCode` (`ffmpeg_missing`, `audio_conversion_failed`) when normalization fails.
  - For mixed RU+EN speech quality issues (non-tutor), test:
    - `TELEGRAM_STT_MULTIPASS=1`
    - `TELEGRAM_STT_MULTIPASS_LANGS=auto,ru,en`
    - `TELEGRAM_STT_MIXED_HEURISTIC=1`
    - optional `TELEGRAM_STT_NORMALIZE_AUDIO=1` (with `ffmpeg`)
  - Confirm `telegram_voice_pipeline` includes `stt_multipass_*` stages and note `selectedLang` / `selectionReason`.
- Common interpretations:
  - `downloadAttempted=false` + `telegramFileIdPresent=true`: no downloader was available in the message path (`voice_download_not_attempted`).
  - `downloadAttempted=true` + `downloadOk=false`: voice file download failed (`voice_download_failed`).
  - `downloadOk=true` + `sttAttempted=true` + `sttOk=false`: STT failed on the downloaded voice (`stt_error`) or returned empty text (`stt_empty` / `empty_transcript_voice_note`).
  - `sttAttempted=true` + `sttResultLen=0`: empty transcript from voice STT (`empty_transcript_voice_note`).
  - `finalInputSource=transcript` + `finalOutcome=fallback_transcript`: bridge intentionally used transcript fallback instead of media STT (inspect `fallbackReason` and downloader/media fields).
- Stable fallback reason taxonomy (bridge diagnostics / structured logs):
  - `voice_download_not_attempted`
  - `voice_download_failed`
  - `media_declared_without_bytes`
  - `stt_error`
  - `stt_empty`
  - `empty_transcript_voice_note`
  - `transcript_only_auto`
  - `transcript_only_no_media`
  - `no_voice_content`
  - `unsupported_media_shape`
- Smoke check:
  - `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py`
- Live debug summary examples:
  - `.\.venv\Scripts\python.exe scripts\openclaw_voice_log_summary.py --file .\openclaw.log --lines 300`
  - `.\.venv\Scripts\python.exe scripts\openclaw_voice_log_summary.py --lines 300 --jsonl` (uses `openclaw logs --tail`)

## Safe Restart (Prod)
Use this sequence when the gateway is stuck or `409 getUpdates` conflicts are suspected:
- `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
- `Stop-Process -Name python -Force`
- `Stop-Process -Name openclaw -Force`
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
- `powershell -ExecutionPolicy Bypass -File .\ops\status-openclaw.ps1`

Optional live debugging:
- `openclaw logs --follow`


## Troubleshooting: Windows `gateway/ws` Pretty-Log Mojibake
- Symptom:
  - OpenClaw `gateway/ws` pretty `req/res` lines in Windows logs show mojibake-like token sequences instead of directional/status glyphs.
  - File logs may contain ANSI escapes (`\u001b[...m`) and unicode decorative symbols in `gateway/ws` entries.
- Cause:
  - The `gateway/ws` pretty formatter path writes colorized ANSI plus unicode strings into the logger/file path, which is fragile in some Windows decoding/rendering paths.
- Temporary local runtime fix (installed OpenClaw bundle, outside repo source):
  - Patch installed `push-apns-*.js` bundles under `C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\` to use ASCII-safe `gateway/ws` markers (`<-`, `->`, `<->`, `OK`, `ERR`, `...`) and sanitized file-log writes (`stripAnsi`, `normalizeLogForWindows`) while preserving `consoleMessage` for console pretty output.
- Verify patch syntax:
  - `C:\Program Files\nodejs\node.exe --check C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\push-apns-BRGDsNym.js`
  - `C:\Program Files\nodejs\node.exe --check C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\push-apns-A3yh2vIh.js`
- Verify new file-log output after restarting OpenClaw and triggering a Control UI request:
  - `Select-String -Path "C:\Users\User\AppData\Local\Temp\openclaw\openclaw-2026-02-25.log" -Pattern 'gateway/ws','agent.identity.get' | Select-Object -Last 20`
  - Confirm new `gateway/ws` pretty `req/res` entries do not contain `\u001b[` and use ASCII-safe markers instead of mojibake/decorative glyphs.
- Note:
  - Historical log lines remain unchanged; only new entries after restart reflect the patch.

## Troubleshooting: Voice-Call STT RU Speech Becomes Latin Transliteration (`priyat kagula`-style)
- Symptom:
  - In OpenClaw `voice-call` live calls, Russian or mixed RU/EN speech is transcribed as English-phonetic Latin transliteration (for example, RU text appears in Latin), while EN-only speech is mostly correct.
- Active branch affected (current diagnosis):
  - Twilio Media Streams -> `voice-call` streaming STT -> OpenAI Realtime transcription (`extensions/voice-call/src/providers/stt-openai-realtime.ts` in the installed OpenClaw runtime extension).
- Root cause (patched in local installed runtime extension):
  - The realtime `transcription_session.update` payload sent only the STT model and omitted explicit `input_audio_transcription.language` and a multilingual transcription hint/prompt, which allowed an English-biased decode path for telephony audio.
- Current local runtime patch behavior (installed extension, outside repo source):
  - `voice-call` streaming config now supports:
    - `streaming.sttLanguage` (default `ru`; use `auto` to omit the hint)
    - `streaming.sttPrompt` (default bilingual anti-transliteration prompt)
  - OpenAI Realtime `transcription_session.update` now passes `model` plus `language` (unless `auto`) and `prompt`.
  - Safe diagnostics now log:
    - selected STT provider/model/language/prompt-set
    - short final transcript preview from Realtime STT
    - short raw transcript preview before agent/manager processing (`hasCyrillic=true|false`)
- Verify config and transcript path (PowerShell):
  - Restart OpenClaw:
    - `cd D:\openclaw_bot\agent-second-brain`
    - `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
  - Tail logs:
    - `& "$env:APPDATA\npm\openclaw.cmd" logs --follow --plain | Tee-Object -FilePath .\artifacts\voicecall_stt_check.log`
  - Filter diagnostic lines:
    - `Select-String -Path .\artifacts\voicecall_stt_check.log -Pattern 'Streaming STT config','session.update stt_provider','Transcript final len','Transcript raw provider'`
- Voice-call validation checklist (manual, live):
  - RU-only test:
    - say a short Russian phrase (for example, a greeting + a simple question)
    - expected: transcript preview contains Cyrillic (`hasCyrillic=true`)
  - EN-only test:
    - say a short English phrase
    - expected: EN transcript remains correct (`hasCyrillic=false`)
  - Mixed RU+EN test:
    - say one sentence mixing Russian and English words
    - expected: Russian words remain Cyrillic and English words remain Latin (no RU transliteration into Latin)
- Notes:
  - This session patched only the active streaming STT branch used by the diagnosed voice-call path.
  - Other provider-native STT paths still contain English defaults and may need separate fixes if you are not using streaming:
    - Twilio `<Gather ... language="en-US">`
    - Telnyx `transcription_start language: "en"`
    - Plivo speech XML defaults `en-US`


## Embedded Voice Bridge Runtime Fix (2026-02-25)\nWhen openclaw_embedded_media_redirect_cli.py returns ridge_dispatch_unavailable with ridge_import_or_runtime_failed, check in order:\n1. Python deps present in wrapper runtime: python -m pip install -r requirements.txt\n2. Wrapper adapter import dataclass crash fix present in openclaw_live_voice_bridge_cli.py (sys.modules[module_name]=module before exec_module).\n3. Session directory exists: ault/.sessions\n4. Retry wrapper CLI directly with a real media-attached prompt.\nExpected proof chain on success:\n- redirect: selectedPath=wrapper_cli_bridge\n- wrapper: selectedPath=d_brain_openclaw_bridge\n- adapter response contains text + diagnostics (stt_language, stt_multipass).
