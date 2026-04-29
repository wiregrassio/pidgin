---
name: new-sprint
description: >
  Create a sprint plan from a design document, then self-review for
  correctness. Reads the design doc and context files, writes the plan
  as well-formed XML, then adversarially reviews against the design.
---

# New Sprint

> **Model: Opus.** Sprint plan creation is single-shot architectural
> reasoning — decomposing a design into self-contained missions with
> correct dependency ordering.

You are the sprint plan writer AND reviewer. You read the design doc
and context material, produce a sprint plan as well-formed XML, then
adversarially review your own output.

## Invocation

```
/new-sprint <path-to-design-doc>
```

Example:
```
/new-sprint local/sprints/tooling-v0.4.1/design.md
```

## Sprint Package Layout

```
local/sprints/<sprint-name>/
├── design.md       # operator-authored input
├── context/        # reference material
├── sprint.xml      # produced by this skill
└── log.md          # produced by /run-sprint
```

## Workflow

### Step 1: Validate and Discover

1. Read the design doc at the provided path.
2. Confirm `context/` exists. Scan and read every file in it.
3. Check that `sprint.xml` does not already exist (ask to overwrite if it does).
4. Read `.claude/mission-grammar.md` — this defines the output format.

Present discovery results and ask: "Proceed with sprint plan creation?"

### Step 2: Write the Sprint Plan

Produce `<sprint-dir>/sprint.xml` — a well-formed XML document.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<sprint name="<sprint-name>" version="1">
  <summary>One-line goal. Number of missions.</summary>

  <decision_points>
    <dp id="1" default="<default>"><question></dp>
  </decision_points>

  <missions>
    <mission n="1" tier="execute" review="true">
      <context>...</context>
      <objective>...</objective>
      <specification>...</specification>
      <steps>...</steps>
      <report>...</report>
    </mission>
  </missions>
</sprint>
```

**Per mission:**
- Attributes: `n` (number), `tier` (scout|execute|reason), `review` (true|false)
- Inner tags: `<context>`, `<objective>`, `<specification>`, `<steps>`, `<report>`
- Each mission is self-contained — the executor sees ONLY the mission element
- Use CDATA sections for code blocks, shell commands, angle brackets
- All paths relative to repo root. Source code is in `src/pidgin/`.

**Tier assignment:**
- `scout` — read-only verification, structural checks
- `execute` — create/modify files, standard implementation
- `reason` — architectural judgment, complex integration, reviews

**Review assignment:**
- `review: true` — missions writing code where correctness matters
- `review: false` — scaffolding, documentation, cleanup

### Step 3: Verify

1. XML well-formedness: parse with Python xml.etree.ElementTree
2. Count missions matches summary
3. Every mission has n, tier, review attributes
4. Every design decision traces to at least one mission

### Step 4: Self-Review

Check against the design doc:
1. XML validity — parses cleanly, CDATA sections closed
2. Completeness — every design decision has a mission
3. Grammar conformance — matches .claude/mission-grammar.md
4. Internal consistency — dependencies flow correctly
5. Tier appropriateness — correct tier for each mission
6. Self-containment — executor can proceed from mission alone

Present: CLEAN or issues with severity (BLOCKING/WARNING).

### Step 5: Present

If clean: "Sprint plan ready. Run: /run-sprint <path>"
If issues: propose fixes, ask operator how to proceed.
