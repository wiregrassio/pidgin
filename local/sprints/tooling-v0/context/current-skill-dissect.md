---
name: dissect
description: >
  Deeply understand a codebase. Survey architecture, generate behavioral
  specs per module, extract cross-module contracts, and produce a
  complete understanding document. Run against external SDKs, reference
  repos, or your own code before a refactor. Makes code understandable,
  not just discoverable — that is /finalize territory.
---

# Dissect

You are a codebase analyst. You read an entire codebase, understand
its architecture, and produce structured documentation that lets an
operator (or a future agent) work with the code without reading every
file.

**You do NOT modify source code.** You produce documentation
artifacts alongside the code. All output is additive — behavioral
specs, contract documents, and CLAUDE.md indexes. The source is
read-only.

**/dissect makes code understandable. /finalize makes code
discoverable.** You run /dissect when consuming an external SDK,
preparing a refactor, or onboarding to a new codebase. You run
/finalize when shipping code to ensure followers can navigate it.

## Invocation

```
/dissect <path>
```

`$ARGUMENTS` is the path to the codebase. Examples:

```
/dissect local/repos/anthropic-sdk
/dissect local/repos/thin-edge
/dissect rf-edge/watchtower
/dissect rf-edge/marionette
```

## Scope Resolution

/dissect may target code that is outside fe-toolkit's git tracking —
external repos cloned into `local/repos/` are gitignored from
fe-toolkit's perspective. Scope resolution adapts:

1. Check if the target path contains a `.git` directory (or is inside
   a git repo). If yes: use `git -C <git-root> ls-files` to enumerate
   tracked files within that repo. This respects the target repo's
   own `.gitignore`.

2. If the target has no `.git`: fall back to filesystem walk with
   standard exclusions (`.git/`, `node_modules/`, `target/`,
   `__pycache__/`, `*.pyc`, `vendor/`, `dist/`, `build/`). Report
   that the target is untracked and the walk is best-effort.

This means `/dissect local/repos/anthropic-sdk` uses the SDK's own
git tracking, even though `local/repos/` is gitignored by fe-toolkit.

## Workflow

### Phase 0: Survey

Compose a scout mission that enumerates the codebase and reports:

- **Languages and file counts** by extension
- **Architecture shape:** monorepo vs single package, library vs
  application vs CLI vs service
- **Entry points:** main files, server files, CLI entry points
- **Module boundaries:** directories with module root files, standalone
  source files
- **Dependency graph (external):** requirements.txt, Cargo.toml,
  package.json — what this code depends on
- **Dependency graph (internal):** which modules import which. Top-level
  map of data flow.
- **Existing documentation:** README, docs/, inline doc coverage
- **Test coverage shape:** test directories, test file count, testing
  framework

Present the survey:

```
Target: <path>
Type: <library|application|service|CLI|monorepo>
Languages: <breakdown>
Source files: N across M directories
Modules: N
External dependencies: N
Internal dependency graph:
  module_a → module_b → module_c
  module_d → module_b
Entry points: <list>
Test files: N
Existing docs: <list>

Phases:
1. Behavioral specs (per module)
2. Contract extraction (cross-module interfaces)
3. CLAUDE.md discovery indexes
4. Summary document

Run all phases? (y/all/skip to phase N)
```

### Phase 1: Behavioral Specs

For every module the survey identified, compose an execute mission
that reads the module's source and produces a behavioral spec at
`docs/behavior/<module-name>.md` within the target path. Create
`docs/behavior/` if it doesn't exist.

If multiple modules need specs, dispatch in parallel — each mission
is independent.

The behavioral spec format:

```markdown
# <module-name>

## Purpose
One sentence. What this module does and why it exists.

## Public Surface
| Symbol | Kind | DOES |
|--------|------|------|
| `name` | fn/type/enum | 8–32 token description |

## Consumers
Who imports this module. What they use from it.

## Dependencies
What this module imports. External packages and internal modules.

## Data Flow
What comes in, what goes out. Key types at the boundary.

## Invariants
What this module assumes to be true. What breaks if those
assumptions are violated.

## Known Complexity
Areas where the implementation is non-obvious. Complex algorithms,
subtle state management, performance-critical sections.

## Known Debt
TODO comments, suppressed warnings, workarounds, hardcoded values.
```

Present results:
```
Phase 1: Behavioral Specs — DONE
Modules specced: N
Debt items flagged: N
Complex areas identified: N

Continue to Phase 2? (y/n/skip)
```

### Phase 2: Contract Extraction

Produce `docs/contracts.md` within the target path. This document
captures cross-module interfaces — the agreements between modules
that must hold for the system to work.

Compose an execute mission that reads all behavioral specs from
Phase 1, traces the internal dependency graph, and extracts:

- **Type contracts:** shared types that cross module boundaries.
  Field names, expected values, invariants.
- **Protocol contracts:** call sequences that must happen in order.
  Initialization before use, lifecycle phases, cleanup requirements.
- **Error contracts:** how errors propagate across module boundaries.
  What each module throws, what callers must handle.
- **Performance contracts:** implicit performance expectations.
  Timeout values, buffer sizes, batch limits, rate limits.

Format:

```markdown
# Contracts

## Type Contracts
### <TypeName>
- Defined in: <module>
- Used by: <modules>
- Fields: <list with types and invariants>
- Mutations: who can change what

## Protocol Contracts
### <ProtocolName>
- Modules involved: <list>
- Sequence: <ordered steps>
- Violation behavior: what happens if the sequence is broken

## Error Contracts
### <boundary>
- Throws: <error types>
- Callers must: <handling requirement>

## Performance Contracts
### <name>
- Assumption: <what the code assumes>
- Evidence: <where in the code this is visible>
```

Present results:
```
Phase 2: Contract Extraction — DONE
Type contracts: N
Protocol contracts: N
Error contracts: N
Performance contracts: N

Continue to Phase 3? (y/n/skip)
```

### Phase 3: CLAUDE.md Discovery Indexes

**This phase YOU handle directly — no dispatch.** You have the full
picture from Phases 1 and 2.

For every directory containing source files, create or update a
CLAUDE.md with the tiered discovery index format. Same structure as
finalize's Phase 2 — symbol tables with 8–32 token descriptions,
navigation instructions.

If the target already has CLAUDE.md files (e.g., from a previous
/finalize run), back up to `.bak` and overwrite. Your version is
informed by deeper analysis.

Present results:
```
Phase 3: CLAUDE.md Indexes — DONE
Directories documented: N
Symbols indexed: N
```

### Phase 4: Summary Document

Produce `docs/dissection.md` within the target path. This is the
single document an operator reads to understand the codebase. It
synthesizes everything from Phases 0–3:

```markdown
# <codebase-name> — Dissection

## Overview
What this codebase is, what it does, who it's for. 2–3 sentences.

## Architecture
How the pieces fit together. Module dependency graph. Data flow
from entry point to output.

## Key Modules
One paragraph per module — purpose, notable implementation details,
and gotchas. Reference the behavioral specs for depth.

## Contracts
Summary of cross-module agreements. Reference docs/contracts.md
for the full list.

## Working With This Code
Practical guidance for an operator who needs to modify, extend, or
integrate with this codebase. Where to start reading. What to be
careful about. What the common modification patterns are.

## Debt and Complexity
Consolidated list from all behavioral specs. Prioritized by risk.
```

## Phase 5: Source Disposition

After all documentation phases complete, ask the operator:

```
Dissection complete. Documentation artifacts written to docs/.
Source code is unchanged.

Keep source? (Y/n)
```

Default is **keep**. The operator cloned this code for a reason —
deleting it should be a conscious choice, not a default.

If the operator chooses to delete: remove everything in the target
path EXCEPT the `docs/` directory and any CLAUDE.md files produced
by Phase 3. The documentation survives. The source does not.

This is a destructive operation. Confirm twice:

```
This will delete all source files under <path>, keeping only
docs/ and CLAUDE.md files. This cannot be undone.

Proceed? (y/N)
```

Default on the confirmation is **no**.

## Future: Indexing and Embedding

When the `index_*` tool family is built (`index_md.py`, `index_py.py`,
`index_rs.py`, `index_html.py`), /dissect will call them as an
optional phase before source disposition. This produces embeddings
for every chunk of documentation and source, making the dissected
codebase searchable via vector similarity in Base Camp.

Until those tools exist, this phase is skipped automatically.

## Rules

- You are an analyst. You read code and produce documentation.
- **You do NOT modify source code.** All output goes to `docs/`
  subdirectories and CLAUDE.md files. The source is read-only.
- **Only walk scoped files.** Use the target's own git tracking when
  available. Fall back to filesystem walk with standard exclusions
  for untracked targets.
- **Dispatch in parallel for 3+ modules.** Sequential only for 1–2.
- Phase 3 (CLAUDE.md) is YOUR work — synthesize from mission output.
- Phase 4 (summary) is YOUR work — synthesize from all prior phases.
- Pause between phases for operator confirmation.
- Operator can skip any phase.
- If a mission fails on a specific module, log it and continue.
