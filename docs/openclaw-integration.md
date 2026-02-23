# OpenClaw Integration

## Strategy
- OpenClaw is the core runtime/gateway/channel foundation.
- Reuse-first: prefer stable OpenClaw components and marketplace skills.
- One main OpenClaw skill for domain workflows and Telegram UX.
- One sidecar backend for storage, workers, schedulers, collectors, and utility services.
- Local LLM is a utility layer; Codex handles reasoning/dialog/final synthesis.
- Anti-context-bloat: structured retrieval first, summaries over raw transcripts, top-k context.

## What Stays Outside OpenClaw Core
- Domain logic and orchestration policies.
- SQLite schema and migrations.
- Vault organization and data retention.
- Custom collectors/workers and schedulers.
- Utility services (extraction, tagging, formatting).

## Integration Interfaces
- Skill -> Sidecar: HTTP/RPC with explicit schemas and payload limits.
- Sidecar -> Skill: deterministic responses and error contracts.
- Logging/metrics: structured logs and trace IDs.

## Minimal Skill <-> Sidecar Contract (Draft)
Scope: Stage 1 only. Keep the surface small and avoid over-design.

### Request (Skill -> Sidecar)
- `request_id` (string, required): client-generated unique ID.
- `user_id` (string, required): stable caller identity.
- `action` (string, required): short verb, e.g. `ping`, `noop_job`.
- `payload` (object, optional): action-specific data (must be JSON-serializable).
- `metadata` (object, optional): trace IDs and client info.

### Response (Sidecar -> Skill)
- `request_id` (string, required): echo from request.
- `status` (string, required): `ok` or `error`.
- `data` (object, optional): action result.
- `error` (object, optional): `{ code, message }`.

### Validation Notes
- Reject unknown `action` values with `status=error`.
- Enforce JSON schema validation at the boundary.
- Validate `payload` per action and return structured errors.

### Payload Limits
- Default max payload size: 32 KB (configurable).
- Reject requests exceeding the limit with `status=error`.

## Compatibility Goals
- Minimize deep core modifications.
- Use adapters/configs to preserve update compatibility.
- Keep APIs versioned and forward-compatible.

## Guardrails
- No hardcoding in skills or sidecar.
- Migrations are explicit and versioned.
- Context payloads are validated and size-limited.
