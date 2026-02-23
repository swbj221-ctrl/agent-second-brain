# DB Schema

## Overview
Purpose: persist minimal state needed by the sidecar backend.

## Entities (TBD)
- `tasks`
- `runs`
- `artifacts`
- `audit_logs`

## Fields (TBD)
- Define primary keys, timestamps, and foreign keys.

## Migrations
- Tool: TBD
- Versioning: `YYYYMMDDHHMM_description`

## Notes
- Keep schema minimal; avoid storing large context blobs.
