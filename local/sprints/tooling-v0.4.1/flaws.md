# Tooling Sprint v0.4.1 — Design Flaws

**Reviewed:** 2026-04-29
**Design:** local/sprints/tooling-v0.4.1/design.md

---

## Flaws

---

FLAW-1: M6 references a non-existent Anthropic API call path
Severity: BLOCKING
Mission: M6

The design says:
> "update the retry logic in both the Anthropic call path (`_one_anthropic_call`) and the OpenAI call path"

The problem: Every context document confirms this project has no Anthropic API dependency. `.claude/CLAUDE.md` states explicitly "No Anthropic API dependency." All three providers (generation, gate, embeddings) are OpenAI. The v0.4 cherry-pick list notes that gate was switched from haiku (Anthropic) to gpt-4.1-mini in M5 — meaning the Anthropic path was removed before this sprint started. The function `_one_anthropic_call` either no longer exists in api.py or exists as unreachable dead code.

What happens if shipped as-is: The execute-tier agent follows specs literally and stops when it can't find `_one_anthropic_call`. The report will note a missing function but may still mark the "Anthropic path" as updated (since it didn't exist to update). Rate limit handling will be shipped against only the OpenAI path, which is what the spec claims to require — but the requirement is stated as "both call paths." Any reviewer reading "both paths updated" in the report will be misled.

Fix: Remove all mention of an Anthropic call path from M6. The spec should say "update the retry logic in the OpenAI call path in api.py." If `_one_anthropic_call` exists as dead code, add a step to delete it.

---

FLAW-2: M8 documents `pip install pidgin` — the package is not on PyPI
Severity: BLOCKING
Mission: M8

The design says:
> "Installation — `pip install pidgin` (or `pip install -e .` for dev). OPENAI_API_KEY required."

The problem: current-state.md records only `pip install -e .` as the install method. The v0.4.1 founding record (#6) says to push a working version to GitHub — not to PyPI. There is no mission that publishes the package. The name "pidgin" is almost certainly already taken on PyPI. If a developer runs `pip install pidgin` they will install a different package entirely.

What happens if shipped as-is: The first piece of user-facing documentation ships with a false installation command. Any developer who follows the quick start will install the wrong package and get confusing import errors.

Fix: Change the Installation section in M8's spec to `pip install -e .` (from GitHub clone) only. Do not document `pip install pidgin` unless a publishing mission exists.

---

FLAW-3: M1 checks for `convergence_verdict` string but not for callers of removed FunctionMldResult fields
Severity: SERIOUS
Mission: M1

The design says:
> "All references to `convergence_verdict` across the codebase must be gone."
> "Update `FunctionMldResult`: remove fields `sv1`, `sv2`, `sv3`, `convergence_verdict`, `per_draft_centroid`, `per_draft_tightness`, `per_draft_n`."

The problem: M1 step 5 verifies `grep -r "convergence_verdict" src/` returns nothing. It does NOT require a grep for `sv1`, `sv2`, `sv3`, or any other removed FunctionMldResult field. `candidates.py` implements adaptive expansion based on convergence decisions. If candidates.py (or any other file) accesses these removed fields — either directly or via attribute unpacking — the code will fail at runtime with AttributeError. The string grep for `convergence_verdict` will pass clean while the codebase is broken.

What happens if shipped as-is: M1 passes its verification. M2 runs `pidgin index . --sync` and crashes on an AttributeError when candidates.py or another caller tries to access `sv1`/`sv2`/`sv3` on a FunctionMldResult that no longer has those fields. Phase 1 fails at M2 with a bug that M1's review could have caught.

Fix: Add a verification step to M1: `grep -rn "\.sv1\|\.sv2\|\.sv3\|per_draft_centroid\|per_draft_tightness\|per_draft_n" src/` must return nothing. FAIL: HARD if any results found.

---

FLAW-4: M3→M4 handoff has no format contract
Severity: SERIOUS
Mission: M3, M4

The design says (M3 report requirements):
> "For each SIMPLIFY verdict: exact proposed change (file, function, specific action)"

The design says (M4 step 3):
> "No interpretation — follow M3's spec exactly. If M3's spec is ambiguous for a specific item, note it as a carry-forward and skip."

The problem: M3 is reason-tier, producing free-form reasoning and a change list. M4 is execute-tier and "follows the spec literally." The phrase "exact proposed change (file, function, specific action)" in M3's report requirements is not enforced — it's a request. A reason-tier agent could write "split `generate` into generation and cost tracking concerns" and satisfy the requirement while producing something M4's execute-tier cannot follow without interpretation. There is no format for the M4 change list (JSON, bulleted steps, diff notation) that M4 is told to expect. The design's escape hatch — "note it as a carry-forward and skip" — means ambiguous M3 output silently results in zero refactors, which is indistinguishable from "all functions ACCEPT."

What happens if shipped as-is: M3 produces a loosely specified change list. M4's executor finds several items ambiguous, skips them as carry-forwards, and reports GREEN with "zero changes applied due to ambiguity." The divergent function problem goes unfixed without any alarm.

Fix: Add a required output format to M3's report: each SIMPLIFY item must include (1) absolute file path, (2) function name, (3) specific action in one of these forms: SPLIT <fn> INTO <fn1>, <fn2> with exact new signatures, or RENAME <old> TO <new>, or EXTRACT <block description> INTO <new_fn_name> with signature. M4 should be told it will receive a structured list in this format.

---

FLAW-5: Phase 1 gate at 50% doesn't prove the fix works; DP1 misstates the math
Severity: SERIOUS
Mission: M2, design-level

The design says:
> "Phase 1 Gate: M2 must be GREEN (convergence rate ≥ 50%, no crashes) before Phase 2 dispatches."

And DP1 says:
> "If M2 reports 50–70% convergence, this is within model nondeterminism range. Proceed to Phase 2, note the deviation."

The problem: This is wrong on the numbers. Calibration Finding 5 shows N=10 has a mean deviation of 0.0095 from the N=25 reference (which produces 81%). "Model nondeterminism" at N=10 would explain a deviation of ~5-10 percentage points from 81%, putting the expected range at roughly 70-91%. A result of 50-70% is NOT within nondeterminism range — it indicates either the pipeline fix is incomplete or there's a regression. The 50% floor makes Phase 2 proceed with a half-broken pipeline, which then taints M5's "clean" re-index with incorrect convergence data.

What happens if shipped as-is: M2 produces 58% convergence (pipeline has a partial bug), the gate passes, Phase 2 runs, M5 produces a self-indexed nest with wrong convergence data, and the project ships with the same fundamental problem it started with — just less severe.

Fix: Raise the Phase 1 gate to ≥ 70%. Update DP1: "50–70% is not nondeterminism — it's a pipeline bug. Stop and issue an amendment to M1." The 81% reference is at N=25; N=10 should still produce 70%+ based on the calibration deviation table.

---

FLAW-6: M5 cannot compare against M2's sv values due to per-mission context isolation
Severity: SERIOUS
Mission: M5

The design says (M5 step 5):
> "Any functions that changed convergence status compared to M2"

The problem: Per the mission grammar: "Each mission runs in a fresh agent context." M5 depends on M4. M4 depends on M3. M4's report requirements include "list of changes applied" and "import verification" — not M2's sv values. M3's report requirements include verdicts and change lists — not M2's sv values. M5 receives M4's report. M2's sv data is not in the chain M5 receives.

M5 cannot compare against M2 because M2's report is not passed to M5. The executor will either fabricate the comparison, skip it, or halt in confusion. The grammar is explicit: "If an agent can't proceed from this information alone, the report from the prior mission is insufficient — that's a design problem."

What happens if shipped as-is: M5's report omits the M2 comparison entirely (the executor has no data to compare against), or the executor halts. The step produces no useful output.

Fix: Either (a) require M4's report to include "carry-forward: M2 sv values for the 5 divergents" in a structured format, OR (b) remove the M2 comparison from M5 and replace it with a comparison against the calibration reference numbers (which ARE in the design's context documents that each agent receives).

---

FLAW-7: M2 step 3 checks a feature that may not exist
Severity: SERIOUS
Mission: M2

The design says:
> "The index verb should print per-function convergence status in `--verbose` mode, or query the nest for `converged` field."

The problem: "Should" means the designer doesn't know if this feature exists. current-state.md doesn't list `--verbose` convergence reporting as a "What Works" item. If `--verbose` doesn't print convergence rates, the executor has two fallback options: query the nest (which requires knowing the exact ChromaDB query) or compute the rate from individual records. Neither is specified. The executor is being asked to verify behavior using an undefined method.

What happens if shipped as-is: M2's executor either invents a method to extract convergence rates (producing potentially wrong numbers), queries the nest incorrectly (producing empty results), or reports "unable to determine convergence rate" and fails HARD. Phase 1 gate cannot be evaluated.

Fix: If `pidgin index --verbose` prints convergence status, state that and provide the expected output format. If it doesn't, specify the exact nest query the executor should run to extract convergence counts. "Should print" is not a spec.

---

FLAW-8: M4 is review=false for behavior-changing code refactors with only an import check as verification
Severity: SERIOUS
Mission: M4

The design says:
> "Review: false"

And M4's verification is:
> "run `python -c 'import pidgin'` to verify the package still imports."

The problem: M4 applies refactors to production functions — potentially splitting multi-purpose functions into multiple functions, changing function names, or extracting helpers. These changes affect callers, imports, and potentially the MLD pipeline's semantic output. An import check only verifies the package loads — it does not verify that any caller of the refactored functions still works, that the pipeline still produces correct output, or that the refactored function signatures match what M3 specified.

M3 is reason-tier (judgment-heavy) and M4 is execute-tier (follows literally). The combination of a loosely formatted M3 output (see FLAW-4) with a no-review M4 and an import-only verification is the most likely place in the sprint to introduce a silent regression.

What happens if shipped as-is: M4 applies changes that pass the import check but break `pidgin index . --sync` in ways that surface only in M5. M5 then fails with a crash or wrong convergence rates, and the executor reports a pipeline bug without knowing M4 caused it.

Fix: Set review=true on M4. The reviewer receives M3's change list and M4's applied changes and verifies they match. Alternatively, add a step: `pidgin index . --sync --dry-run` (or equivalent) that exercises the pipeline without writing to the nest, verifying the refactored functions work in context.

---

FLAW-9: M8 is review=false for the first external-facing documentation
Severity: SERIOUS
Mission: M8

The design says:
> "Review: false"

The problem: M8 writes `docs/pidgin.md`, the first document a developer outside the project will read. The design tells M8 "do not invent features that don't exist" — but there is no reviewer to enforce this. A review pass would catch: inaccurate CLI flags, missing OPENAI_API_KEY setup steps, wrong model names, features that were planned but not shipped, or the PyPI install command (FLAW-2 above). The review=false decision means these errors ship unchallenged.

What happens if shipped as-is: docs/pidgin.md ships with documentation errors. A developer follows the quick start, hits a wall (wrong install command, missing env setup, incorrect flag name), and the tool's first impression is broken.

Fix: Set review=true on M8. The reviewer verifies every command in the document against current-state.md and the CLAUDE.md files.

---

FLAW-10: No mission bumps the version to 0.4.1
Severity: MINOR
Mission: design-level

The design says:
> "After M9: The operator reviews the report and manually tags v0.4.1 and pushes."

The problem: M9 step 2 says "verify version string exists" and step 3 says "note the current value." The root CLAUDE.md lists `pidgin.__version__ = "0.2.0"`. No mission updates `pyproject.toml` or `__init__.py` to reflect 0.4.1. The operator will tag a commit as v0.4.1 while the package self-reports as 0.2.0.

What happens if shipped as-is: `import pidgin; pidgin.__version__` returns "0.2.0" while the git tag says v0.4.1. Any downstream consumer pinning to the version string will be misled.

Fix: Add a step to M9 or M7: update the version field in `pyproject.toml` to `0.4.1`. Add it to M9's EXPECT check: `pidgin.__version__` must equal `"0.4.1"`. FAIL: SOFT if not.

---

FLAW-11: M2 "comparison baseline" language is misleading
Severity: MINOR
Mission: M2

The design says:
> "We are NOT clearing the nest — we are re-indexing into it so the existing calibration entries serve as a comparison baseline."

The problem: When `pidgin index . --sync` runs, it upserts into the nest. The calibration entries for the same functions will be overwritten with live pipeline results. After the re-index, the calibration baseline no longer exists in the nest. The actual comparison is between M2's live convergence rate and the hardcoded calibration reference numbers (102/19/5 split) stated in the design. The nest entries do not participate in this comparison.

What happens if shipped as-is: An executor who tries to "compare calibration entries against live entries" in the nest will find only live entries — the calibration baseline has been overwritten. They may spend time attempting a comparison that is structurally impossible, or report the comparison as "unable to perform."

Fix: Replace "the existing calibration entries serve as a comparison baseline" with "the calibration reference numbers (102 CONVERGED / 19 AMBIGUOUS / 5 DIVERGENT from the context documents) are the comparison target." The nest is not the comparison vehicle.

---

FLAW-12: M7 step 4 is numbered as a step despite being labeled OUT OF SCOPE
Severity: STYLE
Mission: M7

The design says (M7 step 4):
> "OUT OF SCOPE — Deferred to next sprint: [list of deferred items]"

The problem: The step numbering includes out-of-scope items as numbered steps. An execute-tier agent processes numbered steps in sequence. Step 4 reads as an instruction before the "OUT OF SCOPE" label clarifies otherwise. The executor must parse the label to determine this is not a task. The step should not exist as a step.

What happens if shipped as-is: Minor confusion. Executor reads step 4, sees "OUT OF SCOPE," skips it. No functional impact, but clutters the spec and creates an unnecessary parsing moment.

Fix: Remove step 4 as a numbered step. Move the deferred items to a "Deferred (not in scope for this mission)" section below the steps.

---

FLAW-13: M5 step 1 deletes the nest without noting recoverability
Severity: STYLE
Mission: M5

The design says:
> "Delete the existing nest: `rm -rf .pidgin/nest/`"

The problem: The nest contains 126 carefully loaded calibration entries. The instruction to delete it is correct for the mission goal, but provides no note that the deletion is recoverable via `scripts/load_calibration.py`. An executor who hesitates or makes a mistake after this step has no guidance on recovery. This is a one-way door with no sign pointing back.

What happens if shipped as-is: If the subsequent `pidgin init` or `pidgin index` crashes, the executor has no nest and no explicit path to restore the baseline. They must infer that load_calibration.py exists and can restore it.

Fix: Add a note after step 1: "Recovery: if subsequent steps fail, run `python scripts/load_calibration.py` to restore the calibration nest from the raw data files."

---

## Summary

**Total flaws by severity:**
- BLOCKING: 2 (FLAW-1, FLAW-2)
- SERIOUS: 7 (FLAW-3 through FLAW-9)
- MINOR: 2 (FLAW-10, FLAW-11)
- STYLE: 2 (FLAW-12, FLAW-13)

**Overall verdict: REJECT**

The design has two blocking flaws that would produce incorrect or false outputs regardless of how well the executor performs. FLAW-1 (Anthropic path that doesn't exist) causes M6 to either silently fail or produce a misleading report. FLAW-2 (PyPI install documentation) ships false instructions in the first external document.

**The single most important thing the designer got wrong:**

The transition from M3 (reason) to M4 (execute) is not a handoff — it's a gap. M3 produces free-form verdicts and M4 is told to "follow exactly" with no format contract, no review, and only an import check as verification. A reason-tier agent producing ambiguous change specs fed to an execute-tier agent with no review is the highest-probability path to a silent regression. The design treats this as the low-risk part of the sprint. It is the highest-risk part.
