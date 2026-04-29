# Hardener Prompt — v0.4.1 Design Revisions

You are the hardener for sprint v0.4.1. A senior reviewer found 5 flaws
in design-final.md that the previous review/harden cycle missed. Your job
is to apply the fixes below to `local/sprints/tooling-v0.4.1/design-final.md`.

Read these files first:
1. `local/sprints/tooling-v0.4.1/senior-review.md` — the full analysis
2. `local/sprints/tooling-v0.4.1/design-final.md` — what you're editing

Then apply exactly these 6 changes. Do not alter anything else in the
document.

---

## Change 1: M1 step 2 — add converge.xml example cleanup (FLAW-14)

In M1 step 2 (converge.xml), after the line about removing duplicate
examples and fixing the contradictory role section, add:

```
   - Update or remove example ex20 (lines ~333–343) which references `convergence_verdict` in its sample code (`return convergence_verdict(centroid)`) and `<why>` tag. Replace the function call with `is_converged` or remove the example entirely.
```

This is needed because M1 step 6 greps `src/` for `convergence_verdict`
and these lines will match, causing FAIL: HARD.

---

## Change 2: M1 — add new step for pipeline/CLAUDE.md (FLAW-14)

In M1, between the current step 5 (index.py) and step 6 (grep
verification), insert a new step. Renumber step 6 → step 7. The new
step 6 is:

```
6. **pipeline/CLAUDE.md** (`src/pidgin/pipeline/CLAUDE.md`):
   - Remove the `convergence_verdict` row from the geometry.py symbol table (line ~42).
   - Delete the `## convergence_verdict Draft-Decay Test` section (lines ~95–102).
   - Add a row for `is_converged` to the geometry.py symbol table: `| is_converged | fn | Return (converged, sv) where converged = spherical_variance(vectors) < threshold. |`
   - EXPECT: No `convergence_verdict` references in the file. FAIL: SOFT (note and continue).
```

Update the M1 report requirements to add `pipeline/CLAUDE.md` to the
"Lines changed per file" list.

---

## Change 3: M7 — add templates.py hardcoded path (FLAW-15)

In M7, after step 1 (candidates.py) and before step 2 (mld.py), insert
a new step. Renumber steps 2–5 → 3–6. The new step 2 is:

```
2. **Hardcoded path in templates.py** (`src/pidgin/prompts/templates.py`):
   - Line ~96 contains `/Users/elliotwillis/Desktop/fe-toolkit/ORIGAMI.md` as a default parameter.
   - Replace with `None` default; if the parameter is dead, remove it entirely.
   - EXPECT: No `/Users/elliotwillis` paths in templates.py. FAIL: SOFT (note and continue).
```

Also fix step 1 (candidates.py): change "Lines ~86, ~96" to "Line ~86"
— there is only one hardcoded path in candidates.py, not two.

---

## Change 4: M4 step 5 — fix the dry-run claim (FLAW-17)

Replace M4 step 5 entirely with:

```
5. Verify the pipeline can load the refactored code without runtime errors:
   `python -c "from pidgin.pipeline.batch import run_embedding_mld_pipeline_for_functions; from pidgin.pipeline.mld import mld; from pidgin.pipeline.geometry import is_converged; print('pipeline imports OK')"`
   - EXPECT: Prints "pipeline imports OK" with no errors. FAIL: HARD on ImportError or AttributeError.
```

Update M4 report requirements: change "Exit code and any error output
from `pidgin index src/pidgin --sync` (dry-run)" to "Output of pipeline
import verification".

---

## Change 5: PD6 — correct to match reality (FLAW-17)

Replace PD6 with:

```
**PD6:** `index --dry-run` is the preview mode — zero API calls, no nest writes. The `--write-db` gate was removed in v0.2; it is not the dry-run mechanism. M4 uses import verification instead of a pipeline run to avoid API cost.
```

---

## Change 6: M2 step 4/5 — remove sv value requirement (FLAW-18)

In M2 step 4, change:

```
   - EXPECT: Each of these 5 functions has `converged=False` and `sv > 0.10`.
```

to:

```
   - EXPECT: Each of these 5 functions has `converged=False` (which implies sv ≥ 0.10 by threshold definition).
```

In M2 step 5, change:

```
5. Document total function count indexed, final convergence breakdown (converged / ambiguous / divergent counts and percentages), and the sv values for the 5 known divergents.
```

to:

```
5. Document total function count indexed, final convergence breakdown (converged / ambiguous / divergent counts and percentages), and the convergence status for the 5 known divergents.
```

In the M2 report requirements, change "sv values for the 5 known
divergent functions" to "convergence status (converged=True/False) for
the 5 known divergent functions".

---

## Change 7: Flaw Resolution Log — fix FLAW-12 entry

Change the FLAW-12 entry from:

```
**FLAW-12** (STYLE) — M7 step 4 numbered as OUT OF SCOPE  
**Ignored per design instructions.** (Structural cosmetic issue with no functional impact.)
```

to:

```
**FLAW-12** (STYLE) — M7 step 4 numbered as OUT OF SCOPE  
**Adopted.** Deferred items moved to a non-numbered section below the steps.
```

---

## After all changes

Add new entries to the Flaw Resolution Log for the senior review flaws:

```
---

**FLAW-14** (SERIOUS) — M1 step 6 grep catches converge.xml examples and pipeline/CLAUDE.md  
**Resolution: FIXED.**  
M1 step 2 now includes converge.xml example ex20 cleanup. New step 6 added for pipeline/CLAUDE.md updates (remove convergence_verdict docs, add is_converged row). Grep verification (now step 7) will pass clean.

---

**FLAW-15** (SERIOUS) — M7 misses hardcoded path in templates.py  
**Resolution: FIXED.**  
New step 2 added to M7 for `src/pidgin/prompts/templates.py:96`. M9 step 6 grep will now pass clean. Also corrected M7 step 1: candidates.py has one hardcoded path (line ~86), not two.

---

**FLAW-16** (MINOR) — M7 claims two hardcoded paths in candidates.py  
**Resolution: FIXED.** Corrected "Lines ~86, ~96" to "Line ~86" in M7 step 1.

---

**FLAW-17** (SERIOUS) — M4 step 5 dry-run claim is wrong — PD6 gate was removed  
**Resolution: FIXED.**  
M4 step 5 replaced with import verification that tests pipeline module loading without API calls. PD6 corrected to document `--dry-run` as the actual preview mechanism.

---

**FLAW-18** (MINOR) — M2 asks for sv values but sv is not stored in nest or output  
**Resolution: FIXED.**  
M2 steps 4/5 and report requirements changed to require `converged=False` status instead of exact sv float values. The boolean is sufficient for the gate check and is available in the nest metadata.
```

---

## Verification

After applying all changes, confirm:
1. M1 has 7 steps (geometry.py, converge.xml, batch.py, mld.py, index.py, pipeline/CLAUDE.md, grep verification)
2. M7 has 6 steps (candidates.py, templates.py, mld.py, index.py, version bump, import verify)
3. M4 step 5 uses import verification, not `pidgin index`
4. PD6 references `--dry-run`, not `--write-db`
5. M2 steps 4/5 and report requirements say `converged=False`, not sv values
6. Flaw Resolution Log has entries for FLAW-14 through FLAW-18
7. FLAW-12 entry says "Adopted" not "Ignored"
