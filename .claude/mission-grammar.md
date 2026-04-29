# Mission Grammar

Standard structure for sprint missions. Every mission follows this schema.

## Mission Block

```xml
<mission id="M1" title="Short title" tier="execute|reason|scout" review="true|false">
  <context>
    What the executor needs to know before starting. Prior missions this
    depends on. State of the codebase. Why this mission exists.
  </context>

  <objective>
    One sentence. What this mission delivers.
  </objective>

  <specification>
    <step id="1">
      RUN: What to do. Be specific — file paths, function names, exact behavior.
      EXPECT: What success looks like. Measurable, not vibes.
      FAIL: HARD (stop the mission) or SOFT (note and continue)
    </step>
    <step id="2">
      ...
    </step>
  </specification>

  <report>
    What the executor must document when done. This is the ONLY thing the
    next mission's agent sees from this mission (plus the spec). If it's
    not in the report, it didn't happen.
  </report>
</mission>
```

## Tiers

**execute** (Sonnet-class): Implementation, file modification, testing.
Most missions. The agent follows the spec literally. If the spec is
ambiguous, it stops and asks — it doesn't interpret.

**reason** (Opus-class): Architectural judgment, gate decisions, ambiguity
resolution. Used when the mission requires weighing tradeoffs. The agent
may deviate from the spec if it documents why.

**scout** (cheap/fast model): Read-only audits, verification passes,
compliance scans. Zero side effects.

## Review

Missions with `review="true"` get a separate review agent after execution.
The reviewer sees the executor's report and the original spec. Produces:
- **PASS** — no issues
- **CONCERNS** — non-blocking findings, carry forward
- **FAIL** — critical issues, requires patch and re-review

## Per-Mission Agent Termination

Each mission runs in a fresh agent context. The agent executes, writes
its report to log.md, and terminates. The next agent receives:
- Its own mission spec
- The risk review section for its mission (if any)
- Pre-decisions and amendments that affect it
- Report sections from missions it directly depends on

If an agent can't proceed from this information alone, the report from
the prior mission is insufficient — that's a design problem.

## Amendments

Issued by the commander when a spec needs revision mid-sprint. Numbered
sequentially (A1, A2...). Recorded in log.md. Applied to the affected
mission before re-dispatch.

## Pre-Decisions

Ambiguities resolved by the commander before the sprint starts. Numbered
PD1, PD2... Executors apply them as stated — they don't re-decide.

## Known Exceptions

Design constraints intentionally violated, blessed by the commander.
Numbered KE1, KE2... Referenced in the affected mission's report.

## Carry-Forwards

Issues found during execution that are out of scope. Logged in the
mission report with a CF tag. The cleanup mission addresses them.
Anything unresolved becomes a next-sprint item.

## Patches

When a mission fails review, the commander issues a patch spec. The
executor applies the patch and the reviewer re-reviews. Patches are
scoped to the specific findings — not a full re-execution.

## Phase Gates

Each phase must be fully GREEN before the next phase dispatches.
Phase boundaries are where the commander reviews cumulative status.
