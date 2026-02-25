# Live Telegram Acceptance Template (OpenClaw-first)

Use this template during the final pre-signoff live Telegram acceptance run.

## Run Metadata
- Timestamp:
- Operator:
- Environment:
- OpenClaw gateway status snapshot:
- Telegram channel status snapshot:
- Evidence file path (from `ops/capture-live-signoff.ps1`):

## Command Acceptance (Real Telegram Transport Path)
### 1. `/help`
- Expected: command list returned through OpenClaw gateway; no crash.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 2. `/status`
- Expected: status reply returned; bridge path responds normally.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 3. `/plan list`
- Expected: plan list or empty-state response; no crash.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 4. `/plan add Test live`
- Expected: plan created response with ID; no duplicate side effect.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 5. `/diag`
- Expected: transport/prefs/sidecar summary shown; no secrets.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 6. `/ping`
- Expected: quick bridge response with timing; no error.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 7. `/version`
- Expected: version/build/commit/transport info shown.
- Result: `PASS` / `FAIL`
- Evidence notes:

## Voice Acceptance (Real Telegram Transport Path)
### 8. Send RU voice note
- Expected: STT policy uses `ru`; meaningful reply returned; flow stays alive.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 9. Request TTS reply
- Expected: valid `sendVoice` or `sendAudio` media is sent when TTS output is valid.
- Result: `PASS` / `FAIL`
- Evidence notes:

### 10. If TTS fails, verify text fallback (non-fatal)
- Expected: no crash; text fallback reply returned; gateway remains responsive.
- Result: `PASS` / `FAIL` / `N/A`
- Evidence notes:

## Transcript-only Warning Check (No Media)
- Action: send transcript-like text without voice/audio media.
- Expected: short RU warning (no fake STT, no crash).
- Result: `PASS` / `FAIL`
- Evidence notes:

## Voice/Fallback Assertions
- Media > transcript priority: `PASS` / `FAIL`
- `file must be non-empty` no longer drops the flow: `PASS` / `FAIL`
- sendAudio/sendVoice failure path is non-fatal fallback: `PASS` / `FAIL`

## Final Result
- Manual command acceptance: `PASS` / `FAIL`
- Manual voice acceptance: `PASS` / `FAIL`
- Live Telegram channel verification: `PASS` / `FAIL`
- Final verdict candidate: `GO` / `GO WITH KNOWN LIMITATIONS` / `NO-GO`
- Blocking issues (if any):

