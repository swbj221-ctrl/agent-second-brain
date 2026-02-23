# Decisions

## Decision Log
Format: `YYYY-MM-DD | Decision | Status | Rationale`

- 2026-02-23 | One primary skill + sidecar backend | Accepted | Keeps orchestration centralized while isolating integrations.
- 2026-02-23 | Local LLM as utility layer | Accepted | Fast, cheap utility tasks; keep reasoning in Codex.
- 2026-02-23 | Anti-context-bloat | Accepted | Reduce prompt drift and cost.
- 2026-02-23 | English-only project documentation | Accepted | Cyrillic rendering issues in current environment.
- 2026-02-23 | Reuse-tested solutions first | Accepted | Prefer stable OpenClaw components, marketplace skills, and proven libraries.
- 2026-02-23 | Anti-hardcode policy | Accepted | Use configs/adapters/feature flags and explicit migrations.
- 2026-02-23 | Voice priority (human-like + low latency) | Accepted | Optimize UX for natural output and fast responses.

Documentation Language Contract:
All docs and generated documentation must be in English only (no Cyrillic).
This includes markdown files, comments in documentation templates, progress notes, context packs, runbooks, and architecture notes.
Reason: Cyrillic rendering is unreliable in the current environment.

## Pending
- Persistence store selection
- Migration toolchain
- Interface contract between skill and sidecar
