# Operational Reliability

This is the blocking track. Nothing else in v0.4 ships until these are solid.
The operator will not run large index jobs until these are implemented.

## Problem Statement

Pidgin's index pipeline is all-or-nothing. A 27-hour job that fails at hour 26
loses everything. The operator lost ~300 functions worth of API calls ($0.06)
when Ctrl+C killed a run before the nest write. This must never happen again.

## R1: Incremental Nest Writes

**Current behavior:** The pipeline collects all results in memory, then writes
the entire nest at the end of the run.

**Required behavior:** Write results to the nest as each batch of functions
completes. After every batch chunk (100 requests = ~20 functions), upsert the
converged results into ChromaDB immediately.

**Implications:**
- The nest is always up-to-date with whatever has completed so far
- Ctrl+C at any point loses at most the current in-flight batch (~20 functions)
- Restarting triggers idempotency (M13): already-written functions show as
  unchanged, only remaining functions are new
- The SFT data writer (M18) should also write incrementally
- File-level summaries should generate per-file as that file's functions complete,
  not in a bulk pass at the end

**Design constraint:** ChromaDB supports concurrent writes but the current
upsert_function_descriptions call expects all results at once. Need to either:
- Call it per-batch with a subset of results
- Or accumulate a write queue and flush after each batch

**Testing:** Index 50 functions, Ctrl+C after 20, restart, verify unchanged=20
new=30 on the second run.

## R2: Graceful Shutdown

**Current behavior:** KeyboardInterrupt produces a full Python traceback (50+ lines
of httpx/asyncio internals). No cleanup, no summary, no partial save.

**Required behavior:** Catch KeyboardInterrupt at the top level of the index verb.
On interrupt:
1. Cancel any in-flight batch polling (don't wait for completion)
2. Write whatever results have been collected so far to the nest
3. Print a clean summary: "Interrupted. Wrote N/M functions to nest. Resume with
   the same command to continue."
4. Exit 130 (standard SIGINT exit code)

**The async cleanup error** (RuntimeError: Event loop is closed) that appeared in
the v0.3 stress tests should also be suppressed — it's cosmetic but alarming.

**Testing:** Start an index run, Ctrl+C during polling, verify clean output and
partial nest write.

## R3: Progress Tracking

**Current behavior:** Terminal is silent for hours during batch polling. The only
output is the initial discovery line and the final convergence summary.

**Required behavior:** After each batch completes, print a progress line:

```
[batch 3/247] 300/4930 functions | 215 converged (71.7%) | ~4h 12m remaining
```

Components:
- Batch number / total batches
- Functions processed / total functions
- Converged count and percentage (running total)
- Estimated time remaining (based on observed batch completion rate)

Also print when a batch is submitted and when it starts being polled:
```
[batch 4/247] submitted, polling...
```

For --verbose mode, print per-function results as they complete:
```
  ✓ create (converged, cluster=8, tightness=0.94)
  ✗ AsyncChat (not converged, cluster=3)
```

**Implementation:** The progress printing should happen inside the batch pipeline,
not the index verb. The pipeline already knows batch boundaries — it just doesn't
emit anything.

## R4: Abandoned Batch Recovery

**Current behavior:** When Pidgin is killed during a run, any batches that were
already submitted to OpenAI continue processing. Their results are available for
24 hours via the Batch API. Pidgin has no way to know about them on restart.

**Required behavior:** Before starting a new index run, check for completed
OpenAI batches that match the current run's custom_id pattern. If found, download
their results and apply them to the nest before submitting new batches.

**Design:**
- Pidgin already uses custom_ids that encode the function name + call index
- On startup, list recent batches (last 24h), filter by status=completed,
  check if any custom_ids match functions in the current run's to-index list
- If matches found, download results, process them (embed, converge, upsert)
- Then proceed with the remaining unprocessed functions

**This is optional for v0.4 but highly desirable.** The alternative is accepting
the wasted API spend and re-running. With incremental writes (R1) and graceful
shutdown (R2), the window for abandoned batches shrinks dramatically — but it
doesn't go to zero (network failures, machine crashes, OOM kills).

**Testing:** Submit a batch manually, kill Pidgin, restart, verify recovery.

## Implementation Order

R1 (incremental writes) → R2 (graceful shutdown) → R3 (progress) → R4 (recovery)

R1 is the foundation. R2 depends on R1 (shutdown writes partial results). R3 is
independent but most useful after R1/R2. R4 is a nice-to-have that can be deferred
to v0.5 if the sprint is full.
