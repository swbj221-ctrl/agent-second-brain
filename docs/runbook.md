# Runbook

## Session Workflow (Codex)
- Use `docs/commands/open-session.md` to start every session.
- Use `docs/commands/close-session.md` to end every session.
- Update docs during implementation, not only at the end.
- Documentation must be English-only (no Cyrillic).

## Local Development
TODO: steps to start local services, env vars, and health checks.

## Migrations
- Create: `python scripts/migrate.py create <name>`
- Apply: `python scripts/migrate.py apply`
- Rollback: `python scripts/migrate.py rollback`
- Status: `python scripts/migrate.py status`

## Verification
- Scheduler smoke test (no-op): run a short script or REPL and call
  `Scheduler(build_default_registry()).run_once("noop")`.

## Debugging
TODO: logs, tracing, and common failure modes.
