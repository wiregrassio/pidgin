# Sprint Plan Writer — v0.4.1

You are writing the executable sprint plan (sprint.xml) for Pidgin v0.4.1.
This sprint has been through three review cycles. The design is solid. Your
job is to verify the intent one final time, then produce the sprint.xml
that `/run-sprint` will dispatch mission by mission.

## Phase 0: Read Everything

Read these files in this exact order. Do not skip any. Each builds on the
previous.

### Project context (what Pidgin is, how it works)
1. `.claude/CLAUDE.md` — project overview, structure, conventions
2. `.claude/mission-grammar.md` — the schema your output must conform to

### Sprint context (what happened, what the data says)
3. `local/sprints/tooling-v0.4.1/context/INDEX.md` — read order for context
4. `local/sprints/tooling-v0.4.1/context/v4.1-founding-record.md` — timeline
5. `local/sprints/tooling-v0.4.1/context/calibration-findings.md` — the data
6. `local/sprints/tooling-v0.4.1/context/convergence-rewrite.md` — the fix
7. `local/sprints/tooling-v0.4.1/context/v4-cherry-pick.md` — prior work
8. `local/sprints/tooling-v0.4.1/context/current-state.md` — repo now

### Design lineage (what was designed, what was wrong, what was fixed)
9. `local/sprints/tooling-v0.4.1/design.md` — original architect design
10. `local/sprints/tooling-v0.4.1/flaws.md` — hostile review (13 flaws)
11. `local/sprints/tooling-v0.4.1/design-final.md` — hardened design (all
    flaws resolved, then 5 more found and fixed by senior reviewer)
12. `local/sprints/tooling-v0.4.1/senior-review.md` — senior review

### Sprint infrastructure (what format to produce)
13. `local/templates/sprint.xml` — the XML template your output fills
14. `local/templates/log.md` — what /run-sprint writes per mission
15. `.claude/skills/new-sprint/SKILL.md` — the skill spec you're fulfilling
16. `.claude/skills/run-sprint/SKILL.md` — how your output gets consumed

### Reference sprint (what a real sprint.xml looks like)
17. `local/sprints/tooling-v0.4/sprint.xml` — v0.4's plan (18 missions,
    shipped M1-M5 GREEN before being killed). Read the first 3-4 missions
    to see the format, CDATA usage, and level of detail expected. Do NOT
    read all 18 — just enough to calibrate.

### Codebase verification (spot-check the claims)
Before writing, verify these against the actual source files. Don't trust
the design documents alone — the senior reviewer found flaws precisely
because earlier reviewers trusted claims without checking code.

- `src/pidgin/pipeline/geometry.py` — confirm `convergence_verdict()`
  exists (it will be deleted by M1)
- `src/pidgin/pipeline/batch.py` — confirm `FunctionMldResult` dataclass
  fields, `ADAPTIVE_MAX_BATCHES = 5`, `_extract_drafts()` shape
- `src/pidgin/verbs/index.py` lines ~515-532 — confirm
  `r.per_draft_tightness` access that M1 step 5 must fix
- `src/pidgin/verbs/index.py` line ~582 — confirm `[index] Converged:`
  output format that M2 depends on
- `src/pidgin/utils/api.py` lines ~284-349 — confirm `_one_anthropic_call`
  dead code that M6 deletes
- `src/pidgin/prompts/converge.xml` lines ~333-343 — confirm example ex20
  references `convergence_verdict` (M1 step 2 must update)
- `src/pidgin/pipeline/CLAUDE.md` lines ~42, ~95 — confirm
  `convergence_verdict` docs (M1 step 6 must update)
- `src/pidgin/pipeline/candidates.py` line ~86 — confirm hardcoded path
- `src/pidgin/prompts/templates.py` line ~96 — confirm hardcoded path

## Phase 1: Intent Verification

Before writing sprint.xml, answer these questions to yourself. If any
answer is "no" or "unclear," stop and report the issue instead of
writing a broken plan.

1. **Does each mission have everything it needs?** Walk M1 through M9
   in order. For each, ask: if I gave ONLY this mission block to a fresh
   agent, could it complete the work without guessing? Pay special
   attention to M1 (7 steps, 5 files + CLAUDE.md + grep verification)
   and M4 (receives M3's structured change list).

2. **Do the phase gates make sense?** Phase 1 gate: ≥ 70% convergence.
   Phase 2 gate: ≥ 60% convergence + queries working. Are these
   achievable given the calibration data?

3. **Is the dependency chain correct?** M1 → M2 (phase 1 gate) → M3 →
   M4 → M5 (phase 2 gate) → M6, M7, M8 (concurrent) → M9. Does any
   mission need information it won't have?

4. **Are the tiers right?** M1: execute, M2: execute, M3: reason,
   M4: execute, M5: execute, M6: execute, M7: execute, M8: execute,
   M9: scout. The reason tier gets M3 (architectural judgment about
   function complexity). Everything else is follow-the-spec execution
   or read-only verification.

5. **Are the reviews right?** M1: true (core pipeline rewrite), M3: true
   (reason-tier judgment), M4: true (behavior-changing refactors),
   M8: true (first external docs). M2, M5, M6, M7, M9: false.

## Phase 2: Write sprint.xml

Produce `local/sprints/tooling-v0.4.1/sprint.xml`.

### Format rules
- Well-formed XML. Parse-test with `python3 -c "import xml.etree.ElementTree as ET; ET.parse('local/sprints/tooling-v0.4.1/sprint.xml'); print('VALID')"` after writing.
- Wrap ALL mission content in `<![CDATA[...]]>` sections. The missions
  contain code blocks, shell commands, angle brackets, and special
  characters. Raw content will break XML parsing.
- Use the template structure from `local/templates/sprint.xml`.
- All paths relative to repo root. Source code lives in `src/pidgin/`.

### What goes into each mission element
The executor agent receives ONLY the `<mission>` element. It has no access
to design.md, flaws.md, or any other sprint document. Everything the
executor needs must be inside the mission block:

- `<context>`: What state the codebase is in when this mission starts.
  What prior missions delivered (summarize, don't reference). Why this
  mission exists. Enough that a fresh agent understands the situation.
- `<objective>`: Numbered list of what this mission delivers. Concrete
  and verifiable.
- `<specification>`: The detailed technical spec. File paths, function
  names, exact changes. For M1, this is the bulk of the content.
- `<steps>`: Ordered execution steps. Each step has RUN/EXPECT/FAIL.
  HARD fail = stop. SOFT fail = note and continue.
- `<report>`: What the structured report must include. This is the ONLY
  thing downstream missions see.

### Content source
The content for each mission comes from design-final.md. Transcribe
faithfully — do not summarize, reinterpret, or "improve" the specs.
The design has been through three review cycles. Your job is format
conversion (markdown → XML), not editorial judgment.

Specifically:
- M1 steps 1-7, report requirements → M1 mission element
- M2 steps 1-5, report requirements, phase gate → M2 mission element
- M3 steps 1-5, report requirements → M3 mission element
- M4 steps 1-5, report requirements → M4 mission element
- M5 steps 1-5, report requirements, phase gate → M5 mission element
- M6 steps 1-4, report requirements → M6 mission element
- M7 steps 1-6, report requirements, deferred list → M7 mission element
- M8 sections 1-7, constraints, report, reviewer instructions → M8
- M9 steps 1-7, report requirements → M9 mission element

### Decision points
Transcribe from design-final.md Decision Points section (DP1-DP4).
Include PD1-PD6 as pre-decisions (already resolved, stated for executor
context).

### Phase structure
Encode phase boundaries as XML comments between mission groups, like
the v0.4 sprint.xml does. Include the gate criteria in the comment.

## Phase 3: Verify

After writing sprint.xml:

1. **Parse test:** Run the Python XML parse command above. Must print
   VALID.

2. **Mission count:** 9 missions. Confirm the summary line matches.

3. **Attribute check:** Every `<mission>` has `n`, `tier`, `review`.
   Verify tier and review values match design-final.md.

4. **Completeness:** Every step from every mission in design-final.md
   appears in sprint.xml. Do a side-by-side check for M1 (the largest
   mission — 7 steps) and M7 (6 steps, most likely to have ordering
   errors from the renumbering).

5. **Self-containment:** Pick M4 and M5. Read each mission element in
   isolation. Could a fresh agent complete the work? M4 must explain
   the SIMPLIFY format it will receive. M5 must include the calibration
   reference numbers (102/19/5) since it can't access design.md.

6. **Grep traps:** M1 step 7 greps for `convergence_verdict` across
   `src/`. Confirm the mission includes steps to clean converge.xml
   example ex20 (step 2) and pipeline/CLAUDE.md (step 6) — without
   these, the grep fails and M1 halts.

Present the verification results. If all pass, state:
"Sprint plan ready. Run: /run-sprint local/sprints/tooling-v0.4.1/sprint.xml"
