# Close Session (Codex)

## 1) Update Docs
- Update `docs/progress.md` with what changed and today’s entry
- Update `docs/context-pack.md` if project context shifted
- Update `docs/decisions.md` with any new decisions or pending items
- Update `docs/runbook.md` if operational steps changed
- Update `docs/db-schema.md` if data model changed
- Update `docs/backlog.md` if priorities shifted

## 2) Final Report
- Summary: what was done, what was not done, and why
- Risks / gotchas
- Tests run (or note not run)
- List of files modified

## 3) Project State Snapshot
- Current status summary (1-3 bullets)
- Open questions
- Next step (single concrete action)

## Documentation Language Rule (must follow)
- All project documentation must be written in English only.
- Do not use Cyrillic in docs/templates/generated documentation.

Documentation Language Contract:
All docs and generated documentation must be in English only (no Cyrillic).
This includes markdown files, comments in documentation templates, progress notes, context packs, runbooks, and architecture notes.
Reason: Cyrillic rendering is unreliable in the current environment.

## 4) Architecture Compliance Check
- reuse-first followed
- one main skill + sidecar maintained
- anti-context-bloat respected
- local LLM used only for utility tasks
- no hardcoding; configs/adapters used
