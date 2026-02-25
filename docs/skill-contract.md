# Skill Contract (Internal)

Purpose: define the minimum contract for creating or updating internal skills in this repository with OpenClaw-first compatibility.

## Trigger Rule
- When the user asks to create or update a skill, use the `skill-creator` process first.
- If a requested skill (for example `self-improving-agent`) is not available in the current skill registry, document the fallback workflow in project docs and continue with a repo-local implementation.

## Compatibility Rule (OpenClaw-first)
- Do not change the production transport architecture.
- OpenClaw remains the only Telegram transport in production.
- `d_brain` remains the bridge/logic/services layer.
- Any aiogram polling usage must stay dev-only.

## Required Skill Structure
Minimum folder structure:

```text
<skill-name>/
  SKILL.md
  references/          # optional but recommended for non-trivial skills
  scripts/             # optional; add when deterministic steps repeat
  assets/              # optional; templates/resources used in outputs
```

## Required `SKILL.md` Content
- YAML frontmatter:
  - `name`
  - `description`
- Body instructions in imperative form.
- Clear trigger situations in the `description` field (not only in the body).
- Progressive disclosure guidance:
  - keep `SKILL.md` lean
  - move detailed references to `references/`
  - point to specific reference files from `SKILL.md`

## Required Skill Documentation (Project-side)
For every new/updated skill, document:
- Purpose and trigger conditions
- Input/output expectations
- Smoke checks (local, no secrets)
- Example usage prompts/commands
- Rollback path
- Troubleshooting notes
- Compatibility notes (OpenClaw transport-first, no prod aiogram polling)

Recommended locations:
- Skill-owned docs inside the skill folder (`SKILL.md`, `references/*`)
- Project-level notes in `docs/runbook.md` and `docs/openclaw-integration.md` when the skill affects runtime/workflow

## Smoke Checks (Required)
- Add at least one deterministic smoke check (script or command) for non-trivial skills.
- Prefer no-network smokes when possible.
- If network/external API is required, document env prerequisites and safe failure behavior.
- Record smoke command and expected outcome in `docs/runbook.md`.

## Example Usage (Required)
Include at least 2 examples in `SKILL.md` or a referenced doc:
- one happy-path example
- one edge-case or failure-path example

## Rollback / Troubleshooting (Required)
- State how to disable or bypass the skill safely.
- Document common failure modes and fallback behavior.
- Avoid destructive rollback steps.

## Documentation Contract for Skill Changes
If a skill change affects behavior, routing, operator workflow, or commands, update:
- `docs/progress.md`
- `docs/runbook.md`
- `docs/openclaw-integration.md`
- `.openclaw/workspace/BOOTSTRAP.md` (workspace file is currently `.openclaw/workspace/bootstrap.md`)
- `.openclaw/workspace/HEARTBEAT.md` (workspace file is currently `.openclaw/workspace/heartbeat.md`)

Conditional (if impacted):
- `docs/cutover-checklist.md`
- `docs/release-notes-v1.0-draft.md`
- skill docs in `vault/.claude/skills/...` or `docs/skills/...`
- smoke checks in `scripts/*`

