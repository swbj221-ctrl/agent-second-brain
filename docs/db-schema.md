# DB Schema

## Overview
Purpose: persist minimal state needed by the sidecar backend.

## Entities (Stage 1)
- `artifacts`
- `artifact_summaries`
- `notes`
- `jobs`
- `app_settings`
- `app_feature_flags`

## Entities (Stage 3)
- `events`
- `event_reminders`
- `event_parse_logs`

## Fields (Minimal)
- Common: `id` (PK), `created_at`/`updated_at` timestamps where applicable.
- `artifacts`: `source_type`, `source_ref`, `content_type`, `content_path`, `content_hash`.
- `artifact_summaries`: `artifact_id` (FK), `summary_text`, `summary_format`, `model_ref`.
- `notes`: `title`, `body`, `source_type`, `source_ref`.
- `jobs`: `name`, `schedule_spec`, `status`, `last_run_at`, `next_run_at`.
- `app_settings`: `key`, `value`, `updated_at`.
- `app_feature_flags`: `key`, `enabled`, `updated_at`.
- `events`: `title`, `body`, `start_at`, `end_at`, `status`, `source_type`, `source_ref`.
- `event_reminders`: `event_id` (FK), `remind_at`, `status`, `triggered_at`.
- `event_parse_logs`: `source_type`, `source_ref`, `input_excerpt`, `input_hash`, `input_length`, `parse_status`, `error_message`, `event_id` (FK, nullable).

## Migrations
- Tool: `scripts/migrate.py` (SQLite)
- Versioning: `YYYYMMDD_HHMM_description.sql`
- Format: `-- +migrate Up` and `-- +migrate Down` sections in each file.

## Notes
- Keep schema minimal; avoid storing large context blobs.
