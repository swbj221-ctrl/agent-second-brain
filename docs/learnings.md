# Learnings Log (Self-Improvement)

Purpose: capture repeated failures, user corrections, and proven fixes so future sessions avoid the same mistakes.

## Policy
- Write in English only.
- Keep entries short and operational.
- Prefer one entry per confirmed issue/fix pattern.
- Update this file during the session when the issue is discovered or fixed (do not defer to close-session only).

## When to Write an Entry (Required)
- A command, script, or operation fails and the root cause is identified.
- The user corrects the agent (requirements, assumptions, behavior, or workflow).
- A workaround or fix is found and used successfully.
- A recurring error is eliminated or prevented.

## Entry Format (Required)
Use this template for every entry:

```md
## YYYY-MM-DD HH:MM (local)
- Area:
- Symptom:
- Root cause:
- Fix:
- Prevention:
- Verification:
- References:
```

## Example Entry
```md
## 2026-02-24 21:10 (local)
- Area: MSI / summarize CLI
- Symptom: URL summarize command fails behind corporate TLS inspection.
- Root cause: Node process does not trust the corporate root CA.
- Fix: Install corporate root CA and set `NODE_EXTRA_CA_CERTS` for Node-based summarize runs.
- Prevention: Keep the TLS note in `docs/runbook.md` and run the summarize smoke command after workstation changes.
- Verification: `summarize "https://example.com" --extract --plain` returns text output.
- References: `docs/runbook.md`, `docs/progress.md`
```

## Current Session Notes
- No new entries yet for this file creation step.

## 2026-02-24 21:35 (local)
- Area: Windows CLI verification (`scripts/ux_cli.py`)
- Symptom: `/plan list` verification command failed with `UnicodeEncodeError` in `cp1251`.
- Root cause: Windows console encoding could not print emoji characters in plan titles.
- Fix: Run verification commands with UTF-8 console/output (`chcp 65001` and `PYTHONIOENCODING=utf-8`).
- Prevention: Use UTF-8 console settings for CLI verification commands that may print user content.
- Verification: `/plan list`, `/plan add Тест cutover`, `/diag`, `/ping`, `/version` printed successfully after UTF-8 workaround.
- References: `docs/runbook.md`, `docs/cutover-checklist.md`
## 2026-02-25 01:25 (local)
- Area: Telegram voice/TTS delivery
- Symptom: `sendAudio/sendVoice -> 400 Bad Request: file must be non-empty`
- Root cause: Empty TTS output was not centrally validated before the Telegram media send path.
- Fix: Added an early guard (bytes/path existence + size check) before media send response handoff and forced text fallback when TTS output is empty.
- Prevention: Keep one central media payload validation guard before transport send and preserve smoke coverage for empty/non-empty TTS output paths.
- Verification: `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py` PASS (`tts_empty_nonfatal`, `adapter_empty_tts_output_guard`, `tts_valid_nonempty_media_path`).
- References: `vault/.claude/skills/openclaw-main/adapter.py`, `scripts/openclaw_fallback_smoke.py`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-25 01:40 (local)
- Area: Windows OpenClaw startup script (`scripts/start_openclaw_stack.ps1`)
- Symptom: Foreground startup failed with `""node"" is not recognized...` while `openclaw gateway` was launched from the script.
- Root cause: Process PATH/command resolution was not validated explicitly, and quoted PATH segments could break downstream command invocation in the OpenClaw CLI wrapper.
- Fix: Normalize process PATH entries (strip stray quotes), prepend Node/npm paths, require `Get-Command node` and `Get-Command openclaw`, print resolved command sources, and invoke OpenClaw via call operator with explicit args (`gateway --port <port>`).
- Prevention: Keep command-resolution checks in startup wrappers before launch and avoid `Invoke-Expression` / string-built command execution.
- Verification: PowerShell parser check returned `parse_ok`; live foreground launch validation pending on MSI.
- References: `scripts/start_openclaw_stack.ps1`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-24 23:55 (local)
- Area: OpenClaw Telegram voice note STT source selection
- Symptom: Short/medium Telegram voice notes ("circles") often failed or fell back too early to Telegram auto-transcript text; some replies asked the user to resend as `.ogg/.m4a` even though the input was a normal `message.voice`.
- Root cause: OpenClaw bridge message normalization prioritized top-level `audio_bytes/audio_path` only and could treat transcript/text as sufficient when nested `message.voice` media metadata existed but no preloaded bytes/path were provided. Voice-note failures also reused a generic STT fallback message that included a poor file-format UX hint.
- Fix: Enforced explicit source priority (`voice` -> `audio` -> audio `document` -> transcript fallback), parsed nested media metadata, added optional message-level media downloader callback support for `file_id`, and added voice-note-specific retry fallback messages plus `empty_transcript_voice_note` handling (no "send as file" request for normal voice notes).
- Prevention: Keep source-selection diagnostics structured (`telegram_stt_source_select`, `telegram_voice_ingest`) and maintain smoke coverage for voice-note priority/download/empty-transcript cases.
- Verification: `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py` PASS (5/5 cases), `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py` PASS, `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py` PASS.
- References: `src/d_brain/integrations/openclaw_bridge.py`, `scripts/openclaw_voice_source_select_smoke.py`, `docs/runbook.md`, `docs/openclaw-integration.md`, `docs/progress.md`

## 2026-02-25 00:20 (local)
- Area: OpenClaw Telegram voice-note STT observability / diagnostics taxonomy
- Symptom: Initial structured logs were useful but still too ambiguous in live debugging (missing request correlation, downloader callback identity/path, media bytes/path evidence, and stable final outcome taxonomy). Some fallback reasons used overlapping names (`voice_stt_failed`, `stt_timeout`, `media_path_*`), which reduced operator speed during incident triage.
- Root cause: Voice-note hardening was implemented first for behavior correctness; observability fields and fallback reason taxonomy were added incrementally and not normalized yet.
- Fix: Added normalized evidence fields (`requestId`, `userIdHash`, `messageKind`, Telegram file-id flags, downloader metadata, media bytes/path metadata, transcript shape hints, `finalInputSource`, `finalOutcome`, `responseMode`) to `telegram_stt_source_select` / `telegram_voice_ingest`; added whitelist-based fallback reason normalization and lightweight counters under existing in-memory observability counters; added `scripts/openclaw_voice_log_summary.py` to summarize voice STT events by `requestId`.
- Prevention: Keep one fallback reason whitelist and verify with edge smoke cases (malformed media shape, downloader exception, nested bytes, transcript fallback regressions).
- Verification: `.\.venv\Scripts\python.exe -m py_compile src\d_brain\integrations\openclaw_bridge.py scripts\openclaw_voice_source_select_smoke.py scripts\openclaw_voice_log_summary.py`, `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py`, `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`, `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py`, `.\.venv\Scripts\python.exe scripts\openclaw_voice_log_summary.py --file .\tmp_voice_log.txt --lines 50 --jsonl` (synthetic sample).
- References: `src/d_brain/integrations/openclaw_bridge.py`, `scripts/openclaw_voice_source_select_smoke.py`, `scripts/openclaw_voice_log_summary.py`, `docs/runbook.md`, `docs/progress.md`
