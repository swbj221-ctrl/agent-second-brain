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

## 2026-02-25 10:47 (local)
- Area: OpenClaw bridge voice-note STT fallback UX
- Symptom: Live Telegram `message.voice` failures still sometimes returned legacy generic UX asking the user to resend as `.ogg/.m4a` file.
- Root cause: Voice fallback text was formed in multiple branches, so generic transcript/media fallback text could bypass the voice-note-safe retry wording.
- Fix: Added a final bridge response safety override for voice-note fallback paths, centralized voice-note-safe fallback text selection, strengthened `telegram_voice_note` inference, and guaranteed structured fallback logs with `isVoiceNote`.
- Prevention: Keep fallback text finalization centralized in `_build_voice_response(...)` and retain regression smokes that assert no `.ogg/.m4a`/file resend UX for `message.voice`.
- Verification: `.\.venv\Scripts\python.exe -m py_compile src\d_brain\integrations\openclaw_bridge.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py` (all PASS).
- References: `src/d_brain/integrations/openclaw_bridge.py`, `scripts/openclaw_voice_source_select_smoke.py`, `docs/runbook.md`, `docs/openclaw-integration.md`, `docs/progress.md`

## 2026-02-25 11:05 (local)
- Area: OpenClaw runtime import wiring / bridge diagnostics
- Symptom: Live OpenClaw voice path did not show new bridge structured events or the bridge patch marker despite local smoke PASS.
- Root cause: Runtime likely loaded a different `d_brain.integrations.openclaw_bridge` module copy (or executed without repo `src` first in `sys.path`), so local patched file was not the one used by the gateway.
- Fix: Added runtime import-path diagnostics logs in bridge/adapter and hardened adapter import wiring to prepend repo `src` before importing `d_brain` when `src/d_brain` is found relative to the adapter file.
- Prevention: Keep one-time runtime module-path logs enabled for voice dispatch triage and verify `moduleFile` + `voiceFixRev` after OpenClaw restarts.
- Verification: `.\.venv\Scripts\python.exe -m py_compile src\d_brain\integrations\openclaw_bridge.py vault\.claude\skills\openclaw-main\adapter.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py` (all PASS).
- References: `vault/.claude/skills/openclaw-main/adapter.py`, `src/d_brain/integrations/openclaw_bridge.py`, `docs/runbook.md`, `docs/openclaw-integration.md`, `docs/progress.md`

## 2026-02-25 11:35 (local)
- Area: Telegram voice/audio/document STT pipeline diagnostics and routing
- Symptom: Voice/audio quality issues were hard to triage because logs did not show download/preprocess/STT stages clearly, and non-audio documents could be considered media hints in the OpenClaw adapter path.
- Root cause: The bridge lacked stage-level pipeline logs and optional audio normalization diagnostics; adapter media hint detection treated any `document` as media before audio MIME/extension filtering.
- Fix: Added `telegram_voice_pipeline` staged logs (download, optional ffmpeg preprocess, STT request/result, transcript preview, pipeline errors), optional `TELEGRAM_STT_NORMALIZE_AUDIO=1` ffmpeg normalization hook, optional `TELEGRAM_STT_LANGUAGE` override for non-tutor path, and tightened adapter media hint routing to audio documents only. Added aiogram voice handler debug logs for `get_file` / `download_file` stages and audio metadata.
- Prevention: Keep stage-level pipeline logs and synthetic smoke coverage for conversion failure fallback; avoid broad document media predicates in voice routers.
- Verification: `.\.venv\Scripts\python.exe -m py_compile src\d_brain\integrations\openclaw_bridge.py src\d_brain\bot\handlers\voice.py vault\.claude\skills\openclaw-main\adapter.py scripts\openclaw_voice_dispatch_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_source_select_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py`; `.\.venv\Scripts\python.exe scripts\openclaw_fallback_smoke.py` (all PASS).
- References: `src/d_brain/integrations/openclaw_bridge.py`, `src/d_brain/bot/handlers/voice.py`, `vault/.claude/skills/openclaw-main/adapter.py`, `scripts/openclaw_voice_dispatch_smoke.py`, `docs/runbook.md`

## 2026-02-25 11:50 (local)
- Area: Voice pipeline ffmpeg-missing regression coverage
- Symptom: `ffmpeg_missing` fallback branch depended on local machine setup, so regressions could slip through when `ffmpeg` happened to be installed.
- Root cause: No deterministic smoke path forced the bridge preprocess branch (`TELEGRAM_STT_NORMALIZE_AUDIO=1` + missing ffmpeg) without invoking real ffmpeg.
- Fix: Added deterministic smoke coverage by monkeypatching bridge `shutil.which -> None` and asserting exact `pipeline_error_code=ffmpeg_missing`, safe user fallback text, and preprocess structured log fields (`normalizeAudioEnabled`, `ffmpegPathFound`, `inputMimeType`).
- Prevention: Keep ffmpeg-availability branches tested via monkeypatch, not workstation state.
- Verification: `.\.venv\Scripts\python.exe scripts\openclaw_voice_dispatch_smoke.py` PASS (includes `ffmpeg_missing_fallback`).
- References: `scripts/openclaw_voice_dispatch_smoke.py`, `src/d_brain/integrations/openclaw_bridge.py`, `docs/runbook.md`, `docs/progress.md`

## Current Session Notes
- No new entries yet for this file creation step.

## 2026-02-25 14:10 (local)
- Area: OpenClaw embedded voice/audio transcript encoding (Windows shell mojibake)
- Symptom: Embedded audio transcript text sometimes appeared as mojibake token patterns or degraded to empty transcript when crossing the OpenClaw embedded `exec`/PowerShell path, causing corrupted fallback text and unreliable diagnostics.
- Root cause: Transcript text crossing shell boundaries is vulnerable to Windows console encoding mismatches (UTF-8 vs cp1251/cp866) and ad-hoc stdout parsing. The wrapper path was already safer than direct Deepgram `exec`, but it did not normalize transcript payload encoding formats (`TranscriptB64`) or explicitly detect/suppress corrupted transcript fallback input.
- Fix: Hardened `openclaw_live_voice_bridge_cli.py` with UTF-8 stdio reconfiguration, `TranscriptB64`/`TranscriptBase64` UTF-8 decode, explicit `EMPTY_TRANSCRIPT` diagnostics, mojibake detection, and suppression of suspicious embedded transcript text before adapter handoff. Hardened `openclaw_embedded_media_redirect_cli.py` wrapper subprocess env (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`). Updated the installed `pi-embedded` runtime exec-guard hotfix command to set PowerShell UTF-8 input/output/console encoding before invoking the redirect shim.
- Prevention: Prefer JSON/base64 transcript payloads across shell boundaries, keep transcript diagnostics explicit (`status`, `decode_mode`, `len`, `mojibake_suspected`), and do not trust embedded transcript text as fallback input when media STT should be authoritative.
- Verification: `.\agent-second-brain\.venv\Scripts\python.exe -m py_compile agent-second-brain\scripts\openclaw_live_voice_bridge_cli.py agent-second-brain\scripts\openclaw_embedded_media_redirect_cli.py agent-second-brain\scripts\openclaw_live_voice_bridge_cli_smoke.py`; `.\agent-second-brain\.venv\Scripts\python.exe agent-second-brain\scripts\openclaw_live_voice_bridge_cli_smoke.py`; `C:\Program Files\nodejs\node.exe --check` on both patched `pi-embedded` bundles (PASS).
- References: `agent-second-brain/scripts/openclaw_live_voice_bridge_cli.py`, `agent-second-brain/scripts/openclaw_embedded_media_redirect_cli.py`, `agent-second-brain/scripts/openclaw_live_voice_bridge_cli_smoke.py`, `agent-second-brain/docs/runbook.md`, `agent-second-brain/docs/progress.md`

## 2026-02-25 13:20 (local)
- Area: OpenClaw embedded Telegram audio/voice bypass hard-enforcement (runtime)
- Symptom: Live Telegram audio/voice still bypassed the project wrapper/adapter/bridge path and used direct Deepgram STT via `toolCall exec`, so bridge multipass and proof markers never appeared.
- Root cause: The bypass is generated in the installed OpenClaw embedded runtime (`pi-embedded` bundle) before project repo code executes; workspace instructions and repo wrappers alone do not provide a hard guarantee.
- Fix: Patched the installed OpenClaw npm `pi-embedded` bundles at `runBeforeToolCallHook(...)` to detect direct Deepgram STT `exec`/`bash` commands for embedded audio media prompts and rewrite them to the project redirect shim (`scripts/openclaw_embedded_media_redirect_cli.py`) with runtime proof/error markers and a safe block fallback when shim/python path resolution fails.
- Prevention: Re-apply or upstream the runtime exec-guard patch after OpenClaw updates/reinstalls; verify the runtime exec-guard marker appears before wrapper/adapter/bridge markers in live tests.
- Verification: `C:\Program Files\nodejs\node.exe --check` on patched `pi-embedded-CWNyms-S.js` and `pi-embedded-54x4PM3A.js` (PASS). Live Telegram marker-order + verdict verification pending.
- References: `C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-CWNyms-S.js`, `C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-54x4PM3A.js`, `scripts/openclaw_embedded_media_redirect_cli.py`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-25 12:20 (local)
- Area: OpenClaw live Telegram voice/audio routing (bridge multipass verification)
- Symptom: Live Telegram voice/audio messages were answered, but `telegram_voice_pipeline` / `stt_multipass_*` never appeared in `openclaw logs`, so the new bridge multipass STT path could not be verified or applied.
- Root cause: Live OpenClaw embedded agent handled `<media:audio>` via ad-hoc `exec` + direct Deepgram STT (visible in session JSONL tool calls), bypassing `vault/.claude/skills/openclaw-main/adapter.py` and `d_brain.integrations.openclaw_bridge`.
- Fix: Added a narrow wrapper `scripts/openclaw_live_voice_bridge_cli.py` that parses OpenClaw embedded Telegram audio prompts and routes audio/voice/audio-document payloads into the existing adapter/bridge path, with proof marker JSON `openclaw_voice_dispatch_path_select` and explicit diagnostic fallback (no silent direct-STT fallback). Added adapter proof marker for the media->bridge branch and workspace bootstrap/AGENTS guidance to use the wrapper first for embedded `<media:audio>`.
- Prevention: When live voice fixes do not show bridge markers, check `openclaw` session JSONL for direct `exec` STT tool calls before tuning the bridge heuristic; prove path selection first.
- Verification: `.\.venv\Scripts\python.exe -m py_compile scripts\openclaw_live_voice_bridge_cli.py scripts\openclaw_live_voice_bridge_cli_smoke.py vault\.claude\skills\openclaw-main\adapter.py`; `.\.venv\Scripts\python.exe scripts\openclaw_live_voice_bridge_cli_smoke.py` (PASS).
- References: `scripts/openclaw_live_voice_bridge_cli.py`, `scripts/openclaw_live_voice_bridge_cli_smoke.py`, `vault/.claude/skills/openclaw-main/adapter.py`, `.openclaw/workspace/bootstrap.md`, `docs/runbook.md`

## 2026-02-24 21:35 (local)
- Area: Windows CLI verification (`scripts/ux_cli.py`)
- Symptom: `/plan list` verification command failed with `UnicodeEncodeError` in `cp1251`.
- Root cause: Windows console encoding could not print emoji characters in plan titles.
- Fix: Run verification commands with UTF-8 console/output (`chcp 65001` and `PYTHONIOENCODING=utf-8`).
- Prevention: Use UTF-8 console settings for CLI verification commands that may print user content.
- Verification: `/plan list`, `/plan add test-cutover`, `/diag`, `/ping`, `/version` printed successfully after UTF-8 workaround.
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

## 2026-02-25 14:55 (local)
- Area: OpenClaw Windows `gateway/ws` pretty logging
- Symptom: `gateway/ws` pretty `req/res` lines in Windows logs showed recurring mojibake token sequences while many JSON log lines remained readable.
- Root cause: The compiled `gateway/ws` pretty formatter in installed OpenClaw `push-apns-*.js` bundles emitted ANSI-colored unicode pretty strings into the normal logger/file path, so Windows log viewing/encoding paths could misrender decorative glyphs.
- Fix: Applied a temporary local runtime patch (installed npm bundle, outside repo source) to add `stripAnsi` and `normalizeLogForWindows`, write sanitized/plain file-log messages, preserve pretty `consoleMessage` for console output, and replace decorative `gateway/ws` glyph tokens with ASCII-safe markers (`<-`, `->`, `<->`, `OK`, `ERR`, `...`).
- Prevention: Keep file logging plain and ANSI-free for `gateway/ws` pretty messages on Windows, and re-apply or upstream the runtime patch after OpenClaw bundle updates/reinstalls.
- Verification: `C:\Program Files\nodejs\node.exe --check` PASS on patched `push-apns-BRGDsNym.js` and `push-apns-A3yh2vIh.js`; source inspection confirms sanitized file writes and ASCII-safe tokens. Live post-restart file-log evidence of a new patched `gateway/ws` line is still pending.
- References: `docs/runbook.md`, `docs/openclaw-integration.md`, `docs/progress.md`, `docs/decisions.md`

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
