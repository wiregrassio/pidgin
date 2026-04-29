# One-Shot: Local Agent Infrastructure

You are fixing the dispatch infrastructure for a sprint that's about to
run. The agent files and mission grammar were copied from a container
environment (Marionette) and contain container-specific paths and framing
that don't apply to local Claude Code task dispatch. You are forking them
for local use.

## Project Root

The project root is: `/Users/elliotwillis/Desktop/fe-toolkit`

All paths below are relative to this root unless absolute.

## What You Do

### 1. Copy and adapt mission-grammar.md

Copy `rf-edge/marionette/mission-grammar.md` to `.claude/mission-grammar.md`.

In the local copy, make these changes:
- Remove all references to "Marionette container" and "container."
  Replace with "your working environment" or just remove the framing.
- In the "Path Conventions" section: replace the `/project` convention
  with the actual project root path. The key sentence should read:
  "All paths in missions are relative to the project root at
  `/Users/elliotwillis/Desktop/fe-toolkit`." Remove the sentence about
  the container not seeing the host filesystem.
- In the "Review missions" section: change `/app/.claude/skills/` to
  `.claude/skills/`.
- Remove any other `/app/` references.
- Leave the grammar itself (step types, EXPECT/FAIL, report format,
  phases, conventions) completely untouched. That's universal.

### 2. Rewrite .claude/agents/execute.md

Keep the YAML frontmatter (name, model, effort, description) identical.

Rewrite the body:
- Remove "You are a mission executor inside a Marionette container."
  Replace with: "You are a mission executor running as a Claude Code
  task. You have full access to the project filesystem."
- Change the mission grammar reference from `/app/mission-grammar.md`
  to `.claude/mission-grammar.md`.
- Add a "Project Root" section after the grammar reference:
  ```
  ## Project Root
  
  The project lives at `/Users/elliotwillis/Desktop/fe-toolkit`.
  All paths in the mission spec are relative to this root. When the
  mission says `/project/pidgin/cli.py`, that means
  `/Users/elliotwillis/Desktop/fe-toolkit/pidgin/cli.py`.
  ```
- Keep ALL of the tier-specific rules, the "What you do" / "What you
  do NOT do" sections, and the behavioral guidance. These are universal
  and correct. Only the container framing changes.

### 3. Rewrite .claude/agents/reason.md

Same pattern as execute.md:
- Keep YAML frontmatter identical.
- Remove container framing.
- Add mission grammar and project root references.
- Keep all tier-specific rules and judgment calibration guidance intact.

### 4. Rewrite .claude/agents/scout.md

Same pattern:
- Keep YAML frontmatter identical.
- Remove container framing.
- Add mission grammar and project root references.
- Keep all tier-specific rules intact.

### 5. Update .claude/agents/CLAUDE.md

Replace the current content. The new CLAUDE.md should state:
- These agent files are for local Claude Code task dispatch.
- They were originally derived from `rf-edge/marionette/.claude/agents/`
  but are now an independent lineage. Do not sync from Marionette.
- The Marionette canonical agents remain at
  `rf-edge/marionette/.claude/agents/` for container dispatch.
- Changes to local agents go here. Changes to container agents go in
  Marionette.
- Keep the agent table (scout/execute/reason with models and descriptions).
- Reference `.claude/mission-grammar.md` as the local grammar.

### 6. Update sprint.xml paths

In `local/sprints/tooling-v0.4/sprint.xml`:
- Replace every occurrence of `/project/` with the actual project root
  path `/Users/elliotwillis/Desktop/fe-toolkit/`.
- Do NOT change anything else in the file. No structural changes, no
  mission rewrites. Just the path substitution.

### 7. Reset the execution log

Delete `local/sprints/tooling-v0.4/log.md`. The sprint will restart
from M1. The previous M1 execution wrote to container paths and
produced no actual changes — the GREEN status was false.

## Verification

After all changes:

1. Confirm no `/app/` references remain in `.claude/agents/*.md` or
   `.claude/mission-grammar.md`:
   ```
   grep -r "/app/" .claude/
   ```
   Expected: 0 matches.

2. Confirm no "Marionette container" references in `.claude/agents/*.md`:
   ```
   grep -ri "marionette container" .claude/agents/
   ```
   Expected: 0 matches.

3. Confirm `/project/` is replaced in sprint.xml:
   ```
   grep -c "/project/" local/sprints/tooling-v0.4/sprint.xml
   ```
   Expected: 0.

4. Confirm mission-grammar.md exists locally:
   ```
   test -f .claude/mission-grammar.md && echo PASS
   ```

5. Confirm log.md is deleted:
   ```
   test ! -f local/sprints/tooling-v0.4/log.md && echo PASS
   ```

## What You Do NOT Change

- `rf-edge/marionette/.claude/agents/` — the Marionette canonical source
  stays untouched. That's a different lineage now.
- `rf-edge/marionette/mission-grammar.md` — same, don't touch.
- `local/sprints/tooling-v0.4/design.md` — the design is fine.
- `local/sprints/tooling-v0.4/sprint.xml` — only path substitution,
  no structural changes.
- Any file outside `.claude/`, `local/sprints/tooling-v0.4/sprint.xml`,
  and `local/sprints/tooling-v0.4/log.md`.
