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

## Entities (Stage 4)
- `english_words`
- `english_topics`
- `english_sessions`
- `english_session_turns`
- `english_session_word_usage`

## Entities (Stage 5)
- `reflection_sessions`
- `reflection_turns`

## Entities (Stage 6)
- `news_sections`
- `news_sources`
- `news_items`

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
- `english_words`: `word` (unique).
- `english_topics`: `name` (unique).
- `english_sessions`: `topic_id` (FK, nullable), `status`, `opened_at`, `closed_at`, `summary_text`.
- `english_session_turns`: `session_id` (FK), `role`, `content`.
- `english_session_word_usage`: `session_id` (FK), `word_id` (FK), `usage_count`.
- `reflection_sessions`: `status`, `opened_at`, `closed_at`, `summary_text`.
- `reflection_turns`: `session_id` (FK), `role`, `content`.
- `news_sections`: `name` (unique), `description`, `status`.
- `news_sources`: `section_id` (FK), `name`, `source_type`, `source_ref`, `status`.
- `news_items`: `section_id` (FK), `source_id` (FK), `external_id`, `title`, `url`,
  `published_at`, `content_text`, `content_hash`, `raw_payload`.

## News Dedupe (Stage 6)
Deterministic dedupe uses `content_hash` computed from a normalized JSON payload:
- Normalize each field by trimming whitespace and collapsing internal whitespace.
- Lowercase `title`, `url`, and `content_text` for hash input.
- Include `published_at` and `external_id` as-is after trimming.
- Build a JSON object with keys:
  `title`, `url`, `published_at`, `content_text`, `external_id`, `raw_payload`.
- Serialize with sorted keys and compact separators, then hash with sha256.

## Migrations
- Tool: `scripts/migrate.py` (SQLite)
- Versioning: `YYYYMMDD_HHMM_description.sql`
- Format: `-- +migrate Up` and `-- +migrate Down` sections in each file.

## Notes
- Keep schema minimal; avoid storing large context blobs.
