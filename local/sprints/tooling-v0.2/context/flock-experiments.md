# Flock Experiments — Findings

## What we tested

During the v0.2 design session, we ran a series of experiments applying
MLD convergence geometry to sprint plan generation. The question: can
a flock of cheap models (gpt-5-nano, gpt-5.4-nano) replace a single
Opus call for authoring sprint plans?

## Experiment 1: One-shot generation (gpt-5-nano)

- 30 calls, $0.25 budget, 20K max tokens, 10 parallel
- 16/30 produced valid XML (53%), 509 total missions extracted
- Per-mission convergence: 0.88–0.96 avg cosine similarity
- Tightest: M4 (0.9552) — most precisely specified in design
- Loosest: M1 (0.8824) — first mission, no prior pattern
- Finding: specification density drives convergence. Well-specified
  missions cluster tight. Underspecified missions diverge.
- Finding: per-mission embedding works. Individual missions are
  well under the 8192 token embedding limit.
- Finding: regex fallback extracts valid missions from broken XML.
  A plan with 17/19 valid missions contributes 17 data points.

## Experiment 2: Selector (Haiku judgment over nano candidates)

- Geometry picked top 3 per mission from 1,135 variants
- Haiku walked M1→M19 sequentially, selecting or synthesizing
- Result: structurally correct but substantively thin. Nano
  converges on structure, not substance.

## Experiment 3: Iterative batch (gpt-5.4-nano)

- 19 positions × 10 candidates each via OpenAI Batch API
- $1.15 total with 50% batch discount
- 175/190 valid (92%), convergence 0.95–0.97 across all positions
- Cache hits reached 81% by M2 (OpenAI auto-caching)
- Inline risks: 4 per mission, severity-tagged
- Output: dense, executor-ready specs with function signatures,
  dataclasses, validation scripts, backup/rollback

## Experiment 4: Independent comparison (fresh Opus judge)

Compared the Opus /new-sprint one-shot against the iterative batch.

**Opus won.** The iterative plan drifted from the design's intent:
- M14 replaced real API-bound probes with deterministic hash proxies
- M17-M19 reduced multi-pass compression to string concatenation
- Phase 4/5 could not answer the design's gate question

The iterative plan had better mechanical rigor (risks, shell scripts,
backup steps) but worse design fidelity. The judge's summary:
"Plan A reads like an executable specification grounded in v0.1.
Plan B reads like a competently-written greenfield Python sprint
that happens to share names with the design."

## Key findings

### The flock/architect split

Nano models excel at volume generation, mechanical elaboration, and
convergence testing. They fail at design interpretation, intent
preservation, and reasoning about speculative features.

Opus excels at design fidelity, architectural judgment, and intent
preservation. It's too expensive for volume generation.

The correct pipeline: Opus writes intent, the flock elaborates,
Opus validates.

### Pidgin is the flock

The flock's natural role is infrastructure: indexing repos, populating
nests, laying eggs, running CRISPR edits, validating diffs. Mechanical
work at scale for pennies. It doesn't think. It retrieves, compresses,
validates, and converges.

### Batch economics

- OpenAI Batch API: 50% discount, separate rate limits, no 429s
- gpt-5.4-nano at batch pricing: ~$0.05/mission for 10 candidates
- Full 19-mission iterative plan: $1.15
- Cache hits: 62% on first position, 81%+ by second
- gpt-5-nano is a reasoning model (temperature locked to 1.0,
  burns tokens on deliberation). gpt-5.4-nano is not.
- Anthropic rate limits (10K output tokens/minute on Haiku) make
  it unsuitable for volume generation at current tier.

### Convergence geometry works on documents

Per-mission embedding produces meaningful similarity scores.
Specification density (how much the design pre-decides) predicts
convergence tightness. This is the same pattern MLD showed on
function descriptions — the less the model has to improvise,
the tighter the cluster.

### Temperature is an uninvestigated variable

gpt-5-nano locks temperature to 1.0. gpt-5.4-nano doesn't.
Temperature sweep as independent variable against convergence
is an open research question.

## What this means for v0.3

The iterative batch pipeline works. The generation, embedding,
convergence, and selection infrastructure is validated. The missing
piece is intent preservation — which requires either a smarter
generation model or a validation layer that catches drift.

The research direction: Opus writes N mission intents (short,
one paragraph each). The flock expands each into full specs.
Opus reviews expansions for drift. Three-pass pipeline:
intent → elaboration → validation.
