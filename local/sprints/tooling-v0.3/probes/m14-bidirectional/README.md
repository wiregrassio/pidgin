# M14 — Bidirectional MLD Probe

## Goal

Test the central V2 hypothesis empirically: that MLD descriptions are
**lossless** under round-trip. M3 validated the **code → description**
direction (4/4 probes converged at 15/15). M14 tests the
**description → code** direction. If the geometry holds in BOTH
directions, the MLD is a true bidirectional artifact and Phase 5
(sprint-plan-as-artifact) unlocks. If it does not, the convergence we
observed in M3 may be a one-way property of code embeddings, and the
artifact-as-MLD plan defers to v0.3.

## Method

For each of 5 probes we:

1. Take the converged description from M3 (or, for the synthesized 5th
   probe, a hand-crafted description that mirrors the function's
   docstring algorithm block).
2. Render it through `expand.xml` against `gpt-4.1-nano` to produce
   N=10 implementation candidates.
3. Embed every candidate using the canonical store config
   (`text-embedding-3-small`, 256 dim, via
   `pidgin.pipeline.batch.run_batch_embedding`).
4. Run `antipode_test` to get the dominant-cluster size.
5. Repeat each (probe, budget) cell 3 times for stability.
6. Score: cluster_size ≥ 6 of 10 AND ast.parse-valid count ≥ 6 AND
   the cluster centroid implementation is semantically correct
   (operator review).

## Probes

| ID | Function | Class | Description (first 80 chars) | Source |
|----|----------|-------|------------------------------|--------|
| P1 | embed_for_store | data-flow | Call embed_text with store model, dimension, and input text to gen | M3 |
| P2 | main | control-flow | Parse CLI args, read text, embed it, write JSON vector. | M3 |
| P3 | apply | state-mutation | Update the state with delta, remove keys if delta value is None. | M3 |
| P4 | merge | numeric/geometric | Merge dictionaries a and b, prioritizing b if prefer_b is true. | M3 |
| P5 | antipode_test | complex | Compute the centroid of vectors, score each vector's cosine simil | synthesized |

### P1 — embed_for_store (data-flow)

A single delegating call. The description names two constants
(`store model`, `dimension`) and the delegate (`embed_text`). The
question: can the model reconstruct the right delegate-call shape from
those four nouns? P1 stresses **identifier recall**.

### P2 — main (control-flow)

A 5-line argparse-and-print body — the toy probe used in M3, not the
production `tools/embed.py:main`. The description compresses four
behaviors (parse, read, embed, write) into nine words. P2 stresses
**verb-to-statement expansion** and ordering.

### P3 — apply (state-mutation)

Mutates a copy of state with delta values, deleting keys when the delta
value is `None`. The description names the conditional deletion but
omits the `strict` flag's KeyError behavior. P3 stresses **what the
description leaves implicit**: does the model add the strict-flag check
even though the description doesn't mention it? If yes, the description
is *not* lossless — the model is reading from the signature alone.

### P4 — merge (numeric/geometric)

A one-line conditional dict-spread. The description fully captures
behavior; this is the **easiest** probe and serves as a positive
control. If P4 fails, the harness itself is broken.

### P5 — antipode_test (complex)

Centroid + cosine similarity + adaptive mean threshold + index list.
The description is dense but complete (synthesized from the function's
own algorithm comment block). P5 stresses **multi-step numeric flow**
and **the limits of stdlib-only expansion** — the production
implementation uses numpy; expand.xml rule 4 forbids numpy unless the
description names it. We expect the model to produce a stdlib-only
mean / dot-product implementation that is semantically equivalent.

## Parameter Choices

### Why N=10 (not 15)

M3 used N=15 (3 drafts × 5 calls). M14 uses N=10 because:

1. The expand schema is `{"implementation": "..."}` — single field, no
   three-draft fallback. So N candidates = N batch requests, not N/3.
   Holding cost flat against M3 means N=10.
2. DP4 batch threshold is exactly 10. N=10 keeps every (probe, budget,
   run) cell on the batch path with no special-case sync routing.
3. antipode_test's dominant-cluster ratio is robust at N=10 — six of
   ten is the same hypothesis as nine of fifteen (60%) but with
   discrete integer thresholds that survive small-sample noise better.

### Why budget extremes (50, 200) only

M3 swept four budgets (8, 16, 24, 32) for descriptions. M14 generates
implementations, not descriptions. Function bodies vary from 1 line
(`merge`) to 15+ lines (`antipode_test`). Two budgets cover the range:

- **50 tokens**: pressure test. Forces concise implementations; long
  bodies must be aggressively compressed. If P5 converges at 50, the
  model genuinely understands the algorithm; if it doesn't, the
  description is information-sufficient but the budget is the bottleneck.
- **200 tokens**: comfortable. All five probes fit easily. This is the
  "fair" measurement of whether the description-space contains enough
  information to reconstruct the code.

We skip middle values (75, 100, 150) because the cost cap is $1.00 and
because the binary low/high contrast is more informative for an
**existence proof** (does it converge at all) than a sweep would be.
A sweep is appropriate once we know whether the geometry holds; that is
M16's job, not M14's.

### Why stability=3 runs

A single run could converge by luck or fail by transient model noise.
Three runs at each (probe, budget) cell gives a 0/1/2/3 convergence
count. Stable convergence = 3/3; stable divergence = 0/3. Anything in
between is "ambiguous" and is reported to M16's gate logic as
inconclusive for that probe.

We do not run 5 or 10 stability runs because:

- 30 cells (5 × 2 × 3) at N=10 is 300 generation calls — already at
  the batch dispatch sweet spot.
- Going to 50 cells doubles cost without doubling information; the
  marginal value of run 4 over run 3 is small when the verdict is
  already 3/3 or 0/3.

### Why convergence threshold 6/10

The threshold is a **defensible hypothesis**, not yet a calibrated
constant. The reasoning:

1. M3 used 8/15 (53%) for descriptions and observed 15/15 actual
   convergence on every passing probe. The geometry was NOT close to
   the threshold; it was overwhelming.
2. 6/10 (60%) is a slightly stricter ratio. Code embedding space may
   be less convergent than description space (see Architectural
   Reasoning below), so a stricter threshold guards against false
   positives.
3. We pair the geometric threshold with **two semantic gates**:
   - syntactic validity (ast.parse) ≥ 6/10
   - cluster centroid is semantically correct (operator review)
4. These two together mean a probe declared "converged" must have at
   least 6 implementations that (a) are real Python and (b) cluster
   tightly in 256-dim space. That is a stronger claim than M3's
   description convergence, which only required cluster cohesion.

If 6/10 turns out to be too strict (probes converge geometrically at
4/10 but the implementations are obviously equivalent on inspection),
M16 will flag this for v0.3 calibration with a larger probe set.
If it turns out to be too lax (probes converge at 8/10 but the
implementations are subtly wrong), M16 will tighten.

## Cost Projection

Generation: 5 probes × 2 budgets × 3 runs × N=10 = **300 calls**
- gpt-4.1-nano batch pricing: $0.05 / $0.20 per million tokens (in/out)
- avg input: ~1500 tokens (cached preamble + payload) → 1500 × 300 = 450K tokens → $0.0225
- avg output (200 budget cap): ~120 tokens × 300 = 36K tokens → $0.0072
- **Generation total: ~$0.030**

Embedding: 300 candidates max → 300 embedding calls
- text-embedding-3-small batch pricing: $0.01 per million tokens
- avg candidate: ~120 tokens × 300 = 36K → $0.0004
- **Embedding total: ~$0.0004**

**Combined: ~$0.030 — well under the $1.00 cap.**

The cost cap is more about runtime caution than budget. Batch jobs
take 5–25 minutes each; we issue 30 generation batches and 30
embedding batches sequentially. Total wall time estimate: 1–4 hours.

## M16 Gate Criteria

Per the sprint plan, M16 will collapse the 30 records to a 5-row
verdict table (one row per probe). For each probe, count how many of
the 6 cells (2 budgets × 3 runs) declared `converged=True` AND had
syntactically_valid_count ≥ 6 AND had a semantically correct cluster
centroid. Then:

- **stable_converged := stable_cells ≥ 4 of 6**
- **stable_diverged := stable_cells ≤ 1 of 6**

Across the 5 probes:

| Outcome | Count | Action |
|---------|-------|--------|
| **UNLOCK** | 4 or 5 of 5 stable_converged | Phase 5 unlocks. Ship sprint-plan-as-artifact. |
| **AMBIGUOUS** | 3 of 5 stable_converged | Operator decides. Probable v0.2.5 calibration sprint. |
| **DEFER** | ≤ 2 of 5 stable_converged | Phase 5 defers to v0.3. Document what failed and why. |

The gate is asymmetric on purpose — UNLOCK requires a strong majority
because Phase 5 is a forward commitment with downstream implications,
while DEFER is the safe-by-default outcome.

## Architectural Reasoning — Why Code Embedding Space May Differ

V2 MLD's bet is that the embedding model sees descriptions and code
through the same geometry. The evidence for this is indirect: both
modalities are token sequences, the embedding model is multilingual
(natural language + code), and M3 demonstrated tight clustering in
description space.

But there are three structural reasons code-space convergence may
**diverge** from description-space convergence:

1. **Surface variance**. Descriptions have one canonical phrasing
   per concept (Origami's whole point). Code has many — `dict(state)`
   vs `state.copy()` vs `{**state}` are the same operation written
   three ways. Embedding may not collapse all three to the same
   neighborhood.
2. **Boilerplate dominance**. Code is mostly boilerplate (signatures,
   imports, return statements) and a small spike of behavior. The
   embedding may be dominated by the boilerplate, not the behavior,
   so two implementations of the same description may cluster more
   by their syntactic shape than by their semantics.
3. **Model bias toward verbosity**. gpt-4.1-nano with a 200-token
   budget tends to expand. It may add type hints the signature does
   not request, helper variables, or inline comments. Boilerplate
   variance compounds (1) and (2).

If these effects are large enough, P4 (`merge`, one-liner) will
converge cleanly because there is no boilerplate room, P3 / P1 will
converge moderately, and P2 / P5 (longer functions) may not converge
at all. That outcome would be a 2/5 result and trigger DEFER. It would
not invalidate V2 MLD — it would mean the artifact-as-MLD bet needs a
different mechanism (perhaps MLD-driven AST normalization before
embedding) before Phase 5 ships.

Conversely, if 4/5 or 5/5 probes converge cleanly across both budgets
and all stability runs, the geometry is real in both directions and
the bet is empirically validated. The sprint plan as artifact becomes
a buildable thing in v0.3.

## Files in this directory

- `README.md` — this document
- `probes.json` — probe metadata (5 entries)
- `harness.py` — pipeline driver; importable, runs only when called
- `results.json` — written by `harness.main()` in M15 (not present in M14)

## Provenance

- M3 probe outputs: `../m3-converge-xml/`
- v0.1 baseline: `../../../tooling-v0.1/context/v2-mld-validation.md`
- expand.xml: `/project/pidgin/prompts/expand.xml`
- Reference implementations: see `probes.json` per-probe paths
