# Release Notes v1.0 (Draft)

## Summary
- Production runtime remains OpenClaw-first (OpenClaw = Telegram transport; `d_brain` = bridge/logic/services).
- aiogram polling is explicitly dev-only and disabled in production mode.
- Bridge command/voice reliability, diagnostics, and fallback behavior are hardened for cutover readiness.
- Documentation workflow now requires same-session docs updates for behavior/routing changes.
- Session continuity workflow is formalized via workspace bootstrap/heartbeat + progress + learnings.

## Included Operational Improvements
- Production diagnostics and no-polling readiness/RC smoke coverage.
- Bridge `/diag`, `/diag full`, `/ping`, `/version`, preferences, and duplicate protection.
- Voice/media priority and non-fatal TTS/STT fallback behavior.
- Cutover checklist and recovery/rollback documentation.

## Cutover Status (Current Draft)
- Offline/no-polling verification: completed.
- Bridge command acceptance (CLI/no-polling path): completed.
- Voice fallback/policy acceptance (smoke): completed.
- Live Telegram channel acceptance via OpenClaw gateway: pending manual operator verification.

## Known Limitations (Current Draft)
- If `OPENAI_API_KEY` is not configured in the runtime environment, main/voice reasoning routes may be unavailable.
- If `DEEPGRAM_API_KEY` is not configured and Deepgram is enabled, STT/TTS features may degrade or fall back.
- Windows console may require UTF-8 (`chcp 65001` / `PYTHONIOENCODING=utf-8`) for CLI outputs containing emoji.

## Recommended Sign-off Path
1. Run `docs/cutover-checklist.md` commands.
2. Perform manual Telegram command and voice acceptance on the production-like runtime.
3. Record evidence and verdict in the checklist.
4. Promote to final `v1.0` sign-off notes.

