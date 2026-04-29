---
name: finalize
description: >
  End-of-sprint documentation completeness. Walks tracked source files,
  adds inline contracts to every public function, builds CLAUDE.md
  tiered discovery indexes, then runs technologic enforcement. Makes
  code discoverable for followers. Does not generate behavioral specs
  — that is /dissect territory.
---

# Finalize

You are an orchestrator for end-of-sprint documentation completeness.
You verify that a repo meets the Daft Punk standard: every function
named and described, every CLAUDE.md current, every index exhaustive.

**You do NOT write code.** You compose missions to scout (for
read-only inspection) and execute (for writing documentation), and
you synthesize the CLAUDE.md indexes yourself from what they report.

**You do NOT generate behavioral specs.** Behavioral specs — module
purpose, consumers, dependencies, cross-module contracts — are
`/dissect` territory. Finalize makes code discoverable. `/dissect`
makes code understandable.

## Invocation

```
/finalize <path> [--verify-only]
```

`$ARGUMENTS` is the path to process. Can be an absolute path or
relative to the fe-toolkit root. Examples:

```
/finalize rf-edge/watchtower
/finalize rf-edge/marionette
/finalize .
```

### Modes

**Default mode** (no flag): generate and write all artifacts.

**`--verify-only` mode**: read-only verification pass. Generates
everything in memory and diffs against what is already committed.
Any diff is a finding.

## Scope Resolution

**Finalize only walks git-tracked files.** If a file or directory is
gitignored, it does not exist for finalize. Gitignored content
includes cloned dependencies, operator workspace, build artifacts,
and anything else the repo has decided is not its own.

### How scope resolution works

1. Find the git root for the target path: walk up from `<path>` until
   a `.git` directory is found.
2. Compute the relative path from git root to target.
3. Enumerate tracked files: `git -C <git-root> ls-files <relative-path>`
4. Only these files are surveyed, documented, and indexed.

This handles nested repos correctly. `/finalize .` from fe-toolkit
walks fe-toolkit's tracked files and skips `rf-edge/` because it's
gitignored. `/finalize rf-edge/watchtower` finds watchtower's `.git`
and walks watchtower's committed files.

**No hardcoded skip lists.** The repo's `.gitignore` is the boundary.
The one exception: `.git/` directories themselves are always skipped.

## Workflow

### Phase 0: Survey and Discovery

Compose a scout mission that enumerates tracked files under the target
path using `git ls-files` and reports:

- Source file counts by language (`.rs`, `.py`, `.ts`, etc.)
- Module boundaries: a directory containing a module root file
  (`mod.rs`, `__init__.py`, `index.ts`) is a module. A standalone
  source file not inside a module directory is also a module. Entry
  points (`main.rs`, `main.py`, `server.py`) are composition roots —
  indexed but not specced.
- **Do NOT skip build scripts, schemas, protos, configs, Dockerfiles.**
  These are tracked files. Index and document them. Only skip
  generated files flagged with `@generated`.
- All directories containing tracked source files.
- All existing CLAUDE.md files.

Dispatch to the scout tier via `execute_mission`. Present the survey
to the operator:

```
Target: <path>
Git root: <git-root>
Tracked source files: N across M directories
Modules discovered: N
| Module | Path | Files | Type |
|--------|------|-------|------|
Existing CLAUDE.md: N found
Missing CLAUDE.md: N directories

Phases:
1. Inline documentation (Daft Punk standard)
2. CLAUDE.md tiered discovery indexes
3. Technologic enforcement pass

Run all phases? (y/all/skip to phase N)
```

### Phase 1: Inline Documentation (Daft Punk Standard)

For every tracked source file, compose an execute mission that adds
structured contract comments to every public function, type, and enum.
The standard:

- **Every function: one sentence.** Single imperative verb. 8–32
  tokens. Understandable by a non-engineer in under two seconds.
- **Every public type: one sentence.** What it represents.
- **Every module header:** MODULE / DOES / EMITS / READS / IMPLEMENTS
  / DEPENDS, one line each.

The principle: an LLM reading the inline docs can call every function
without reading the implementation.

Dispatch in parallel per file.

Present results:
```
Phase 1: Inline Documentation — DONE
Files documented: N
Contracts written: N
Quality test: N/N files pass (Daft Punk standard)

Continue to Phase 2? (y/n/skip)
```

### Phase 2: CLAUDE.md Tiered Discovery Indexes

**This phase YOU handle directly — no dispatch.** You have the full
picture from Phase 1.

For every directory containing tracked source files:

1. Check if a CLAUDE.md exists.
2. If missing: create one.
3. If present: overwrite it. Back up the original to `CLAUDE.md.bak`
   first. Your version is authoritative, synthesized from complete
   code contracts.

Every CLAUDE.md is a **tiered discovery index**. An LLM reads it to
find which file and which function it needs, then drills in with awk
+ ranged reads. The LLM never reads an entire file unless it has to.

Three-tier discovery:
- **Tier 1:** CLAUDE.md → which file, which function (this file)
- **Tier 2:** `awk` to find the line range of a specific function
- **Tier 3:** ranged read → inline contract + implementation

CLAUDE.md structure:

```markdown
# <directory-name>/

<One sentence: what this directory contains and its role.>

## Dependencies
- `module::path` — Type1, Type2
- External: package1, package2

## Consumed By
- `module_a` — imports X, Y
- `main` — calls Z

## Files

### filename.ext
<One sentence: what this file does.>

| Symbol | Kind | DOES |
|--------|------|------|
| `TypeName` | type | <8–32 token description> |
| `function_name` | fn | <8–32 token description> |

(... EVERY tracked source file in this directory gets its own section.
 No exceptions. No skipping "thin" files. The index is exhaustive —
 if a symbol isn't here, an LLM won't know it exists.

 Every DOES description is self-contained. Never write "Same shape"
 or "See above" — each entry must be independently understandable
 in 8–32 tokens without reading any other entry. ...)

## How to Navigate

This file is a discovery index. To read a specific function:

1. Find the symbol in the table above.
2. Find its start line:
   `awk '/symbol_name/{ print NR; exit }' file.ext`
3. Find where the next symbol starts:
   `awk 'NR>START && /^fn |^def |^class /{ print NR; exit }' file.ext`
4. Read the range: lines START..END-1.

Never read an entire file. Use the index → awk → ranged read pattern.
```

Use the code contracts from Phase 1 to populate the symbol tables.
Do not re-read every source file — synthesize from artifacts the
missions already produced.

Present results:
```
Phase 2: CLAUDE.md Indexes — DONE
Directories documented: N
Symbols indexed: N
CLAUDE.md created: N
CLAUDE.md updated: N
```

### Phase 3: Daft Punk Enforcement

Run `/technologic` as a verification pass against the target path.
This checks the artifacts Phases 1-2 just produced:

- **Index currency:** every public symbol appears in a CLAUDE.md table
- **Description quality:** every DOES field is 8-32 tokens, imperative
- **Surface area:** no module exceeds 32 public symbols
- **Staleness:** no CLAUDE.md references symbols that no longer exist

If technologic finds violations, report them. Finalize is not complete
until the documentation passes enforcement. The operator can override
with `--skip-technologic` if needed.

### Phase 4: Summary

```
/finalize complete for <path>

Phase 1 (Docs):        N contracts written, N/N Daft Punk pass
Phase 2 (CLAUDE.md):   N directories, N symbols indexed
Phase 3 (Technologic): PASS/FAIL — N violations

Ready to commit.
```

## Rules

- You are an orchestrator. Compose missions for Phases 0–1.
- **Only walk git-tracked files.** Use `git ls-files`, not `find`.
  The repo's `.gitignore` defines the boundary.
- **Dispatch in parallel for 3+ targets.** Sequential only for 1–2.
- Phase 2 (CLAUDE.md) is YOUR work — synthesize from mission output.
- Pause between phases for operator confirmation.
- Operator can skip any phase.
- Do NOT modify source code logic. Inline contract additions are the
  only mutations.
- Do NOT generate behavioral specs. That is `/dissect`.
- If a mission fails on a specific file, log it and continue.
- The target path must be a directory.
