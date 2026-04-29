# Tooling Sprint v0.4.1 — Final Design

**Status:** FINAL  
**Date:** 2026-04-29  
**Repo:** github.com/wiregrassio/pidgin  
**Integrates:** design.md + flaw resolutions from flaws.md

---

## Premise

### What v0.4 Delivered

v0.4 ran five missions before it was killed:

- **M1 (Batch chunking):** 100 requests per JSONL, 2 concurrent batches, pipelined submission.
- **M2 (Error surfacing):** `first_error` field on `FunctionMldResult`, exits 1 on `ALL_ERRORED`.
- **M3 (Nest at git root):** `find_project_root()` walks up to `.git`, writes nest regardless of CWD.
- **M4 (Class method extraction):** Parser extracts public methods from classes.
- **M5 (Gate model switch):** Validated and switched gate validation to `gpt-4.1-mini`.

All five are present and working in the migrated repo.

### What Broke

**P1 (Convergence rewrite, mid-v0.4):** Replaced the antipode test with `spherical_variance` and `convergence_verdict`. But `convergence_verdict` uses draft decay (`sv1 > sv2 > sv3`) which the calibration data proved is backwards — draft 3 is always *noisier* than draft 1 because the tighter token budget forces different choices about what to include. The pipeline has been reporting near-0% convergence on real code. The descriptions themselves are correct; only the convergence flag is wrong.

### What the Calibration Proved

12,600 API calls (126 functions × 25 calls × 4 temperatures × 3 drafts), 37,638 embedded vectors. Findings are definitive:

1. **Draft 3 is worse, not better.** At t=0.3, draft 1 mean sv=0.0626, draft 3 mean sv=0.0941. Drop drafts 2 and 3.
2. **Temperature 0.3 is 2.7× tighter than t=1.5.** Lock at 0.3. Do not mix.
3. **Pooling drafts hurts.** Mean sv pooled=0.1075, draft 1 only=0.0626.
4. **Threshold: sv < 0.10 gives 81% convergence at N=25.**
5. **N=10 is sufficient.** Mean deviation from N=25 reference: 0.0095 — an order of magnitude smaller than the threshold.
6. **Body length doesn't predict convergence** (correlation 0.169).

The convergence test is now one line:
```python
converged = spherical_variance(draft_1_vectors) < 0.10
```

### The Calibration Reference Numbers (Ground Truth)

126 functions loaded into `.pidgin/nest/` via `scripts/load_calibration.py` using the correct test (sv < 0.10 on draft_1 at t=0.3):
- **102 CONVERGED** (sv < 0.10)
- **19 AMBIGUOUS** (sv 0.10–0.15)
- **5 DIVERGENT** (sv > 0.15): `classify_batch_results`, `MLDResult`, `AssembledPrompt`, `generate`, `EditOp`

All 126 are queryable. `pidgin query "compute spherical variance"` returns 0.833 similarity. These are the reference numbers. They are not in the nest — they are in the context documents. The nest is overwritten during indexing.

### Migration

Pidgin extracted from fe-toolkit to its own repo (github.com/wiregrassio/pidgin). Src layout. Sprint history moved. Fe-toolkit stripped.

---

## Scope

Three phases, 9 missions.

| Phase | Gate | Missions |
|-------|------|----------|
| 1: Convergence Rewrite | M2 GREEN (≥ 70% convergence) | M1, M2 |
| 2: Pidgin Works on Itself | M5 GREEN | M3, M4, M5 |
| 3: Hardening and Docs | M9 GREEN | M6, M7, M8, M9 |

**Phase 1 is the blocking track.** Nothing in Phase 2 dispatches until the convergence smoke test passes (≥ 70% convergence). Phase 3 can proceed once Phase 2's re-index is clean.

---

## Phase 1: Convergence Rewrite

The pipeline generates 3 drafts per call, uses the wrong convergence test, and doesn't lock temperature. All three must be fixed together — they're one coherent change.

### M1 — Convergence Pipeline Rewrite

**Tier:** execute  
**Review:** true  
**Depends on:** nothing (first mission)

**Context:** The convergence test in `geometry.py` and `batch.py` is wrong. `convergence_verdict()` checks whether sv decreases from draft 1 → draft 3 (sv1 > sv2 > sv3). Calibration proved draft 3 always has *higher* variance. The pipeline also generates 3 drafts per call and uses uncontrolled temperature. The exact replacement spec is below.

Additionally: `index.py` line ~521 accesses `r.per_draft_tightness` in the `--verbose` output block. After removing that field from `FunctionMldResult`, this line will crash at runtime. It must be updated in this mission.

**Objective:** Rewrite the convergence-related code in `geometry.py`, `batch.py`, `mld.py`, `converge.xml`, and `index.py` to match the calibration findings: 1 draft per call, temperature 0.3, 10 calls, sv < 0.10.

**Steps:**

1. **geometry.py** (`src/pidgin/pipeline/geometry.py`):
   - Delete `convergence_verdict()` entirely.
   - Add at module top: `CONVERGENCE_THRESHOLD = 0.10`
   - Add function:
     ```python
     def is_converged(vectors: list[list[float]], threshold: float = CONVERGENCE_THRESHOLD) -> tuple[bool, float]:
         """Single-number convergence test. Returns (converged, sv)."""
         sv = spherical_variance(vectors)
         return sv < threshold, sv
     ```
   - Keep `spherical_variance()` and `centroid()` unchanged.
   - EXPECT: `convergence_verdict` is gone from the file. `is_converged` is present. FAIL: HARD.

2. **converge.xml** (`src/pidgin/prompts/converge.xml`):
   - Change response schema from `{draft_1, draft_2, draft_3}` to `{"description": {"type": "string"}}` with `"required": ["description"]` and `"additionalProperties": false`.
   - Update the role/instruction section: remove all language about "produce three drafts at increasing refinement." Replace with "produce one concise description."
   - Remove duplicate example if present. Fix contradictory role section.
   - Update or remove example ex20 (lines ~333–343) which references `convergence_verdict` in its sample code (`return convergence_verdict(centroid)`) and `<why>` tag. Replace the function call with `is_converged` or remove the example entirely.
   - EXPECT: schema has exactly one field `description`. No draft language in instructions. FAIL: HARD.

3. **batch.py** (`src/pidgin/pipeline/batch.py`):
   - Change `ADAPTIVE_MAX_BATCHES = 5` to `ADAPTIVE_MAX_BATCHES = 10`.
   - Change all generation calls to use `temperature=0.3` explicitly.
   - Change generation from 3 drafts per call to 1 draft per call (`n=1`).
   - Update `FunctionMldResult`: remove fields `sv1`, `sv2`, `sv3`, `convergence_verdict`, `per_draft_centroid`, `per_draft_tightness`, `per_draft_n`. Add `sv: float = 0.0` and `converged: bool = False` (set by `is_converged()`).
   - Replace convergence check call with `is_converged(vectors)` from geometry.py. Set `result.converged` and `result.sv` from its return value.
   - Simplify `_extract_drafts()`: primary shape becomes `{"description": "..."}`. Keep fallback for robustness but make `{"description": str}` the first-checked shape.
   - `_stratify()` may remain for telemetry but must not be called in the convergence decision path.
   - EXPECT: `ADAPTIVE_MAX_BATCHES` is 10, temperature is 0.3 on all generation calls, `convergence_verdict` is not referenced, `FunctionMldResult` has `sv` and `converged` fields and does NOT have `sv1`/`sv2`/`sv3`/`per_draft_tightness`/`per_draft_centroid`/`per_draft_n`. FAIL: HARD.

4. **mld.py** (`src/pidgin/pipeline/mld.py`):
   - Apply the same changes as batch.py for the single-function path: 1 draft per call, temperature=0.3, `is_converged()` for the convergence check.
   - Remove any per-draft-tier logic from the single-function path.
   - EXPECT: mld.py imports `is_converged` from geometry.py. No draft-tier references. FAIL: HARD.

5. **index.py** (`src/pidgin/verbs/index.py`, lines ~515–532):
   - In the `--verbose` per-function output block, replace the `per_draft_tightness` access with `r.sv`. The new verbose output for a converged function should be:
     ```python
     print(
         f"  ✓ {r.name} (converged, sv={r.sv:.4f}, cluster={r.cluster_size})",
         file=sys.stderr,
     )
     ```
   - Remove the `tight_vals` and `tightness` local variables.
   - EXPECT: No `per_draft_tightness` reference in index.py. FAIL: HARD.

6. **pipeline/CLAUDE.md** (`src/pidgin/pipeline/CLAUDE.md`):
   - Remove the `convergence_verdict` row from the geometry.py symbol table (line ~42).
   - Delete the `## convergence_verdict Draft-Decay Test` section (lines ~95–102).
   - Add a row for `is_converged` to the geometry.py symbol table: `| is_converged | fn | Return (converged, sv) where converged = spherical_variance(vectors) < threshold. |`
   - EXPECT: No `convergence_verdict` references in the file. FAIL: SOFT (note and continue).

7. **Verify field removal — all callers:**
   - Run: `grep -rn "convergence_verdict" src/`
   - Run: `grep -rn "\.sv1\|\.sv2\|\.sv3\|per_draft_centroid\|per_draft_tightness\|per_draft_n" src/`
   - EXPECT: Both greps return empty. FAIL: HARD if either has results.
   - `is_converged` must be imported wherever convergence is checked.

**Report must include:**
- Lines changed per file (geometry.py, batch.py, mld.py, converge.xml, index.py, pipeline/CLAUDE.md)
- Final state of `FunctionMldResult` fields (list them)
- Final state of `is_converged` signature
- Output of both greps from step 7 (must be empty)
- Any carry-forwards encountered

---

### M2 — Convergence Smoke Test

**Tier:** execute  
**Review:** false  
**Depends on:** M1 GREEN

**Context:** M1 rewrote the convergence pipeline. This mission verifies the rewrite produces the expected results on the actual pidgin codebase. The reference numbers come from the calibration experiment (not the nest — the nest is overwritten by this run): 102 CONVERGED / 19 AMBIGUOUS / 5 DIVERGENT out of 126 functions. The live run uses N=10 calls per function, which produces ~81% convergence by the calibration data. Model nondeterminism at N=10 accounts for ±5-10 percentage points from the N=25 reference; 70%+ is the minimum acceptable result.

**Objective:** Confirm the corrected pipeline produces ≥ 70% convergence on pidgin's own codebase and that the 5 known divergent functions remain divergent.

**Steps:**

1. Run: `pidgin index . --sync 2>&1 | tee /tmp/m2_index.log`
   - EXPECT: Command exits 0. The final output line reads `[index] Converged: N/M` where N and M are positive integers.
   - FAIL: HARD on non-zero exit or crash.

2. Extract the convergence rate from the output captured in `/tmp/m2_index.log`:
   - Find the line matching `[index] Converged: N/M`. Compute rate = N/M × 100.
   - EXPECT: Rate ≥ 70%. FAIL: HARD if rate < 70% (see Phase 1 Gate below).

3. After indexing, run: `pidgin query "compute spherical variance"`
   - EXPECT: Returns a result with similarity ≥ 0.75. The top result should be `geometry.py:spherical_variance` or similar.
   - FAIL: SOFT if below 0.75 (note result and continue).

4. Verify the 5 known divergent functions. Query the nest or inspect its stored `converged` field for:
   `classify_batch_results`, `MLDResult`, `AssembledPrompt`, `generate`, `EditOp`
   - EXPECT: Each of these 5 functions has `converged=False` (which implies sv ≥ 0.10 by threshold definition).
   - FAIL: SOFT if any one is now converged (note it — it may be an improvement, not a bug).

5. Document total function count indexed, final convergence breakdown (converged / ambiguous / divergent counts and percentages), and the convergence status for the 5 known divergents.

**Report must include:**
- Exit code and any error output from the index run
- Full `[index] Converged: N/M` line from stdout
- Convergence rate (%), converged/ambiguous/divergent counts
- Query result for "compute spherical variance" (top result + similarity score)
- convergence status (converged=True/False) for the 5 known divergent functions
- PASS/FAIL verdict with reasoning

**Phase 1 Gate:** M2 must be GREEN (convergence rate ≥ 70%, no crashes) before Phase 2 dispatches.

---

## Phase 2: Pidgin Works on Itself

The calibration identified 5 divergent functions. The operator's stance: "cattle, not pets, understandable, modular." These functions get a review pass. If they can be simplified, simplify them. If they're genuinely complex, accept the divergence and document it. Then re-index from scratch.

### M3 — Review 5 Divergent Functions

**Tier:** reason  
**Review:** true  
**Depends on:** M2 GREEN (convergence rate ≥ 70%)

**Context:** The calibration identified 5 functions with sv > 0.10 that the pipeline cannot converge on. High sv means the model produces semantically different descriptions on different runs — the function is doing too many things or the boundaries are unclear. The operator's stance is "cattle, not pets, understandable, modular" — if a function can be made simpler without losing correctness, it should be. If it can't, accept the divergence and document why.

The 5 functions and their calibration sv values (from M2's report):
- `MLDResult` (sv=0.28) — dataclass with many fields and complex metadata
- `generate` (sv=0.19) — multi-purpose: schema, structured output, async, cost tracking
- `classify_batch_results` (sv=0.19) — unclear why divergent at this level
- `EditOp` (sv=0.18) — multi-step: replace lines, handle payload, manage offsets
- `AssembledPrompt` (sv=0.15) — borderline, dataclass with preamble/payload split

**Objective:** For each of the 5 divergent functions, deliver a written verdict (SIMPLIFY with specific changes, or ACCEPT with reasoning) and a structured change list for M4.

**Steps:**

1. For each of the 5 functions, read the full implementation. Assess:
   - Does the function do more than one thing?
   - Is the ambiguity coming from unclear naming, mixed concerns, or genuine complexity?
   - Can the function be split, renamed, or simplified without changing behavior?
   - Would a split reduce the divergence, or is the complexity load-bearing?

2. Apply the operator's criteria: "understandable, modular." A function is understandable if a reader can state what it does in one sentence. A function is modular if it has one reason to change.

3. Produce a verdict for each function:
   - **ACCEPT** — Function is genuinely complex or correctly multi-step. Document why one-sentence description is impossible. No change.
   - **SIMPLIFY** — Function has separable concerns. State the exact change in the structured format below.

4. **Required format for SIMPLIFY verdicts** (M4 will parse this exactly):
   ```
   SIMPLIFY: <absolute_file_path> | <function_name> | <ACTION_TYPE>: <details>
   ```
   Where `ACTION_TYPE` is exactly one of:
   - `SPLIT INTO fn1(signature1), fn2(signature2)` — both new function names and full signatures required
   - `RENAME TO new_name` — new name only
   - `EXTRACT helper_description INTO new_fn_name(signature)` — extracted logic, new function name, signature

   Each SIMPLIFY verdict must produce exactly one structured line in the M4 change list. If a function needs multiple changes, emit multiple lines.

5. If all verdicts are ACCEPT, produce: `M4 CHANGE LIST: EMPTY — all verdicts ACCEPT, zero changes.`

**Report must include:**
- Verdict for each of the 5 functions (ACCEPT or SIMPLIFY)
- For each ACCEPT: reasoning (one paragraph)
- For each SIMPLIFY: structured change line in the format above
- M4 change list as a numbered block (or the EMPTY declaration)

---

### M4 — Apply Divergent Function Refactors

**Tier:** execute  
**Review:** true  
**Depends on:** M3 GREEN

**Context:** M3 produced a verdict for each of the 5 divergent functions. The M4 change list in M3's report uses the format: `SIMPLIFY: <file_path> | <function_name> | <ACTION_TYPE>: <details>`. This mission applies those changes verbatim. If M3 declared `M4 CHANGE LIST: EMPTY`, close this mission immediately as GREEN with zero changes.

Changes are scoped to behavior-preserving internal restructuring only. Any SIMPLIFY verdict that would change a public API signature or modify the nest schema must be escalated (see DP2) — it is not within this mission's scope.

**Objective:** Apply all SIMPLIFY changes from M3's change list. Preserve behavior.

**Steps:**

1. Read M3's change list from the sprint log.
2. If the change list is EMPTY: report GREEN, zero changes, mission complete.
3. For each SIMPLIFY item: apply the specified change exactly as written. Do not interpret — the format is `file | function | action`. If a specific item's action is missing required detail (e.g., SPLIT missing a signature), note it as a carry-forward and skip that item only.
4. After all changes: run `python -c "import pidgin"` to verify the package still imports. FAIL: HARD if this fails.
5. Verify the pipeline can load the refactored code without runtime errors:
   `python -c "from pidgin.pipeline.batch import run_embedding_mld_pipeline_for_functions; from pidgin.pipeline.mld import mld; from pidgin.pipeline.geometry import is_converged; print('pipeline imports OK')"`
   - EXPECT: Prints "pipeline imports OK" with no errors. FAIL: HARD on ImportError or AttributeError.

**Report must include:**
- List of changes applied (file, function, what changed)
- List of items skipped (if any) with reason
- Output of `python -c "import pidgin"` (must succeed)
- Output of pipeline import verification
- Any carry-forwards

---

### M5 — Fresh Full Re-index

**Tier:** execute  
**Review:** false  
**Depends on:** M4 GREEN (or M4 vacuous GREEN)

**Context:** The nest currently contains functions from the M2 smoke test. M4 may have changed some functions. This mission clears the nest and re-indexes from scratch using the corrected pipeline. This is the first fully live run of the corrected pipeline after all refactors.

If subsequent steps fail after nest deletion, the calibration baseline can be restored via `python scripts/load_calibration.py`.

The calibration reference numbers for comparison are: **102 CONVERGED / 19 AMBIGUOUS / 5 DIVERGENT** out of 126 functions. The live run may differ due to M4 refactors (some previously-divergent functions may now converge) and model nondeterminism. A result meaningfully below 60% converged indicates a regression.

**Objective:** Produce a clean self-indexed nest with convergence rates consistent with the calibration reference.

**Steps:**

1. Delete the existing nest: `rm -rf .pidgin/nest/`
   (Recovery: if subsequent steps fail, run `python scripts/load_calibration.py` to restore from raw data.)
2. Re-initialize: `pidgin init`
   - EXPECT: `.pidgin/nest/` is created. FAIL: HARD.
3. Re-index: `pidgin index . --sync 2>&1 | tee /tmp/m5_index.log`
   - EXPECT: Exits 0. The final output contains `[index] Converged: N/M`.
   - FAIL: HARD on non-zero exit or crash.
4. Run query verification:
   - `pidgin query "compute spherical variance"` — EXPECT: top result at ≥ 0.75 similarity.
   - `pidgin query "batch MLD dispatch"` — EXPECT: returns batch.py or pipeline results.
   - `pidgin query "write files atomically"` — EXPECT: returns write/ module results.
5. Compare against calibration reference: document total function count, convergence breakdown (converged/ambiguous/divergent counts and percentages), and compare to 102/19/5. Note any functions that changed convergence status from the calibration reference (likely M4 refactors or nondeterminism — both are acceptable if the overall rate is ≥ 60%).

**Report must include:**
- Total functions indexed
- Convergence breakdown: converged N (%), ambiguous N (%), divergent N (%)
- Comparison to calibration reference: 102 CONVERGED / 19 AMBIGUOUS / 5 DIVERGENT
- sv values for the 5 originally-divergent functions (or their replacements if M4 split them)
- Query results for the 3 test queries (top result + similarity for each)
- Any functions that changed convergence status vs. the calibration reference
- PASS/FAIL verdict

**Phase 2 Gate:** M5 must be GREEN (converged ≥ 60%, no crashes, queries working) before Phase 3 dispatches.

---

## Phase 3: Hardening and Docs

Carry-forward debt, rate limit handling, version bump, and the first user-facing documentation. M6, M7, and M8 may run concurrently after Phase 2 gate clears. M9 waits for all three.

### M6 — Rate Limit Hardening

**Tier:** execute  
**Review:** false  
**Depends on:** Phase 2 gate (M5 GREEN)

**Context:** `src/pidgin/utils/api.py` has two active OpenAI call paths, both with inadequate retry logic:
- Lines ~379–386: OpenAI generate retry (3 attempts, `asyncio.sleep(1.0 * (2 ** attempt))`)
- Lines ~93–100: OpenAI gate/embedding retry (3 attempts, same fixed-multiplier formula)

Neither path has jitter or Retry-After header support. The calibration hit the 200K TPM ceiling ~30 times. At t=0.3 rate limits are rare but will occur on large repos.

Additionally, `_one_anthropic_call()` (lines ~311–349) is dead code — the Anthropic gate was removed in v0.4 M5. Delete it.

**Objective:** Upgrade the two OpenAI retry paths to exponential backoff with full jitter and Retry-After support. Delete the dead Anthropic function.

**Steps:**

1. In `api.py`, update **both** active OpenAI retry paths (lines ~93–100 and ~379–386):
   - Increase max attempts from 3 to 5 in both paths.
   - Replace the fixed-multiplier sleep with full jitter in both paths:
     ```python
     import random
     BASE_DELAY = 1.0
     MAX_DELAY = 60.0
     delay = random.uniform(0, min(MAX_DELAY, BASE_DELAY * (2 ** attempt)))
     await asyncio.sleep(delay)
     ```
   - Before sleeping, check for a `Retry-After` header on the exception. If present and parseable as a number of seconds, use `max(delay, float(retry_after))` as the sleep duration.
   - EXPECT: Both OpenAI call paths use full-jitter backoff with 5 attempts. FAIL: HARD if either path is unchanged.

2. Delete the dead Anthropic code: find the `_one_anthropic_call` inner function (and any surrounding Anthropic-specific scaffolding, including the `import anthropic` and `anthropic.AsyncAnthropic(...)` lines that are only used by this path). Delete them.
   - EXPECT: `grep -n "anthropic\|_one_anthropic" src/pidgin/utils/api.py` returns nothing. FAIL: HARD.

3. `_is_retryable()` already detects 429 and 5xx. No changes needed unless the implementation is clearly wrong.

4. Verify the package still imports and api.py loads without errors:
   `python -c "from pidgin.utils.api import generate"`
   - EXPECT: No errors. FAIL: HARD.

**Report must include:**
- Final sleep formula used (copy the exact code block)
- Confirmation both OpenAI call paths were updated
- Confirmation `_one_anthropic_call` and Anthropic imports were deleted
- Output of `grep -n "anthropic\|_one_anthropic" src/pidgin/utils/api.py` (must be empty)
- Import verification output

---

### M7 — Carry-Forward Debt Cleanup + Version Bump

**Tier:** execute  
**Review:** false  
**Depends on:** Phase 2 gate (M5 GREEN)

**Context:** Several cosmetic and correctness issues have accumulated across sprints. These are all one-line or small fixes. The version bump to 0.4.1 belongs here — the operator will tag the release after M9, and the version string must match.

**Objective:** Apply all in-scope carry-forward fixes and bump the version to 0.4.1.

**Steps (each item is independent; apply all, note any that can't be applied cleanly):**

1. **Hardcoded paths in candidates.py** (`src/pidgin/pipeline/candidates.py`):
   - Line ~86 contains `/Users/elliotwillis/Desktop/fe-toolkit/...` path as a default.
   - Remove or replace with `None` default; if this is a dead function parameter, remove the whole parameter.
   - EXPECT: No `/Users/elliotwillis` paths in candidates.py. FAIL: SOFT (note and continue).

2. **Hardcoded path in templates.py** (`src/pidgin/prompts/templates.py`):
   - Line ~96 contains `/Users/elliotwillis/Desktop/fe-toolkit/ORIGAMI.md` as a default parameter.
   - Replace with `None` default; if the parameter is dead, remove it entirely.
   - EXPECT: No `/Users/elliotwillis` paths in templates.py. FAIL: SOFT (note and continue).

3. **Stale DEPENDS comment in mld.py** (`src/pidgin/pipeline/mld.py`):
   - There is a stale comment referencing `tools.utils.api` (the old module path from fe-toolkit).
   - Update or remove the comment.
   - EXPECT: No `tools.utils.api` references in mld.py. FAIL: SOFT.

4. **Cosmetic in index.py** (`src/pidgin/verbs/index.py`, line ~65):
   - "requests errored." — incomplete sentence in error message.
   - Fix to a complete, clear error message.
   - EXPECT: Message is a complete sentence. FAIL: SOFT.

5. **Version bump:**
   - In `pyproject.toml`, update `version = "0.2.0"` to `version = "0.4.1"`.
   - In `src/pidgin/__init__.py`, update `__version__ = "0.2.0"` to `__version__ = "0.4.1"`.
   - EXPECT: Both files read `0.4.1`. FAIL: SOFT (note and continue; M9 will catch it).

6. After all changes: `python -c "import pidgin; print(pidgin.__version__)"` must print `0.4.1`. FAIL: HARD if import fails. FAIL: SOFT if version string is wrong.

**Deferred (not in scope for this mission):**
- `function_dict_hash` / `function_source_hash` divergence (non-trivial schema change)
- Identity key portability (absolute file path in nest ID — requires nest migration)

**Report must include:**
- List of changes applied (file, line range, what changed)
- List of items skipped with reason
- Output of `python -c "import pidgin; print(pidgin.__version__)"` (must print `0.4.1`)
- Carry-forwards for next sprint

---

### M8 — docs/pidgin.md

**Tier:** execute  
**Review:** true  
**Depends on:** Phase 2 gate (M5 GREEN); may run concurrently with M7

**Context:** Pidgin has no user-facing documentation. The CLAUDE.md files are agent-facing references, not human onboarding. This mission writes the first external document explaining what Pidgin is and how to use it. The package is not on PyPI — the only install path is from a GitHub clone.

**Objective:** Write `docs/pidgin.md` — a complete, accurate, usable document for a developer who has never seen Pidgin.

**Sections to include:**

1. **What is Pidgin** — LLM-native toolkit for indexing codebases via MLD. The goal: queryable semantic descriptions of every public function in a repo, stored in a per-repo vector database. One paragraph.

2. **How MLD works** — The pipeline. Extract public functions from source. For each function, generate 10 descriptions at t=0.3 (1 draft per call). Embed each description. Compute spherical variance of the embedding cluster. If sv < 0.10, the function has converged — the centroid embedding is the stored description. Include the calibration data summary: 81% convergence rate, 37,638 vectors, empirically derived threshold.

3. **Installation** — Two steps: (1) clone the repo from github.com/wiregrassio/pidgin, (2) `pip install -e .` from the repo root. OPENAI_API_KEY required in environment or `.env` file at repo root.

4. **Quick start** — four commands:
   ```
   pidgin init              # bootstrap .pidgin/nest/
   pidgin index . --sync    # index all public functions
   pidgin query "..."       # semantic search
   pidgin egg .             # generate CLAUDE.md from nest
   ```

5. **CLI Reference** — brief description of each verb: `init`, `index`, `query`, `egg`, `depends`, `summarize`. Flags for `index`: `--sync` (one-at-a-time, shows progress), `--batch` (parallel JSONL, faster for large repos), `--verbose`.

6. **Provider Configuration** — Generation: gpt-4.1-nano. Gate validation: gpt-4.1-mini. Embeddings: text-embedding-3-small, 256-dim. All OpenAI. OPENAI_API_KEY in environment or `.env`.

7. **Understanding convergence** — What CONVERGED/AMBIGUOUS/DIVERGENT means. The sv threshold. When to investigate divergent functions (they're signals, not errors).

**Constraints:**
- Write for a developer who knows Python and has used an LLM API but has not seen Pidgin before.
- No hedging language ("may", "might", "could"). State what the tool does.
- Do not invent features that don't exist. Verify every CLI flag and command against `.claude/CLAUDE.md` and the verbs CLAUDE.md.
- Target length: 400–700 words. Dense and useful, not padded.
- Create `docs/` directory if it doesn't exist.

**Report must include:**
- Confirmation that docs/pidgin.md was written
- Word count
- Any features mentioned that weren't verified against the codebase (flag them for the reviewer)

**Reviewer:** Verify every command in the document against `current-state.md` and `.claude/CLAUDE.md`. Flag any CLI flag, verb, or install instruction that doesn't match the documented state.

---

### M9 — Final Verification

**Tier:** scout  
**Review:** false  
**Depends on:** M6 GREEN, M7 GREEN, M8 GREEN

**Context:** All missions are complete. This scout pass verifies the repo is in a clean, releasable state before the operator tags and pushes v0.4.1.

**Objective:** Confirm the repo is clean, the pipeline works end-to-end, and there are no obvious regressions.

**Steps (read-only, no modifications):**

1. `git status` — EXPECT: working tree clean. Note any unexpected untracked changes.
2. `python -c "import pidgin; print(pidgin.__version__)"` — EXPECT: prints `0.4.1`. FAIL: SOFT if wrong.
3. Check `pyproject.toml` — version field must read `0.4.1`. FAIL: SOFT if not.
4. Run three queries and record results:
   - `pidgin query "compute spherical variance"`
   - `pidgin query "index a repository"`
   - `pidgin query "write files atomically"`
   - EXPECT: Each returns at least one result with similarity ≥ 0.70.
5. `grep -r "convergence_verdict" src/` — EXPECT: empty. Note if not.
6. `grep -r "/Users/elliotwillis" src/` — EXPECT: empty. Note if not.
7. Check `docs/` directory exists and contains `pidgin.md` (from M8).

**Report must include:**
- `git status` output
- Current version string from `pidgin.__version__` and `pyproject.toml`
- Query results for all 3 test queries (top result + similarity)
- Whether `convergence_verdict` or hardcoded paths were found (should be clean)
- Whether `docs/pidgin.md` exists
- Overall verdict: READY TO TAG / ISSUES FOUND

**After M9:** The operator reviews the report and manually tags v0.4.1 and pushes.

---

## Decision Points

### DP1: Convergence rate below 70% at M2

If M2 reports convergence below 70%, the Phase 1 rewrite has a bug — this is NOT within model nondeterminism range. N=10 calls produce a mean deviation of 0.0095 from the N=25 reference (81%), so the acceptable range is roughly 70–91%. Anything below 70% indicates an incomplete or incorrect fix.

Stop Phase 2, issue an amendment to M1. Do not proceed until the root cause is identified.

If M2 reports 70–91%: proceed to Phase 2, note the deviation in the log.

### DP2: M3 SIMPLIFY verdicts require public API changes

If M3's SIMPLIFY verdicts would require changes to public API signatures or nest schema (not just internal restructuring), escalate to the operator before M4 dispatches. M4 is scoped to behavior-preserving internal changes only.

### DP3: M4 introduces import errors

If `python -c "import pidgin"` fails after M4's changes, stop Phase 2 gate. Fix before M5.

### DP4: M5 fresh re-index falls below 60% convergence

If the Phase 2 gate re-index produces fewer than 60% converged functions (vs. ~70–81% expected), investigate before proceeding to Phase 3. This would indicate M4's refactors introduced semantic noise or the pipeline has a regression.

---

## Conventions

**Per-mission agent termination.** Each agent runs in a fresh context. The report is the only communication channel. If a mission's report does not contain the information the next mission needs, the design is wrong — not the agent.

**HARD vs SOFT failures.** HARD failures stop the mission immediately; the commander is notified. SOFT failures are logged in the report and execution continues. Reviewers promote SOFT failures to HARD if they indicate systemic issues.

**No side quests.** An agent that encounters an issue outside its mission scope logs it as a carry-forward and continues. It does not fix it. The cleanup mission (M7) exists for exactly this.

**One-line fixes belong in M7.** Any fix that can be described as "change this line to that line" goes in M7, not its own mission.

**Calibration numbers are ground truth.** Do not second-guess the 102/19/5 split, the sv=0.10 threshold, or the N=10 sample size. These were derived from 37,638 data points.

**The pipeline is not being redesigned.** MLD generation, embedding, nest storage, query logic, batch chunking, and the gate are all correct. The only thing being fixed is the convergence wrapper.

---

## Pre-Decisions

**PD1:** Temperature 0.3 is hardcoded in the pipeline for generation. It is not a configuration parameter. Users do not set it.

**PD2:** `_stratify()` in batch.py may remain for telemetry purposes. It must not be called in the convergence decision path. If removing it is simpler, remove it.

**PD3:** The identity key portability issue (absolute file path in nest ID) is deferred to the next sprint. M7 does not touch it.

**PD4:** The `function_dict_hash` / `function_source_hash` divergence is deferred to the next sprint. M7 does not touch it.

**PD5:** `docs/pidgin.md` is a new file in a new `docs/` directory. Create the directory.

**PD6:** `index --dry-run` is the preview mode — zero API calls, no nest writes. The `--write-db` gate was removed in v0.2; it is not the dry-run mechanism. M4 uses import verification instead of a pipeline run to avoid API cost.

---

## Carry-Forwards to Next Sprint

- Identity key portability (absolute path in nest ID, makes nest non-portable)
- `function_dict_hash` / `function_source_hash` divergence
- P1 bidirectional probe still at 3/6 (description precision measurement)
- `converge.xml` anti-examples audit (may anchor model on failure patterns — deferred)
- SDK indexing (external repo indexing) — blocked until pipeline is verified correct on self-indexing

---

## Flaw Resolution Log

Each entry: flaw ID, severity, resolution decision, what changed in the design.

---

**FLAW-1** (BLOCKING) — M6 references non-existent Anthropic call path  
**Resolution: FIXED.**  
Code inspection confirms `_one_anthropic_call` exists in api.py (lines ~311–349) as dead code — the Anthropic gate was removed in v0.4 M5. M6 spec updated: (1) removed all mention of "both call paths" language and replaced with "two active OpenAI call paths"; (2) added explicit step to DELETE `_one_anthropic_call` and its surrounding Anthropic imports; (3) added grep verification: `grep -n "anthropic\|_one_anthropic" src/pidgin/utils/api.py` must return empty. FAIL: HARD.

---

**FLAW-2** (BLOCKING) — M8 documents `pip install pidgin` — package not on PyPI  
**Resolution: FIXED.**  
M8 Installation section rewritten to: clone from github.com/wiregrassio/pidgin, then `pip install -e .`. The `pip install pidgin` command has been removed entirely. No publish mission exists and no PyPI install path is documented.

---

**FLAW-3** (SERIOUS) — M1 verifies `convergence_verdict` string but not callers of removed fields  
**Resolution: FIXED.**  
Code inspection confirmed the risk: `index.py:521` accesses `r.per_draft_tightness`, which will crash after M1 removes the field. Two changes made: (1) M1 now includes an explicit step (step 5) to update `index.py`'s verbose output block, replacing `per_draft_tightness` with `r.sv`; (2) M1 step 6 adds a second grep: `grep -rn "\.sv1\|\.sv2\|\.sv3\|per_draft_centroid\|per_draft_tightness\|per_draft_n" src/` must return empty. FAIL: HARD. Both greps must pass before M1 can be marked GREEN.

---

**FLAW-4** (SERIOUS) — M3→M4 handoff has no format contract  
**Resolution: FIXED.**  
M3's report requirements now mandate a structured format for SIMPLIFY verdicts: `SIMPLIFY: <absolute_file_path> | <function_name> | <ACTION_TYPE>: <details>` where ACTION_TYPE is SPLIT INTO, RENAME TO, or EXTRACT INTO (with signatures required for SPLIT and EXTRACT). M4's context now states exactly what format to expect and that it must parse the list without interpretation. The escape hatch ("note as carry-forward") is retained only for items missing required detail within that format, not for vague verdicts.

---

**FLAW-5** (SERIOUS) — Phase 1 gate at 50% doesn't prove the fix works; DP1 misstates the math  
**Resolution: FIXED.**  
Phase 1 gate raised from ≥ 50% to ≥ 70%. DP1 rewritten: "50–70% is not model nondeterminism — it's a pipeline bug." The math is grounded in the calibration: N=10 has mean deviation 0.0095 from N=25 reference (81%), placing the expected range at 70–91%. Anything below 70% requires amendment to M1 before Phase 2 proceeds.

---

**FLAW-6** (SERIOUS) — M5 cannot compare against M2's sv values due to context isolation  
**Resolution: FIXED.**  
M5 step 5 now compares against the calibration reference numbers (102/19/5) stated in this design document, not against M2's report. These numbers are available to every agent in the sprint context. The instruction "compare against M2" has been replaced with "compare against calibration reference: 102 CONVERGED / 19 AMBIGUOUS / 5 DIVERGENT." The chain M5 receives (M4 report) does not need to carry M2's data.

---

**FLAW-7** (SERIOUS) — M2 step 3 checks a feature that may not exist  
**Resolution: FIXED.**  
Code inspection confirms `--verbose` IS implemented in `index.py`. The summary line `[index] Converged: N/M` is printed to stdout unconditionally (not just in verbose mode) at the end of every index run (index.py lines ~581–582). M2 step 1 now captures this output to `/tmp/m2_index.log` and step 2 explicitly instructs the executor to find the `[index] Converged: N/M` line and compute rate = N/M × 100. "Should print" language removed entirely.

---

**FLAW-8** (SERIOUS) — M4 is review=false for behavior-changing code refactors  
**Resolution: FIXED.**  
M4 set to `review=true`. The reviewer receives M3's structured change list and M4's applied changes, and verifies they match. Additionally, M4's verification step upgraded: step 5 now runs pipeline import verification (no API calls) to catch runtime breaks before M5. (Step 5 further revised by FLAW-17 — see below.)

---

**FLAW-9** (SERIOUS) — M8 is review=false for first external-facing documentation  
**Resolution: FIXED.**  
M8 set to `review=true`. Reviewer instructions added: "Verify every command in the document against `current-state.md` and `.claude/CLAUDE.md`. Flag any CLI flag, verb, or install instruction that doesn't match the documented state."

---

**FLAW-10** (MINOR) — No mission bumps the version to 0.4.1  
**Handled:** Added as step 4 in M7 (version bump): update `pyproject.toml` and `src/pidgin/__init__.py` to `"0.4.1"`. M9 step 2 now EXPECTs `pidgin.__version__ == "0.4.1"`. FAIL: SOFT on mismatch.

---

**FLAW-11** (MINOR) — M2 "comparison baseline" language is misleading  
**Handled:** M2's context now explicitly states: "The reference numbers come from the calibration experiment (not the nest — the nest is overwritten by this run)." The phrase "calibration entries serve as a comparison baseline" has been removed. M5 similarly uses "calibration reference numbers" throughout.

---

**FLAW-12** (STYLE) — M7 step 4 numbered as OUT OF SCOPE  
**Adopted.** Deferred items moved to a non-numbered section below the steps.

---

**FLAW-13** (STYLE) — M5 step 1 deletes nest without noting recoverability  
**Adopted as improvement (low effort).** M5 step 1 now includes: "Recovery: if subsequent steps fail, run `python scripts/load_calibration.py` to restore the calibration nest from the raw data files." This is a one-line addition with zero risk.

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
