# Open Session (Codex)

## 1) Read Docs First
- Read `docs/context-pack.md`
- Read `docs/decisions.md`
- Read `docs/progress.md`
- Read `docs/runbook.md`
- Read `docs/openclaw-integration.md`
- Read `docs/db-schema.md` (if schema work involved)
- Read `docs/backlog.md`

## 2) Project Summary
- 3-6 bullets: current goals, constraints, architecture (reuse-first, one main skill + sidecar, anti-context-bloat, local LLM utility, Codex reasoning)
- State any blockers or missing info

## 3) Session Plan
- Provide a plan with clear milestones and **acceptance criteria** per milestone
- Keep scope minimal; avoid context bloat
- Prefer reuse-first: existing components, configs, adapters
- Avoid hardcoding; use configs/adapter layers

## 4) Acceptance Criteria (explicit)
- List measurable outcomes for this session
- Include docs updates required by this session

## 5) Files & Touch Points
- List files that will be created/modified
- Identify any configs/adapters to extend

## Documentation Language Rule (must follow)
- All project documentation must be written in English only.
- Do not use Cyrillic in docs/templates/generated documentation.

Documentation Language Contract:
All docs and generated documentation must be in English only (no Cyrillic).
This includes markdown files, comments in documentation templates, progress notes, context packs, runbooks, and architecture notes.
Reason: Cyrillic rendering is unreliable in the current environment.

## Operating Rules (must follow)
- Update docs during work, not only at the end
- Keep prompts minimal and modular
- Local LLM for utility tasks only; Codex handles reasoning/dialog/final synthesis
- One primary skill + sidecar backend (no skill sprawl)
- Prefer explicit interfaces and schemas
