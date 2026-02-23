# Context Pack

## Short Summary
OpenClaw-based system with reuse-first philosophy: one main skill and a sidecar backend. Local LLM is a utility layer; Codex handles reasoning/dialog/final synthesis. Focus: minimal context, operational clarity, and stable interfaces.

## Architecture Snapshot
- Reuse-tested solutions first (OpenClaw core, marketplace skills, stable libraries)
- One primary skill orchestrating flow
- One sidecar backend for integrations, state, and I/O
- Local LLM for utility tasks (classification, extraction, formatting)
- Codex for reasoning, dialog, and final synthesis
- Anti-context-bloat memory design (structured retrieval, summaries over raw transcripts, top-k context)
- Anti-hardcode policy (configs/adapters/feature flags and explicit migrations)
- Voice priority: human-like output and low latency
- Documentation is English-only (no Cyrillic)

## Project Constraints
- Reuse-tested solutions first
- One main skill + one sidecar backend
- Anti-context-bloat memory design
- Local LLM for utility tasks; Codex for reasoning/final synthesis
- Documentation is English-only (no Cyrillic)

## Current Session Goal
- Stage 16: Reminders Delivery + Calendar-style Telegram Views MVP (first pass) implemented; manual Telegram verification pending on MSI.

## Goals
- Ship a stable, minimal core pipeline
- Keep skills small and composable
- Make integration points explicit and testable

## Non-Goals
- Multiple parallel skills
- Heavy context dumping in prompts
- LLM as business logic

## Current Status
- Stage 1 foundation complete
- Stage 2 ingestion + summary pipeline complete with smoke test
- Stage 3 plans/reminders complete with smoke tests (default + parse)
- Stage 4 English MVP completed and validated by local smoke test on MSI
- Stage 5 Reflection MVP completed and validated by local smoke test on MSI
- Stage 6 News MVP first pass completed; second pass slice implemented (briefing schema, manual briefing, summaries)
- Stage 7 Digest + Heartbeat first pass completed and validated by local smoke test on MSI
- Stage 8 Codex limits indicator + economy mode first pass completed and validated by local smoke test on MSI
- Stage 9 Health MVP first pass completed and validated by local smoke test on MSI
- Stage 10 Idea Research first pass completed and validated by local smoke test on MSI
- Stage 11 Telegram UX wiring MVP completed; manual Telegram verification on MSI pending
- Stage 12 Voice English Tutor MVP first pass implemented; manual Telegram verification on MSI pending
- Stage 13 Reflection Voice Loop MVP first pass implemented; manual Telegram verification on MSI pending
- Stage 14 Books / Philosophy / Knowledge UX MVP first pass implemented; manual Telegram verification on MSI pending

## Key Paths
- `docs/` operational documentation
- `skills/` main skill (single source of truth)
- `backend/` sidecar service (if present)

## Contacts / Owners
- Owner: TBD
- On-call: TBD
