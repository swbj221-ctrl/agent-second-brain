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

## 2026-02-26 09:55 (local)
- Area: OpenClaw Telegram upstream embedded transcript ingestion
- Symptom: Mixed RU+EN voice note could collapse to English tail (`how are you`) when upstream delivered `[Audio] ... Transcript:` text before bridge media extraction.
- Root cause: Source-select treated that payload as transcript-only when media came only via embedded text (`[media attached ...]`) and no structured `voice/audio/document` object reached bridge.
- Fix: Added embedded-media extraction in `openclaw_bridge._normalize_voice_payload` (path/mime/ext inference from text), promoted inferred media into media hints, suppressed embedded transcript text whenever media is inferred/present, and logged new evidence fields (`inferredMediaFromEmbeddedPrompt`, `embeddedMediaPath*`, `embeddedMediaMimeType`, `embeddedMediaExt`).
- Prevention: Keep wrapper-first path, and assert transcript precedence with smoke that sends embedded media-attached text without Telegram media object.
- Verification: `scripts/openclaw_voice_source_select_smoke.py` includes `embedded_media_attached_path_without_voice_object_prefers_media_stt`.
- References: `src/d_brain/integrations/openclaw_bridge.py`, `scripts/openclaw_voice_source_select_smoke.py`, `docs/runbook.md`, `docs/openclaw-integration.md`

## Current Session Notes
- Added upstream embedded-media inference + diagnostics and regression smoke for transcript precedence.

## 2026-02-25 23:55 (local)
- Area: Live voice path verdict strict chain correlation
- Symptom: `openclaw_live_voice_path_verdict.py` reported bridge markers present but `full_chain_same_request_id=false` with empty `stage_request_ids`, even though runtime/redirect/wrapper/adapter/bridge markers existed in evidence.
- Root cause: Verdict parser requestId regex did not allow runtime-style request IDs containing pipe separators (`|`) from OpenClaw tool-call IDs (for example `oc-...|fc-...`). Some markers were also embedded in top-level OpenClaw log `raw` JSON strings, which reduced extraction reliability.
- Fix: Extended verdict parser requestId extraction to accept `|` (and common token separators), scan nested `raw`/`message` JSON blobs in log/session records, and keep strict same-requestId chain requirements unchanged. Added focused smoke fixtures for nested `raw` markers + pipe requestId (confirmed bridge) and a missing-stage case (stays inconclusive).
- Prevention: When strict chain correlation fails with markers present, inspect requestId format first (especially runtime-derived IDs) and add parser coverage for the exact log encoding shape before changing routing logic.
- Verification: `.\.venv\Scripts\python.exe scripts\openclaw_live_voice_path_verdict_smoke.py` PASS (includes pipe requestId + nested `raw` fixtures).
- References: `scripts/openclaw_live_voice_path_verdict.py`, `scripts/openclaw_live_voice_path_verdict_smoke.py`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-26 00:10 (local)
- Area: Embedded Telegram audio runtime exec-guard bypass coverage (installed OpenClaw `pi-embedded`)
- Symptom: Latest live strict verdict still showed `session_deepgram_direct=true`, indicating a direct Deepgram exec branch was still reachable for an embedded Telegram audio prompt despite the runtime guard hotfix.
- Root cause: Runtime guard Deepgram detection was too narrow (`api.deepgram.com/v1/listen` only), so alternate Deepgram command shapes in exec-like tools could bypass the rewrite.
- Fix: Widened runtime guard Deepgram signature matching to any Deepgram command text (`deepgram` / `deepgram.com`) for embedded-audio exec-like tool calls and kept default behavior wrapper-first/fail-closed. Added explicit diagnostic override `OPENCLAW_AUDIO_DIRECT_DEEPGRAM_DIAGNOSTIC=1|true|yes` to allow direct Deepgram only when intentionally enabled, with a visible marker (`selectedPath=embedded_direct_deepgram_diag`).
- Prevention: Treat runtime exec-guard command matching as signature-based (provider/domain family) instead of a single endpoint string when blocking unsafe direct STT branches.
- Verification: `node.exe --check` PASS on both patched `pi-embedded` bundles; verdict smoke PASS (`scripts/openclaw_live_voice_path_verdict_smoke.py`). Live Telegram recheck still required.
- References: `C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-54x4PM3A.js`, `C:\Users\User\AppData\Roaming\npm\node_modules\openclaw\dist\pi-embedded-CWNyms-S.js`, `docs/runbook.md`, `docs/progress.md`

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

## 2026-02-25 22:54 (local)
- Area: Live embedded voice path verdict evidence extraction
- Symptom: `scripts/openclaw_live_voice_path_verdict.py --json` failed in Windows console with `UnicodeEncodeError` (`cp1251`), and full-session scans produced noisy evidence lines from older session history that were not suitable as strict live proof.
- Root cause: Windows console default encoding could not emit some Unicode characters, and the verdict helper intentionally performs best-effort scanning across the full provided files without request scoping.
- Fix: Re-ran with `PYTHONIOENCODING=utf-8` and used tail-only slices (`session_tail_250.jsonl`, `log_tail_200.jsonl`) to isolate the latest live test window before running the verdict helper.
- Prevention: For live acceptance proof, always run the verdict helper on short tail slices and set UTF-8 console output first on Windows.
- Verification: Tail-scoped verdict returned `LIVE_PATH_CONFIRMED_BRIDGE` for the sampled live window.
- References: `scripts/openclaw_live_voice_path_verdict.py`, `artifacts/triage_tail_out.json`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-25 23:59 (local)
- Area: Embedded voice strict verdict chain correlation (repo requestId continuity + parser stage extraction)
- Symptom: Strict verdict stayed `INCONCLUSIVE` with bridge/runtime markers visible because the same-requestId full chain was not formed or not fully counted.
- Root cause: In repo bridge path, `dispatch_voice_sync(...)` accepted `request_id` but did not pass it into async `dispatch_voice(...)`, which could break bridge-stage request correlation. In the verdict helper, wrapper-stage extraction was too strict about JSON formatting (`"key":"value"` only), so some JSON spacing/escaping variants did not populate `wrapper_select` in `stage_request_ids`.
- Fix: Passed `request_id` through `dispatch_voice_sync -> dispatch_voice`, normalized `requestId`/`request_id` at redirect wrapper / wrapper CLI / adapter / bridge boundaries, and hardened verdict parser stage extraction for `traceStage` / `selectedPath` spacing/escaping variants without weakening same-requestId strictness.
- Prevention: For request-scoped proof chains, verify requestId continuity across all handoff layers first, and keep verdict parsing tolerant to log encoding/JSON formatting differences while preserving strict acceptance criteria.
- Verification: `py_compile` for bridge/adapter/wrapper/redirect/verdict + focused smokes (`openclaw_embedded_media_redirect_smoke.py`, `openclaw_live_voice_bridge_cli_smoke.py`, `openclaw_live_voice_path_verdict_smoke.py`, `openclaw_voice_source_select_smoke.py`, `openclaw_voice_dispatch_smoke.py`) PASS.
- References: `src/d_brain/integrations/openclaw_bridge.py`, `vault/.claude/skills/openclaw-main/adapter.py`, `scripts/openclaw_embedded_media_redirect_cli.py`, `scripts/openclaw_live_voice_bridge_cli.py`, `scripts/openclaw_live_voice_path_verdict.py`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-26 00:20 (local)
- Area: Verdict contamination / stale Deepgram scope in live voice path verification
- Symptom: Verdict could report `LIVE_PATH_CONFIRMED_BRIDGE` using a fixture-like requestId visible in session data but not grep-able in the provided live log capture; `session_deepgram_direct=true` could also be triggered by stale unrelated session-tail history.
- Root cause: The verdict helper merged stage/request evidence from log capture and session JSONL into a single pool, and direct Deepgram detection was unscoped across the whole session tail.
- Fix: Split log-derived stage/request tracking from merged tracking, require the selected `full_chain_request_id` to be present in raw `--log-capture` lines, and scope Deepgram bypass detection to current-run evidence (Deepgram in log capture or session Deepgram evidence with requestId also seen in log capture).
- Prevention: For live acceptance, always treat session JSONL as supporting evidence only; require final chain requestId and bypass evidence to be anchored to the explicit log-capture file for the run.
- Verification: `\.venv\Scripts\python.exe scripts\openclaw_live_voice_path_verdict_smoke.py` PASS (includes session-only fixture chain rejection + stale session Deepgram non-scope).
- References: `scripts/openclaw_live_voice_path_verdict.py`, `scripts/openclaw_live_voice_path_verdict_smoke.py`, `docs/runbook.md`, `docs/progress.md`

## 2026-02-26 00:35 (local)
- Area: Live log-capture proof-chain discoverability (redirect/wrapper marker sink alignment)
- Symptom: Strict verdict could stay `INCONCLUSIVE` with `full_chain_request_id_in_log_capture=false` even when session evidence showed a full chain, indicating some stages were not reliably grep-discoverable in the captured `openclaw logs` stream.
- Root cause: Redirect and wrapper markers were primarily returned inside tool JSON payloads and not always visible as standalone log lines in the same sink captured by `openclaw logs --follow --json --plain`.
- Fix: Redirect shim and wrapper CLI now mirror proof/error/trace markers as standalone JSON lines to `stderr`, include both `requestId` and `request_id`, and redirect forwards wrapper stderr marker lines after wrapper execution. Adapter pre/post bridge markers now emit both requestId key styles.
- Prevention: For live proof chains, emit stage markers directly into the observable log sink (stderr/logger) in addition to nested tool payloads; preserve dual requestId key emission across boundaries.
- Verification: `\.venv\Scripts\python.exe -m py_compile` (redirect/wrapper/verdict/adapter), `\.venv\Scripts\python.exe scripts\openclaw_embedded_media_redirect_smoke.py`, `\.venv\Scripts\python.exe scripts\openclaw_live_voice_bridge_cli_smoke.py`, `\.venv\Scripts\python.exe scripts\openclaw_live_voice_path_verdict_smoke.py` (PASS).
- References: `scripts/openclaw_embedded_media_redirect_cli.py`, `scripts/openclaw_live_voice_bridge_cli.py`, `vault/.claude/skills/openclaw-main/adapter.py`, `scripts/openclaw_live_voice_path_verdict.py`, `docs/runbook.md`, `docs/progress.md`
