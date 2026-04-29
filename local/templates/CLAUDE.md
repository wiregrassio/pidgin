# templates/sprint-package/

Sprint lifecycle package templates. Copy the entire directory to `local/sprints/<n>/` to start a new sprint.

## Files

### design.md
Operator-authored sprint design document — the input to `/new-sprint`.

| Symbol | Kind | DOES |
|--------|------|------|
| `design.md` | template | Capture sprint goal, decisions, constraints, and scope for the sprint plan writer. |

### sprint.xml
Well-formed XML sprint plan — produced by `/new-sprint`, consumed by `/run-sprint`.

| Symbol | Kind | DOES |
|--------|------|------|
| `sprint.xml` | template | Organize missions as `<mission>` XML elements with tier, review attributes and inner spec tags. |

### log.md
Incremental execution log — produced and appended by `/run-sprint`.

| Symbol | Kind | DOES |
|--------|------|------|
| `log.md` | template | Record each mission result (GREEN/RED), findings, and files written for compaction resilience. |

### behavior.md
Finalized behavioral spec — produced by `/finalize` at sprint close.

| Symbol | Kind | DOES |
|--------|------|------|
| `behavior.md` | template | Document verified post-sprint behavior: what the system now does, contracts, and known debt. |

## Sprint Package Lifecycle

| Artifact | Produced by | Indicates |
|----------|-------------|-----------|
| design.md only | operator | planned, not yet scoped |
| sprint.xml exists | /new-sprint | scoped, not yet executed |
| log.md exists | /run-sprint | execution in progress or complete |
| behavior.md exists | /finalize | finalized and verified |
