# v0.4 Cherry-Pick List

v0.4 ran in fe-toolkit before the migration. M1-M5 shipped GREEN. M6+ is
stale or irrelevant (fe-toolkit-specific scope). The code changes from
M1-M5 are already in this repo (synced during migration).

## Shipped and Present (M1-M5)

**M1: Batch chunking.** 100 requests per JSONL, 2 concurrent batches,
pipelined submission. In pipeline/batch.py. Working.

**M2: Error surfacing.** first_error field on FunctionMldResult, propagated
from generation failures. Index verb prints real error and exits 1 on
ALL_ERRORED. Working. Cosmetic carry-forward: index.py:65 "requests errored."

**M3: Nest at git root.** find_project_root() walks up to .git. Index writes
to repo root nest regardless of which subdirectory is indexed. Working.

**M4: Class method extraction.** Parser extracts public methods from classes
(no leading underscore, not __dunder__ unless __init__). Unblocked SDK
subdirectories that were class-only. Working.

**M5: Gate model switch.** Validated gpt-4.1-mini against haiku on G1-G5
probes. Mini actually caught a factually wrong description that haiku
accepted. Gate calls switched to gpt-4.1-mini. Working.

## Shipped but Needs Rework

**P1: Convergence rewrite.** Replaced antipode_test with spherical_variance
and convergence_verdict. But convergence_verdict uses the draft-decay test
(sv1 > sv2 > sv3) which the calibration proved wrong. Needs the simpler
is_converged(vectors, threshold=0.10) replacement. See convergence-rewrite.md.

## Killed (fe-toolkit concerns, not Pidgin)

- M6: Index full SDK (failed on context exhaustion, needs rewrite)
- M7+: Skills rewrite, agent file rewrite, ORIGAMI/CLAUDE.md audit,
  template restructuring — all fe-toolkit scope, not Pidgin

## Carry-Forward Debt from v0.3 and v0.4

- Hardcoded /Users/elliotwillis paths in candidates.py, templates.py
- function_dict_hash diverges from function_source_hash
- Identity key uses absolute file path (nest not portable)
- mld.py stale DEPENDS comment referencing tools.utils.api
- P1 bidirectional probe still at 3/6 (description precision)
- converge.xml: anti-examples may anchor model on failure patterns
- converge.xml: duplicate example, contradictory role section

## Rate Limit Handling (Never Implemented)

Identified in v0.3, scoped in v0.4 wishlist, never got a mission.
The calibration run hit the 200K TPM ceiling ~30 times, mostly at t=1.5.
At t=0.3 (production setting) rate limits are rare but still possible
on large repos. Fix: exponential backoff with jitter on 429 responses.
