# Tooling Sprint v0.4.1 — Design

**Status:** DRAFT  
**Date:** 2026-04-29  
**Repo:** github.com/wiregrassio/pidgin  

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

**M6 (Index full SDK):** Killed on context window exhaustion during batch polling. Stale and out of scope for this sprint.

### What the Calibration Proved

12,600 API calls (126 functions × 25 calls × 4 temperatures × 3 drafts), 37,638 embedded vectors. Findings are definitive:

1. **Draft 3 is worse, not better.** At t=0.3, draft 1 mean sv=0.0626, draft 3 mean sv=0.0941. Token compression scatters, it doesn't converge. Drop drafts 2 and 3.
2. **Temperature 0.3 is 2.7× tighter than t=1.5.** Lock at 0.3. Do not mix.
3. **Pooling drafts hurts.** Mean sv pooled=0.1075, draft 1 only=0.0626. Every single function gets worse when you include drafts 2 and 3.
4. **Threshold: sv < 0.10 gives 81% convergence at N=25.** Functions above sv=0.15 are all genuinely complex multi-purpose constructs.
5. **N=10 is sufficient.** Mean deviation from N=25 reference: 0.0095 — an order of magnitude smaller than the threshold.
6. **Body length doesn't predict convergence** (correlation 0.169). Semantic clarity matters, not size.

The convergence test is now one line:
```python
converged = spherical_variance(draft_1_vectors) < 0.10
```

### The Calibration Load

126 functions loaded into `.pidgin/nest/` via `scripts/load_calibration.py` using the correct test (sv < 0.10 on draft_1 at t=0.3):
- **102 CONVERGED** (sv < 0.10)
- **19 AMBIGUOUS** (sv 0.10–0.15)
- **5 DIVERGENT** (sv > 0.15): `classify_batch_results`, `MLDResult`, `AssembledPrompt`, `generate`, `EditOp`

All 126 are queryable. `pidgin query "compute spherical variance"` returns 0.833 similarity. These are the reference numbers.

### Migration

Pidgin extracted from fe-toolkit to its own repo (github.com/wiregrassio/pidgin). Src layout. Sprint history moved. Fe-toolkit stripped.

---

## Scope

Three phases, 9 missions.

| Phase | Gate | Missions |
|-------|------|----------|
| 1: Convergence Rewrite | M2 GREEN | M1, M2 |
| 2: Pidgin Works on Itself | M5 GREEN | M3, M4, M5 |
| 3: Hardening and Docs | M9 GREEN | M6, M7, M8, M9 |

**Phase 1 is the blocking track.** Nothing in Phase 2 dispatches until the convergence smoke test passes. Phase 3 can proceed once Phase 2's re-index is clean.

---

## Phase 1: Convergence Rewrite

The pipeline generates 3 drafts per call, uses the wrong convergence test, and doesn't lock temperature. All three must be fixed together — they're one coherent change.

### M1 — Convergence Pipeline Rewrite

**Tier:** execute  
**Review:** true  
**Depends on:** nothing (first mission)

**Context:** The convergence test in geometry.py and batch.py is wrong. `convergence_verdict()` checks whether sv decreases from draft 1 → draft 3 (sv1 > sv2 > sv3). Calibration proved draft 3 always has *higher* variance than draft 1. The pipeline also generates 3 drafts per call and uses uncontrolled temperature. The exact spec is in `local/sprints/tooling-v0.4.1/context/convergence-rewrite.md`.

**Objective:** Rewrite the convergence-related code in geometry.py, batch.py, mld.py, and converge.xml to match the calibration findings: 1 draft per call, temperature 0.3, 10 calls, sv < 0.10.

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
   - Remove duplicate example if present (carry-forward from v0.4 cherry-pick list).
   - Fix contradictory role section (carry-forward).
   - EXPECT: schema has exactly one field `description`. No draft language in instructions. FAIL: HARD.

3. **batch.py** (`src/pidgin/pipeline/batch.py`):
   - Change `ADAPTIVE_MAX_BATCHES = 5` to `ADAPTIVE_MAX_BATCHES = 10`.
   - Change all generation calls to use `temperature=0.3` explicitly.
   - Change generation from 3 drafts per call to 1 draft per call (`n=1`).
   - Update `FunctionMldResult`: remove fields `sv1`, `sv2`, `sv3`, `convergence_verdict`, `per_draft_centroid`, `per_draft_tightness`, `per_draft_n`. Add `sv: float = 0.0` and `converged: bool = False` driven by `is_converged()`.
   - Replace convergence check call with `is_converged(vectors)` from geometry.py.
   - Simplify `_extract_drafts()`: primary shape becomes `{"description": "..."}`. Keep fallback for robustness but make `{"description": str}` the first-checked shape.
   - `_stratify()` may remain for telemetry but must not be called in the convergence decision path.
   - EXPECT: `ADAPTIVE_MAX_BATCHES` is 10, temperature is 0.3 on all generation calls, `convergence_verdict` is not referenced, `FunctionMldResult` has `sv` and `converged` fields. FAIL: HARD.

4. **mld.py** (`src/pidgin/pipeline/mld.py`):
   - Apply the same changes as batch.py for the single-function path: 1 draft per call, temperature=0.3, `is_converged()` for the convergence check.
   - Remove any per-draft-tier logic from the single-function path.
   - EXPECT: mld.py imports `is_converged` from geometry.py. No draft-tier references. FAIL: HARD.

5. **Verify imports:**
   - All references to `convergence_verdict` across the codebase must be gone.
   - `is_converged` must be imported wherever convergence is checked.
   - EXPECT: `grep -r "convergence_verdict" src/` returns nothing. FAIL: HARD.

**Report must include:**
- Lines changed per file (geometry.py, batch.py, mld.py, converge.xml)
- Final state of `FunctionMldResult` fields (list them)
- Final state of `is_converged` signature
- Output of `grep -r "convergence_verdict" src/` (must be empty)
- Any carry-forwards encountered

---

### M2 — Convergence Smoke Test

**Tier:** execute  
**Review:** false  
**Depends on:** M1 GREEN

**Context:** M1 rewrote the convergence pipeline. This mission verifies the rewrite produces the expected results on the actual pidgin codebase. Reference numbers come from the calibration loading: 102 CONVERGED, 19 AMBIGUOUS, 5 DIVERGENT. The existing nest has 126 functions loaded from calibration. We are NOT clearing the nest — we are re-indexing into it so the existing calibration entries serve as a comparison baseline.

**Objective:** Confirm the corrected pipeline produces ~81% convergence on pidgin's own codebase and that the 5 known divergent functions remain divergent.

**Steps:**

1. Run: `pidgin index . --sync --verbose`
   - EXPECT: Command exits 0. Functions are processed. No crashes.
   - FAIL: HARD on non-zero exit.

2. After indexing, run: `pidgin query "compute spherical variance"`
   - EXPECT: Returns a result with similarity ≥ 0.75. The top result should be `geometry.py:spherical_variance` or similar.
   - FAIL: SOFT if below 0.75 (note result and continue).

3. Check convergence rates. The index verb should print per-function convergence status in `--verbose` mode, or query the nest for `converged` field.
   - EXPECT: At minimum 65% of indexed functions report `converged=True`. (Calibration reference is 81%; the live run may vary slightly due to model nondeterminism but should not be dramatically lower.)
   - FAIL: HARD if convergence rate is below 50% (indicates the fix didn't work).

4. Verify the 5 known divergent functions. Query or inspect nest entries for:
   `classify_batch_results`, `MLDResult`, `AssembledPrompt`, `generate`, `EditOp`
   - EXPECT: Each of these 5 functions has `converged=False` and `sv > 0.10`.
   - FAIL: SOFT if any one is now converged (note it — it may be an improvement, not a bug).

5. Document total function count indexed, final convergence breakdown (converged / ambiguous / divergent counts and percentages), and the sv values for the 5 known divergents.

**Report must include:**
- Exit code and any error output from `pidgin index . --sync`
- Query result for "compute spherical variance" (top result, similarity score)
- Total functions indexed, convergence rate, converged/ambiguous/divergent counts
- sv values for the 5 known divergent functions
- PASS/FAIL verdict with reasoning

**Phase 1 Gate:** M2 must be GREEN (convergence rate ≥ 50%, no crashes) before Phase 2 dispatches.

---

## Phase 2: Pidgin Works on Itself

The calibration identified 5 divergent functions. The operator's stance: "cattle, not pets, understandable, modular." These functions get a review pass. If they can be simplified, simplify them. If they're genuinely complex, accept the divergence and document it. Then re-index from scratch.

### M3 — Review 5 Divergent Functions

**Tier:** reason  
**Review:** true  
**Depends on:** M2 GREEN (sv values confirmed)

**Context:** The calibration identified 5 functions with sv > 0.15 that the pipeline cannot converge on. High sv means the model produces semantically different descriptions on different runs — the function is doing too many things or the boundaries are unclear. The operator's stance is "cattle, not pets, understandable, modular" — if a function can be made simpler without losing correctness, it should be. If it can't, accept the divergence and document why.

The 5 functions and their calibration sv values:
- `MLDResult` (sv=0.28) — dataclass with many fields and complex metadata
- `generate` (sv=0.19) — multi-purpose: schema, structured output, async, cost tracking
- `classify_batch_results` (sv=0.19) — unclear why divergent at this level
- `EditOp` (sv=0.18) — multi-step: replace lines, handle payload, manage offsets
- `AssembledPrompt` (sv=0.15) — borderline, dataclass with preamble/payload split

**Objective:** For each of the 5 divergent functions, deliver a written verdict (SIMPLIFY with specific changes, or ACCEPT with reasoning) and a consolidated change plan for M4.

**Steps:**

1. For each of the 5 functions, read the full implementation. Assess:
   - Does the function do more than one thing?
   - Is the ambiguity coming from unclear naming, mixed concerns, or genuine complexity?
   - Can the function be split, renamed, or simplified without changing behavior?
   - Would a split reduce the divergence, or is the complexity load-bearing?

2. Apply the operator's criteria: "understandable, modular." A function is understandable if a reader can state what it does in one sentence. A function is modular if it has one reason to change.

3. Produce a verdict for each function:
   - **ACCEPT** — Function is genuinely complex or correctly multi-step. Document why one-sentence description is impossible. No change.
   - **SIMPLIFY** — Function has separable concerns. Specify the exact change: rename, split into N functions, extract helper. Changes must be behavior-preserving.

4. Produce a consolidated M4 change list: file, function, specific action, expected outcome. If all verdicts are ACCEPT, state "M4 is vacuous — zero changes."

**Report must include:**
- Verdict for each of the 5 functions (ACCEPT or SIMPLIFY)
- For each SIMPLIFY verdict: exact proposed change (file, function, specific action)
- M4 change list (or "M4 is vacuous" if no SIMPLIFY verdicts)
- Reasoning for each verdict

---

### M4 — Apply Divergent Function Refactors

**Tier:** execute  
**Review:** false  
**Depends on:** M3 GREEN

**Context:** M3 produced a verdict for each of the 5 divergent functions. This mission applies the approved SIMPLIFY changes. If M3's report states "M4 is vacuous," close this mission immediately as GREEN with zero changes.

**Objective:** Apply all SIMPLIFY changes from M3's change list. Preserve behavior.

**Steps:**

1. Read M3's change list from the sprint log.
2. If the change list is empty or M3 stated "M4 is vacuous": report GREEN, zero changes, mission complete.
3. For each SIMPLIFY item: apply the specified change. No interpretation — follow M3's spec exactly. If M3's spec is ambiguous for a specific item, note it as a carry-forward and skip.
4. After all changes: run `python -c "import pidgin"` to verify the package still imports.
5. Run `pidgin index . --sync --dry-run` (or equivalent) to confirm no import errors surface.

**Report must include:**
- List of changes applied (file, function, what changed)
- List of items skipped (if any) with reason
- Output of `python -c "import pidgin"` (must succeed)
- Any carry-forwards

---

### M5 — Fresh Full Re-index

**Tier:** execute  
**Review:** false  
**Depends on:** M4 GREEN (or M4 vacuous GREEN)

**Context:** The nest currently contains 126 functions loaded from calibration data. M4 may have changed some functions. This mission clears the nest and re-indexes from scratch using the corrected pipeline from Phase 1. This is the first fully live run of the corrected pipeline.

**Objective:** Produce a clean self-indexed nest with convergence rates consistent with the calibration reference (102/19/5 split or similar).

**Steps:**

1. Delete the existing nest: `rm -rf .pidgin/nest/`
2. Re-initialize: `pidgin init`
   - EXPECT: `.pidgin/nest/` is created. FAIL: HARD.
3. Re-index: `pidgin index . --sync`
   - EXPECT: Exits 0. Functions processed.
   - FAIL: HARD on non-zero exit or crash.
4. Run query verification:
   - `pidgin query "compute spherical variance"` — EXPECT: top result at ≥ 0.75 similarity.
   - `pidgin query "batch MLD dispatch"` — EXPECT: returns batch.py or pipeline results.
   - `pidgin query "write files atomically"` — EXPECT: returns write/ module results.
5. Document total function count, convergence breakdown (converged/ambiguous/divergent), and any functions that changed status from the M2 run (due to M4 refactors or model nondeterminism).

**Report must include:**
- Total functions indexed
- Convergence breakdown: converged N (%), ambiguous N (%), divergent N (%)
- sv values for the 5 originally-divergent functions (or their replacements if M4 split them)
- Query results for the 3 test queries (top result + similarity for each)
- Any functions that changed convergence status compared to M2
- PASS/FAIL verdict

**Phase 2 Gate:** M5 must be GREEN before Phase 3 dispatches.

---

## Phase 3: Hardening and Docs

Carry-forward debt from v0.3 and v0.4, rate limit handling, and the first user-facing documentation.

### M6 — Rate Limit Hardening

**Tier:** execute  
**Review:** false  
**Depends on:** Phase 2 gate (M5 GREEN)

**Context:** `src/pidgin/utils/api.py` has basic retry logic: `_is_retryable()` detects 429s, and both the Anthropic and OpenAI call paths retry up to 3 times with a fixed-multiplier backoff (`await asyncio.sleep(1.0 * (2 ** attempt))` — delays of 1s and 2s). There is no jitter, no Retry-After header respect, and only 3 attempts. The calibration hit the 200K TPM ceiling ~30 times. At t=0.3 rate limits are rare but will occur on large repos.

**Objective:** Upgrade the retry logic in api.py to exponential backoff with full jitter and Retry-After header support.

**Steps:**

1. In `api.py`, update the retry logic in both the Anthropic call path (`_one_anthropic_call`) and the OpenAI call path:
   - Increase max attempts from 3 to 5.
   - Replace fixed-multiplier sleep with full jitter:
     ```python
     import random
     BASE_DELAY = 1.0
     MAX_DELAY = 60.0
     delay = random.uniform(0, min(MAX_DELAY, BASE_DELAY * (2 ** attempt)))
     await asyncio.sleep(delay)
     ```
   - Before sleeping, check for a `Retry-After` header on the exception. If present and parseable as a number of seconds, use `max(delay, float(retry_after))` as the sleep duration.
   - EXPECT: Both call paths use full-jitter backoff with 5 attempts. FAIL: HARD if either path is unchanged.

2. `_is_retryable()` already detects 429 and 5xx. No changes needed unless the implementation is clearly wrong.

3. Verify the package still imports and the api.py module loads without errors:
   `python -c "from pidgin.utils.api import generate"`
   - EXPECT: No errors. FAIL: HARD.

**Report must include:**
- Final sleep formula used (copy the exact code)
- Confirmation both call paths (Anthropic and OpenAI) were updated
- Import verification output

---

### M7 — Carry-Forward Debt Cleanup

**Tier:** execute  
**Review:** false  
**Depends on:** Phase 2 gate (M5 GREEN)

**Context:** Several cosmetic and correctness issues have accumulated across sprints. These are all one-line or small fixes that don't warrant their own missions. The list below is exhaustive for this sprint. Items marked OUT OF SCOPE are deferred deliberately.

**Objective:** Apply all in-scope carry-forward fixes in one pass.

**Steps (each item is independent; apply all, note any that can't be applied cleanly):**

1. **Hardcoded paths in candidates.py** (`src/pidgin/pipeline/candidates.py`):
   - Lines ~86, ~96 contain `/Users/elliotwillis/Desktop/fe-toolkit/...` paths as defaults.
   - Remove or replace with `None` defaults; if these are dead function parameters, remove the whole parameter.
   - EXPECT: No `/Users/elliotwillis` paths in candidates.py. FAIL: SOFT (note and continue).

2. **Stale DEPENDS comment in mld.py** (`src/pidgin/pipeline/mld.py`):
   - There is a stale comment referencing `tools.utils.api` (the old module path from fe-toolkit).
   - Update or remove the comment.
   - EXPECT: No `tools.utils.api` references in mld.py. FAIL: SOFT.

3. **Cosmetic in index.py** (`src/pidgin/verbs/index.py`, line ~65):
   - "requests errored." — incomplete sentence in error message.
   - Fix to a complete, clear error message.
   - EXPECT: Message is a complete sentence. FAIL: SOFT.

4. **OUT OF SCOPE — Deferred to next sprint:**
   - `function_dict_hash` / `function_source_hash` divergence (non-trivial schema change)
   - Identity key portability (absolute file path in nest ID — requires nest migration)

5. After all changes: `python -c "import pidgin"` must succeed. FAIL: HARD if it doesn't.

**Report must include:**
- List of changes applied (file, line range, what changed)
- List of items skipped with reason
- Import verification output
- Carry-forwards for next sprint (hardcoded in the OUT OF SCOPE list above)

---

### M8 — docs/pidgin.md

**Tier:** execute  
**Review:** false  
**Depends on:** Phase 2 gate (M5 GREEN); M7 may run concurrently

**Context:** Pidgin has no user-facing documentation. The CLAUDE.md files are agent-facing references, not human onboarding. This mission writes the first external document explaining what Pidgin is and how to use it.

**Objective:** Write `docs/pidgin.md` — a complete, accurate, usable document for a developer who has never seen Pidgin.

**Sections to include:**

1. **What is Pidgin** — LLM-native toolkit for indexing codebases via MLD. The goal: queryable semantic descriptions of every public function in a repo, stored in a per-repo vector database. One paragraph.

2. **How MLD works** — The pipeline. Extract public functions from source. For each function, generate 10 descriptions at t=0.3 (1 draft per call). Embed each description. Compute spherical variance of the embedding cluster. If sv < 0.10, the function has converged — the centroid embedding is the stored description. Include the calibration data summary: 81% convergence rate, 37,638 vectors, empirically derived threshold.

3. **Installation** — `pip install pidgin` (or `pip install -e .` for dev). OPENAI_API_KEY required.

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
- Do not invent features that don't exist. Check current-state.md and the CLAUDE.md files.
- Target length: 400–700 words. Dense and useful, not padded.

**Report must include:**
- Confirmation that docs/pidgin.md was written
- Word count
- Any features mentioned that weren't verified against the codebase (flag them)

---

### M9 — Final Verification

**Tier:** scout  
**Review:** false  
**Depends on:** M6 GREEN, M7 GREEN, M8 GREEN

**Context:** All missions are complete. This scout pass verifies the repo is in a clean, releasable state before the operator tags and pushes v0.4.1.

**Objective:** Confirm the repo is clean, the pipeline works end-to-end, and there are no obvious regressions.

**Steps (read-only, no modifications):**

1. `git status` — EXPECT: working tree clean. Note any unexpected tracked changes.
2. `python -c "import pidgin; print(pidgin.__version__)"` — verify version string exists.
3. Check `pyproject.toml` — version field should be present. Note the current value.
4. Run three queries and record results:
   - `pidgin query "compute spherical variance"`
   - `pidgin query "index a repository"`
   - `pidgin query "write files atomically"`
   - EXPECT: Each returns at least one result with similarity ≥ 0.70.
5. `grep -r "convergence_verdict" src/` — EXPECT: empty. Note if not.
6. `grep -r "/Users/elliotwillis" src/` — EXPECT: empty. Note if not.
7. Check docs/ directory exists and contains pidgin.md (from M8).

**Report must include:**
- `git status` output
- Current version string from `pidgin.__version__` and pyproject.toml
- Query results for all 3 test queries (top result + similarity)
- Whether `convergence_verdict` or hardcoded paths were found (should be clean)
- Overall verdict: READY TO TAG / ISSUES FOUND

**After M9:** The operator reviews the report and manually tags v0.4.1 and pushes.

---

## Decision Points

### DP1: Convergence rate below target at M2

If M2 reports convergence below 50% (not just below 81%), the Phase 1 rewrite has a bug. Stop Phase 2, issue an amendment to M1.

If M2 reports 50–70% convergence, this is within model nondeterminism range. Proceed to Phase 2, note the deviation.

### DP2: M3 SIMPLIFY verdicts require significant refactors

If M3's SIMPLIFY verdicts would require changes to public API signatures or nest schema (not just internal restructuring), escalate to the operator before M4 dispatches. M4 is scoped to behavior-preserving internal changes only.

### DP3: M4 introduces import errors

If `python -c "import pidgin"` fails after M4's changes, stop Phase 2 gate. Fix before M5.

### DP4: M5 fresh re-index diverges significantly from M2

If the Phase 2 gate re-index produces fewer than 60% converged functions (vs. ~70-81% expected), investigate before proceeding to Phase 3. This would indicate M4's refactors introduced semantic noise or the pipeline has a regression.

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

---

## Carry-Forwards to Next Sprint

- Identity key portability (absolute path in nest ID, makes nest non-portable)
- `function_dict_hash` / `function_source_hash` divergence
- P1 bidirectional probe still at 3/6 (description precision measurement)
- `converge.xml` anti-examples audit (may anchor model on failure patterns — deferred)
- SDK indexing (external repo indexing) — blocked until pipeline is verified correct on self-indexing
