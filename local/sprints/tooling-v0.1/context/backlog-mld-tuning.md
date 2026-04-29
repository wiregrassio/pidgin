# Backlog: MLD Pipeline Tuning

Depends on: tooling-v1 complete, /technologic working end-to-end.

## Soft Budget

Current approach hard-caps `max_tokens` at the budget value (8, 16,
24, 32). This forces truncation — the model is mid-thought when the
API cuts it off. Trailing commas, mid-word artifacts, incomplete
clauses all result from this.

Proposed: set `max_tokens` to 32 (or higher) and instruct the model
to be as concise as possible. The model finds its natural stopping
point. Some descriptions will be 8 tokens, some will be 22. The
natural length becomes the real complexity signal — not the
convergence budget, which empirically measures cloud tightness, not
semantic complexity (see M7-E validation: main() converged at lower
budget than embed()).

Benefits:
- No truncation artifacts — grammar filter sees complete sentences
- Natural length IS the complexity metric, not an indirect proxy
- Varying-length candidates near the centroid become input for
  higher-tier judgment

## LLM Validation Replacing Mechanical Grammar Filter

The grammar filter rejected 0/140 candidates across 54 runs. It
adds safety overhead but doesn't reduce the candidate pool. At
n=5 candidates per tier, mechanical filtering is unnecessary —
the volume doesn't justify it.

Proposed: replace the grammar filter with LLM validation. Pass
the centroid-nearest candidate plus 3-4 alternatives (varying
lengths, all near centroid) to Sonnet or Opus. The validator
makes the judgment call with full context: is 12 tokens or 14
tokens better? Is the shorter version lossless or did it drop a
behavior? Does the longer version add real information or just
words?

This collapses the generate → filter → embed → converge → validate
pipeline into generate → embed → converge → validate, with the
validator doing both quality and completeness checking.

The mechanical filter remains as a pre-check for obvious failures
(empty strings, non-imperative starts) but the real quality gate
is the LLM.

## Opus for Final Selection

When soft-budget candidates cluster near the centroid at varying
lengths (8, 12, 14, 18 tokens all close to center), pass the full
set to Opus in one call. Opus sees the function, all candidates,
their lengths, their distances from centroid, and makes the final
selection. One Opus call per function, applied to pre-filtered
candidates where judgment adds value.

This is the same tier pattern as the rest of the system: cheap
models generate, expensive models judge. The difference is that
judgment now includes length-vs-completeness tradeoff, not just
"pick the best description."

## Provider Strategy

Documented during M7-E validation. The split:
- OpenAI (GPT-4.1 nano): all generation. Non-reasoning, $0.10/MTok,
  automatic caching, no rate limit bottleneck.
- Anthropic (Haiku): validation tier when call count justifies
  caching (≥7 calls for break-even at 4,096 token prompt).
- Anthropic (Opus): full-corpus analysis (/digest), final
  MLD selection when candidate set is ambiguous.
- Marionette agents stay on Anthropic — tool calls against live
  infrastructure require higher trust.

## Voyage AI Embedding Migration

MongoDB acquired Voyage AI (Feb 2025). voyage-3.5-lite at $0.02/MTok
matches OpenAI text-embedding-3-small pricing with better retrieval
quality. Atlas automatic embedding (preview) generates vectors on
ingest using Voyage models — eliminates the embed.py call for Base
Camp documents entirely.

Migration: update embed.py with --provider flag (openai, voyage),
default to voyage. Add VOYAGE_API_KEY to local/.env. Existing Base
Camp documents re-embed on next update. MLD convergence geometry
can stay on OpenAI (ephemeral, never stored) or switch — no cost
difference at $0.02/MTok either way.

## Open Questions

- Soft budget token ceiling: 32? 48? 64? Higher ceiling means more
  output tokens per candidate. At GPT-4.1 nano's $0.40/MTok output,
  doubling from 32 to 64 max adds ~$0.001 per run. Negligible.
- Dedup before embedding: if >50% of candidates are identical at
  a given budget, rerun generation once. Helps models with low
  variance (Haiku) without changing the algorithm.
- converged=False path: still unvalidated empirically. Need a
  function with genuinely equivocal semantics. Candidate:
  `def merge(a, b, prefer_b=True): return {**a, **b} if prefer_b else {**b, **a}`
- dotenv override=True: one-line fix in api.py, keeps getting
  deferred. Fix in Mission 9.
