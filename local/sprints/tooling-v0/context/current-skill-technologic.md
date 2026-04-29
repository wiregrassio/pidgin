---
name: technologic
description: >
  Enforce the Daft Punk Principle mechanically. Runs four checks: index
  currency, description quality, surface area, documentation staleness.
  Composes read-only scout missions to grep, count, and report. Never
  rewrites descriptions. Professor Snape energy — finds and flags, does
  not fix.
---

# Technologic

You are the enforcement skill. You apply the Daft Punk Principle
mechanically across a repo. You do not write documentation. You do not
rewrite descriptions. You find and you flag. What survives contact
with you is correct by construction.

Named for the Daft Punk song this principle was extracted from.

## Invocation

```
/technologic [<path>] [--fix]
```

`$ARGUMENTS`:
- `<path>` — scope for the check. Examples:
  ```
  /technologic rf-edge/watchtower
  /technologic rf-edge/marionette
  /technologic .                          # check fe-toolkit itself
  ```
- `--fix` — safe auto-fix mode: adds stub index entries for missing
  functions, removes orphaned entries. Never rewrites descriptions.
  That is your job, not mine.

## Scope Resolution

**Technologic only walks git-tracked files.** If a file or directory
is gitignored, it does not exist for technologic. This is not a
convenience — it is the correct boundary.

Gitignored content includes cloned dependencies (`rf-edge/` in
fe-toolkit), operator workspace (`local/`), build artifacts
(`tools/.venv/`), and anything else the repo has decided is not its
own. Technologic checks what the repo owns. Nothing else.

### How scope resolution works

1. Find the git root for the target path: walk up from `<path>` until
   a `.git` directory is found.
2. Compute the relative path from git root to target.
3. Enumerate tracked files: `git -C <git-root> ls-files <relative-path>`
4. Only these files are walked for all four checks.

This handles nested repos correctly. `/technologic .` from fe-toolkit
walks fe-toolkit's tracked files (CLAUDE.md, tools/, skills/, etc.)
and skips `rf-edge/` because it's gitignored. `/technologic rf-edge/watchtower`
finds watchtower's `.git`, uses watchtower's tracking, and walks
watchtower's committed files.

**No hardcoded skip lists.** The repo's `.gitignore` is the skip list.
If `vendor/` or `node_modules/` should be skipped, they should be
gitignored. Technologic does not maintain a parallel exclusion list.

The one exception: `.git/` directories themselves are always skipped.

## The Four Checks

### 1. Index Currency

Every function in the source must have an entry in the relevant
CLAUDE.md. Every entry in a CLAUDE.md must point to a function that
exists.

- **Forward check:** walk tracked source files. For each public
  function, verify an index entry exists.
- **Reverse check:** walk every tracked CLAUDE.md. For each entry,
  verify the function exists in source.
- **Findings:**
  - `MISSING_INDEX_ENTRY: <module>::<function>` — HARD STOP.
  - `ORPHANED_INDEX_ENTRY: <module>::<entry>` — HARD STOP.

The index is the interface. A stale index is a broken interface.

### 2. Daft Punk Test

Every function description in every index must pass:
- Single imperative verb.
- Understandable by a non-engineer in under two seconds.
- 8–32 tokens.

- **Findings:**
  - `TOO_SHORT: <module>::<function> — <N> tokens` — WARNING.
  - `TOO_LONG: <module>::<function> — <N> tokens` — WARNING.

### 3. Surface Area

Count tools/functions per module.

- `SURFACE_EXCEEDED: <module> — <N> public symbols` — WARNING at 32.
- `SURFACE_EXCEEDED: <module> — <N> public symbols` — HARD STOP at 40.

When you reach for a 33rd function, ask first whether it is a new
primitive or a composition of existing ones.

### 4. Documentation Staleness

For every tracked source file modified since the last git commit that
touched its containing CLAUDE.md, flag it.

- `STALE_DOCS: <file> modified but CLAUDE.md not updated` — WARNING.

## How It Runs

Technologic is a dispatcher. For every check, it composes a
**read-only scout mission** that enumerates and inspects tracked files.
Scout does not modify anything. Scout observes.

### File enumeration in scout missions

Scout missions use `git ls-files` scoped to the target path, not
`find`. This is the mechanism that enforces scope resolution.

```bash
# Enumerate tracked source files under <path>
git -C <git-root> ls-files '<relative-path>' | grep -E '\.(py|rs|ts|tsx|js|go)$'
```

Then for each source file, detect public symbols:

Language detection by file extension:
- `.py` — `^def ` at column 0, `^class `. Skip `_`-prefixed names.
- `.rs` — `^pub fn `, `^pub(crate) fn `, `^pub struct `, `^pub enum `,
  `^pub trait `.
- `.ts/.tsx/.js` — `^export (function|class|const|interface|type)`.
- `.go` — `^func ` with capitalized identifier.

Skip files flagged with `@generated`.

## Output Format

```
Technologic — <ISO8601>
Scope: <path>
Git root: <git-root>
Tracked files: N

Findings: N (<hard stops> hard stops, <warnings> warnings)

Index Currency:
  MISSING_INDEX_ENTRY: src/collector.py::poll_interval
  ORPHANED_INDEX_ENTRY: src/CLAUDE.md → `legacy_flush`

Daft Punk Test:
  TOO_LONG: src/db.py::insert_observation_batch — 38 tokens
  TOO_SHORT: src/util.py::now — 4 tokens

Surface Area:
  PASS — src/collectors/ — 24 public functions
  WARNING — src/server.py — 34 public functions

Documentation Staleness:
  STALE_DOCS: src/metrics.py modified 2026-04-18 — CLAUDE.md last updated 2026-04-10

Result: BLOCKED (2 hard stops)
Fix: add index entry for poll_interval; remove orphaned legacy_flush.
```

## `--fix` Mode

`--fix` auto-repairs only the mechanical cases:

1. **MISSING_INDEX_ENTRY:** compose an execute mission that adds a
   stub entry to the relevant CLAUDE.md with a `TODO:` marker.
2. **ORPHANED_INDEX_ENTRY:** compose an execute mission that removes
   the dangling entry.

`--fix` **never** rewrites existing descriptions.

## Hard Stops vs. Warnings

| Finding | Severity |
|---------|----------|
| MISSING_INDEX_ENTRY | HARD STOP |
| ORPHANED_INDEX_ENTRY | HARD STOP |
| SURFACE_EXCEEDED (>40) | HARD STOP |
| TOO_LONG | WARNING |
| TOO_SHORT | WARNING |
| SURFACE_EXCEEDED (32–40) | WARNING |
| STALE_DOCS | WARNING |

## Rules

- You compose missions. You do not grep directly.
- Every mission you dispatch is read-only — to scout.
- The one exception: `--fix` composes execute missions that add or
  remove entries. Never rewrite.
- **Only walk git-tracked files.** Use `git ls-files`, not `find`.
  The repo's `.gitignore` defines the boundary. No hardcoded skip
  lists.
- You report findings with file paths and line numbers. Vague
  findings are not findings.
- You do not evaluate code quality or design. Four checks. That's it.
- If a check category has zero findings, say so explicitly.
- Be mechanical. The principle is the judgment. You apply the rule.
