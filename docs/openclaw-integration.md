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

## Stage 2: Ingestion Contract
Scope: ingestion + short summary pipeline. Reuse the Stage 1 request/response envelope.

### Action
- `action`: `ingest`

### Request Payload (action = ingest)
Required:
- `source_type` (string): e.g., `telegram`, `manual`, `import`.
- `content_type` (string): `text`, `audio`, `image`, `file`.
- `summary_format` (string): default `plain`.

Optional:
- `external_id` (string): client-side id for idempotency or tracking.
- `source_ref` (string): source message id, file id, or URL.
- `content` (string): inline content when `content_type=text`.
- `content_path` (string): path or URI to stored content (for non-text or large input).
- `content_hash` (string): hash of stored content for de-dupe.
- `metadata` (object): additional context (must be JSON-serializable).
  - `metadata.transcript` (string): required to summarize non-text inputs.

Validation rules:
- `source_type`, `content_type`, and `summary_format` are required.
- Provide exactly one of `content` or `content_path`.
- `content` is only allowed when `content_type=text`.
- `content_path` is required for non-text content types.
- Non-text content requires `metadata.transcript` for summarization.
- Reject payloads over 32 KB (configurable).

### Response Data (action = ingest)
- `artifact_id` (integer): created artifact record id.
- `summary_id` (integer): created summary record id.
- `summary_text` (string): short summary text.
- `summary_format` (string): echo input or default.
- `model_ref` (string): local utility model or heuristic identifier.

### Status Codes (app-level)
- `ok`: ingestion + summary created.
- `error`: validation failure, storage failure, or summarization failure.

Error object (when `status=error`):
- `code` (string): `invalid_payload`, `payload_too_large`, `unsupported_type`, `storage_error`, `summary_error`.
- `message` (string): human-readable summary.

## Compatibility Goals
- Minimize deep core modifications.
- Use adapters/configs to preserve update compatibility.
- Keep APIs versioned and forward-compatible.

## Guardrails
- No hardcoding in skills or sidecar.
- Migrations are explicit and versioned.
- Context payloads are validated and size-limited.
