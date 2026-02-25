---
name: openclaw-main
description: Thin OpenClaw skill adapter for agent-second-brain. Routes selected commands to the existing sidecar without changing business logic.
metadata: {"openclaw":{"phase":"phase-3-batch-d","intent":"command-bridge"}}
---

# OpenClaw Main (Phase 3 Batch D)

This skill is a thin adapter layer only.

## Purpose
- Provide an OpenClaw entry point without altering the existing runtime.
- Preserve the standalone path: `python -m d_brain`.
- Avoid any business logic duplication.

## Command Coverage
Phase 2:
- `/usage`
- `/digest latest`
- `/news latest`
- `/word add <word>`

Phase 3 Batch A (read-only/status):
- `/word list`
- `/topic list`
- `/health list`
- `/calendar today`
- `/calendar upcoming [N]`
- `/calendar date YYYY-MM-DD`
- `/project list [status]`
- `/task list [project_id] [status]`

Phase 3 Batch B (low-risk writes):
- `/topic add <name>`
- `/health add <title>`
- `/project add <name>`
- `/task add <project_id> | <title>`

Phase 3 Batch C (medium-risk workflows):
- `/note <text or url>`
- `/inbox add <text or url>`
- `/inbox list`
- `/inbox summarize <id>`
- `/inbox save <id> [title]`
- `/news generate`
- `/news deliver`

Phase 3 Batch D (voice/long-running/delivery commands only):
- `/tutor start [target_minutes]`
- `/tutor stop`
- `/tutor status`
- `/reflect start`
- `/reflect close <session_id> [summary]`
- `/reminder deliver`

## Guardrails
- No sidecar changes.
- No Telegram UX changes.
- Safe user-facing errors only.
- Voice/audio/document(audio) messages should route through the existing OpenClaw adapter -> `d_brain.integrations.openclaw_bridge` path (no direct embedded STT bypass).

## Future Phases (High Level)
- None.
