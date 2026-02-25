# v1.0 Cutover Checklist (OpenClaw-first Production)

Purpose: final production cutover verification for the OpenClaw-first runtime where OpenClaw is the only Telegram transport and `d_brain` provides bridge/logic/services.

## Architecture Guardrails (Must Hold)
- OpenClaw = only Telegram transport in production.
- `d_brain` = logic / bridge / services.
- aiogram polling = dev-only and disabled in production (`telegram_disabled=true`).
- No bridge API compatibility breaks during cutover.

## Start / Stop Commands (Windows PowerShell)
Start:
- `powershell -ExecutionPolicy Bypass -File .\ops\start-openclaw.ps1`

Stop:
- `powershell -ExecutionPolicy Bypass -File .\ops\stop-openclaw.ps1`

Restart:
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`

Status:
- `powershell -ExecutionPolicy Bypass -File .\ops\status-openclaw.ps1`

## Health Checks (Required)
Offline / local:
- `.\.venv\Scripts\python.exe scripts\prod_readiness_check.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_rc_smoke.py`

Bridge command smoke (no Telegram polling):
- `.\.venv\Scripts\python.exe scripts\openclaw_command_dispatch_smoke.py --user-id 123 --chat-id 123 --plan-title "Smoke plan"`
- `.\.venv\Scripts\python.exe scripts\openclaw_diag_smoke.py`

Voice / fallback smoke (no Telegram polling):
- `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`
- `.\.venv\Scripts\python.exe scripts\voice_media_preference_check.py`

## Production Cutover Verification (Manual + Observed)
### Transport Ownership / Polling
- Confirm `telegram_disabled=true` (env or effective config) for `d_brain`.
- Confirm no second Telegram poller (`python -m d_brain`) is running in production.
- Confirm OpenClaw gateway process is running and listening.
- Confirm Telegram channel status is OK in OpenClaw runtime/UI/CLI.

### Bridge Command Acceptance (Telegram path)
Run from Telegram (OpenClaw transport):
- `/help`
- `/status`
- `/plan list`
- `/plan add Test live`
- `/diag`
- `/ping`
- `/version`

Expected:
- Responses return via OpenClaw gateway.
- Bridge command behavior matches CLI/no-polling smoke behavior.
- No crash and no duplicate side effects.

### Voice Acceptance (Telegram path)
Required manual scenarios:
- RU voice note -> STT language policy `ru` -> correct reply.
- Transcript-only input without media -> short RU warning.
- TTS valid media -> `sendVoice` or `sendAudio` sends media.
- Empty/invalid TTS media -> text fallback (non-fatal).

Confirm:
- Media > transcript priority.
- `file must be non-empty` does not crash the flow.
- sendAudio/sendVoice failure path degrades safely to text.

## Recover Steps
### 409 Conflict / Duplicate Poller
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`
- `.\.venv\Scripts\python.exe scripts\openclaw_prod_diag.py`

Manual recovery:
- `Get-Process -Name openclaw, python -ErrorAction SilentlyContinue`
- `Stop-Process -Name python -Force`
- `Stop-Process -Name openclaw -Force`
- `powershell -ExecutionPolicy Bypass -File .\ops\restart-openclaw.ps1`

### Timeout / Degraded Behavior Checks
- `.\.venv\Scripts\python.exe scripts\openclaw_diag_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`
- `.\.venv\Scripts\python.exe scripts\openclaw_rc_smoke.py`

## Rollback (Safe)
Goal: revert production transport to a known working OpenClaw configuration without enabling aiogram polling in prod.

Steps:
1. Stop and restart OpenClaw using `ops` scripts.
2. Revert only the deployment bundle/config to the last known-good OpenClaw-first release.
3. Re-run:
   - `scripts\prod_readiness_check.py`
   - `scripts\openclaw_prod_diag.py`
   - `scripts\openclaw_rc_smoke.py`

Do not:
- Enable aiogram polling in production as a rollback shortcut.

## Known Degraded But Alive (Acceptable Signs)
- TTS unavailable / timeout / empty media -> text fallback reply returned.
- STT timeout/provider error -> short RU error returned; process remains alive.
- Sidecar timeout -> short degraded response + structured diagnostics; gateway remains alive.
- Runtime sender unavailable -> outbound may be `deferred` (not a crash).

## Sign-off Evidence Record (Fill Per Cutover)
- Date:
- Operator:
- Environment:
- OpenClaw gateway process:
- Telegram channel status:
- Poller conflict status:
- Command acceptance result:
- Voice acceptance result:
- RC smoke summary:
- Verdict: `GO` / `GO WITH KNOWN LIMITATIONS` / `NO-GO`
- Notes:

## Live Telegram Acceptance Evidence (Required for Final Sign-off)
- Timestamp:
- Operator:
- Gateway status snapshot:
- Channel status snapshot:
- Command test results:
- Voice test results:
- Fallback result (TTS empty/error -> text fallback, non-fatal):
- Final pass/fail:
- Evidence file path (`artifacts/signoff/live-signoff-<timestamp>.md`):

## Final GO Gating Rule (Required)
Final verdict can be `GO` only if all are verified on the live OpenClaw Telegram transport path:
- Telegram live channel status verified via OpenClaw gateway
- Manual command acceptance verified
- Manual voice acceptance verified

If any of the above is missing:
- Use `GO WITH KNOWN LIMITATIONS` or `NO-GO`
- List the missing/failed verification items explicitly

