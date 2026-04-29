# Tooling Sprint v0.4.1 — Senior Review

**Reviewer:** Senior quality gate  
**Date:** 2026-04-29  
**Inputs:** design.md, flaws.md, design-final.md, all context documents, live codebase verification

---

## Missed Flaws

Flaws the hostile reviewer should have caught but didn't.

---

FLAW-14: M1 step 6 grep catches non-code files — M1 will FAIL HARD on its own verification
Severity: SERIOUS
Mission: M1

The problem: M1 step 6 runs `grep -rn "convergence_verdict" src/` and expects empty output. After M1's code changes (geometry.py, batch.py, mld.py), four matches remain that M1 does not address:

- `src/pidgin/prompts/converge.xml:339` — example code: `return convergence_verdict(centroid)`
- `src/pidgin/prompts/converge.xml:342` — `<why>` tag: `convergence_verdict`
- `src/pidgin/pipeline/CLAUDE.md:42` — symbol table documents `convergence_verdict`
- `src/pidgin/pipeline/CLAUDE.md:95` — section header: `## convergence_verdict Draft-Decay Test`

M1 step 2 (converge.xml) says to change the schema and role section, remove duplicate examples, and fix the contradictory role section. It does NOT say to update example ex20 (lines 333–343) which uses `convergence_verdict` in its sample code and `<why>` explanation. No step mentions pipeline/CLAUDE.md at all.

Consequence: M1's execute-tier agent reaches step 6, runs the grep, gets 4 hits, hits FAIL: HARD. The spec doesn't cover these files. An execute-tier agent "follows the spec literally" and "if the spec is ambiguous, it stops and asks." The sprint halts at M1 before it begins.

Fix: Add to M1 step 2: "Update or remove example ex20 (lines ~333–343) which references `convergence_verdict` in sample code and explanation — replace with `is_converged` or remove the example." Add a new step or note: "Update `src/pidgin/pipeline/CLAUDE.md`: remove the `convergence_verdict` row from the geometry.py symbol table, delete the `## convergence_verdict Draft-Decay Test` section, and add `is_converged` to the table."

---

FLAW-15: M7 misses hardcoded path in templates.py — M9 will report ISSUES FOUND
Severity: SERIOUS
Mission: M7, M9

The problem: `src/pidgin/prompts/templates.py:96` contains:
```python
origami_path="/Users/elliotwillis/Desktop/fe-toolkit/ORIGAMI.md"
```

M7 only cleans hardcoded paths in `candidates.py`. M9 step 6 runs `grep -r "/Users/elliotwillis" src/` — this will match templates.py. M9 is a scout (read-only) and cannot fix it. M9 will report ISSUES FOUND, blocking the v0.4.1 tag.

Consequence: The sprint completes all 8 prior missions, reaches the final verification, and fails on a one-line fix that should have been in M7's scope. The operator must issue a patch, adding an unplanned mission or amendment.

Fix: Add templates.py to M7 step 1 (or add a new step):
"**Hardcoded path in templates.py** (`src/pidgin/prompts/templates.py`, line ~96): contains `/Users/elliotwillis/Desktop/fe-toolkit/ORIGAMI.md`. Replace with `None` or a relative path lookup. EXPECT: No `/Users/elliotwillis` paths in templates.py. FAIL: SOFT."

---

FLAW-16: M7 claims two hardcoded paths in candidates.py but there is only one
Severity: MINOR
Mission: M7

The problem: M7 step 1 says "Lines ~86, ~96 contain `/Users/elliotwillis/Desktop/fe-toolkit/...` paths." Verified against the codebase: line 86 has the path (`audit_path` default). Line 96 is the `expand_ratio` threshold comment — no hardcoded path. There is only one path to fix in candidates.py.

Consequence: The executor looks for a second path at line ~96, doesn't find it, notes it and moves on. No functional impact, but it suggests the designer didn't read the file carefully.

Fix: Change "Lines ~86, ~96" to "Line ~86" in M7 step 1.

---

FLAW-17: M4 step 5 dry-run claim is wrong — PD6 gate was removed from the code
Severity: SERIOUS
Mission: M4 (introduced by FLAW-8 fix)

The problem: M4 step 5 says: "Run `pidgin index src/pidgin --sync` (without `--write-db`, which is the dry-run mode per PD6) to exercise the pipeline without writing to the nest."

PD6 states: "`index` without `--write-db` is the dry-run mode — zero API calls."

But the actual code (index.py line 2): `# v0.2: default behaviour is WRITE (PD6 dry-run gate removed).` The `--write-db` flag exists in cli.py but is never referenced in index.py. The actual dry-run gate is the `--dry-run` flag (index.py line 307). Running `pidgin index src/pidgin --sync` without `--dry-run` triggers the full live pipeline — API calls, embedding, the works.

Two failure modes:
1. The executor runs the command, sees real API calls being made, and is confused because PD6 said "zero API calls." They may halt.
2. The command succeeds but burns API budget on ~126 functions (1260+ API calls at 10 calls/function) when the intent was a costless check.

Consequence: Either M4 halts on confusion or spends unexpected API money. Neither is the design's intent.

Fix: If the goal is truly zero API calls: change to `pidgin index src/pidgin --dry-run`. But `--dry-run` only counts files and estimates cost — it doesn't exercise the pipeline. If the goal is to exercise the pipeline (catch runtime import/attribute errors), either: (a) accept the API cost and remove the "dry-run" claim, or (b) add a lighter verification: `python -c "from pidgin.pipeline.batch import run_embedding_mld_pipeline_for_functions; from pidgin.pipeline.mld import mld"` to verify imports resolve. The current step tries to do both (exercise pipeline + zero cost) and achieves neither cleanly.

Also: PD6 in the design-final.md is factually wrong about the codebase. Update PD6 to reflect reality: "`index --dry-run` is the preview mode (zero API calls). The `--write-db` gate was removed in v0.2."

---

FLAW-18: M2 asks for sv values of 5 divergent functions but sv is not stored in nest or printed in output
Severity: MINOR
Mission: M2

The problem: M2 step 4 says each divergent function should have `sv > 0.10`. M2 step 5 says to document "the sv values for the 5 known divergents." But:
- The nest stores `converged` (bool) but not `sv` (float) — verified at `nest.py:940–954`
- The index verb's output doesn't print sv values (not in regular or verbose mode)
- M1 step 5 adds `sv={r.sv:.4f}` to the verbose chunk callback output for CONVERGED functions only — divergent functions get `(not converged, cluster=...)` without sv

The executor can verify `converged=False` from nest metadata, but cannot retrieve the actual sv float.

Consequence: M2's report will be incomplete — it will confirm converged=False for the 5 functions but cannot provide exact sv values. The gate check still works (converged=False implies sv ≥ 0.10 by definition), so Phase 1 proceeds. But the report doesn't match the spec.

Fix: Either (a) have M1 also add sv to the not-converged verbose output line, or (b) change M2 step 4/5 to require only `converged=False` (not exact sv values) since that's sufficient for the gate. Option (b) is simpler and loses nothing meaningful.

---

## Flaw Fix Audit

| Flaw | Severity | Claimed Fix | Actually Fixed? | Notes |
|------|----------|-------------|-----------------|-------|
| FLAW-1 | BLOCKING | Removed Anthropic references from M6, added delete step + grep | **Yes** | M6 now correctly targets two OpenAI paths. `_one_anthropic_call` deletion added with grep verification scoped to api.py. Verified: dead code exists at api.py lines 284–349. |
| FLAW-2 | BLOCKING | Changed install to clone + `pip install -e .` | **Yes** | `pip install pidgin` removed entirely from M8. |
| FLAW-3 | SERIOUS | Added index.py step + second grep for removed fields | **Yes** | Verified: index.py:521 accesses `r.per_draft_tightness` — M1 step 5 now addresses this. Second grep catches all removed field names. |
| FLAW-4 | SERIOUS | Added structured format for SIMPLIFY verdicts | **Yes** | Format is specific: `SIMPLIFY: path | function | ACTION_TYPE: details`. ACTION_TYPE constrained to SPLIT/RENAME/EXTRACT with required signatures. |
| FLAW-5 | SERIOUS | Raised gate from 50% to 70%, rewrote DP1 | **Yes** | Math is now correct: N=10 deviation is 0.0095, expected range 70–91%. |
| FLAW-6 | SERIOUS | M5 compares against calibration reference, not M2 | **Yes** | Calibration numbers (102/19/5) embedded in M5 context. No dependency on M2 report chain. |
| FLAW-7 | SERIOUS | Verified `[index] Converged: N/M` exists, specified capture method | **Yes** | Confirmed: index.py:582 prints this format unconditionally. M2 now captures output via tee. |
| FLAW-8 | SERIOUS | Set M4 review=true, added pipeline exercise step | **Partially** | Review=true is correct. But pipeline exercise step (M4 step 5) relies on PD6 which is dead code — see FLAW-17 above. The fix introduced a new flaw. |
| FLAW-9 | SERIOUS | Set M8 review=true with verification instructions | **Yes** | Reviewer told to verify against current-state.md and CLAUDE.md files. |
| FLAW-10 | MINOR | Added version bump as M7 step 4 | **Yes** | Both pyproject.toml and __init__.py targeted. M9 expects 0.4.1. |
| FLAW-11 | MINOR | Updated language throughout M2 and M5 | **Yes** | "Calibration reference numbers" used consistently. Nest-as-baseline language removed. |
| FLAW-12 | STYLE | Log says "Ignored" | **Actually adopted** | Flaw Resolution Log says "Ignored per design instructions" but design-final.md M7 actually does have deferred items in a non-numbered section. The fix is applied; the log entry is misleading. |
| FLAW-13 | STYLE | Added recovery note to M5 step 1 | **Yes** | `scripts/load_calibration.py` recovery path documented. |

---

## New Flaws Introduced by Fixes

**FLAW-17 (introduced by FLAW-8 fix):** The pipeline exercise step added to M4 relies on PD6 for dry-run behavior, but PD6 was removed from the codebase. The fix to FLAW-8 (add meaningful verification beyond import check) introduced a step that either burns unexpected API budget or confuses the executor. See Missed Flaws section above for full analysis.

**FLAW-12 log inconsistency (introduced by FLAW-12 handling):** The Flaw Resolution Log says "Ignored per design instructions" for FLAW-12, but the design-final.md actually adopted the fix. This is a documentation inconsistency, not a functional issue. An executor or reviewer reading the log would believe the style issue persists when it doesn't.

---

## Ship Decision

**VERDICT: REVISE**

The design-final.md needs one more hardener pass to address 3 specific issues:

1. **M1: Add converge.xml example ex20 and pipeline/CLAUDE.md to scope** (FLAW-14). Without this, M1 fails its own grep verification at step 6 and the sprint halts at mission 1.

2. **M7: Add templates.py hardcoded path to cleanup scope** (FLAW-15). Without this, M9 reports ISSUES FOUND and the operator can't tag without an unplanned amendment.

3. **M4 step 5 / PD6: Fix the dry-run claim** (FLAW-17). Either use `--dry-run`, accept API cost, or use import-only verification. Update PD6 to match reality.

Optional but recommended:
- Fix M7 line reference for candidates.py (FLAW-16)
- Simplify M2 step 4/5 to require `converged=False` instead of exact sv values (FLAW-18)
- Fix FLAW-12 entry in the Flaw Resolution Log to say "Adopted" not "Ignored"

All three required changes are localized (specific lines in specific missions) and introduce no new dependencies. A single hardener pass will fix them.

**The single biggest risk if this ships as-is is:** M1 failing its own grep verification because converge.xml examples and pipeline/CLAUDE.md still reference `convergence_verdict` — the sprint dies at mission 1, before any real work begins.
