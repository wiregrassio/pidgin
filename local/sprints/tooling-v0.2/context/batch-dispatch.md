# Batch Dispatch

V2's MLD pipeline makes sequential async API calls and hits rate limits on large repos. The OpenAI Batch API is purpose-built for this workload: identical preambles with varying payloads, processed asynchronously at 50% cost discount with separate, higher rate limits.

## The Economics

Standard synchronous pricing for GPT-4.1 nano:
- Input: $0.10/MTok
- Cached input: $0.025/MTok
- Output: $0.40/MTok

Batch API pricing: 50% discount across the board. The cached preamble — which is the majority of every MLD call after the first — costs $0.0125/MTok instead of $0.025/MTok. For a 500-function repo at 10 calls per function, the savings are meaningful in aggregate.

Rate limits: the Batch API has a separate, higher rate limit pool. Using batch does not consume standard per-model rate limits. The rate limiting problem V2 hit during M14 (Origami reprocessing) is eliminated entirely.

## The Pattern

MLD convergence for one function requires two API round trips: generation, then embedding. For bulk operations, both can be batched.

**Round trip 1 — Generation batch.** One JSONL file. Each line is a generation request with the identical system prompt (cached preamble) and a different function body as payload. For 500 functions × 5 calls × 3 drafts = 7,500 lines. One upload, one batch submission. `custom_id` encodes `{file}:{function}:{call_index}`.

**Round trip 2 — Embedding batch.** After generation results arrive, embed all candidates. The embedding endpoint also supports batching. One JSONL file with all candidate strings. One upload, one batch submission. Results arrive with custom_id mapping back to the source function.

**Local computation.** Convergence geometry (antipode test, cosine similarity, centroid computation) runs locally on the returned vectors. No API call needed. This is pure numpy — the math is already in the pipeline.

**Round trip 3 (optional) — Gate batch.** All gate calls have the same preamble. The candidates and their metadata vary. One JSONL file with all gate requests. If the number of gate calls is under the auto-threshold, run synchronously instead.

Total: 2-3 API round trips for an entire repo, instead of thousands of sequential calls.

## Auto-Threshold

The user should not need to think about dispatch mode.

- Under 10 tasks: synchronous. Immediate feedback. What a CLI user expects when indexing a single file or running a quick query.
- Over 10 tasks: batch. With a clear message: "Batching 190 requests. Estimated completion: 30-120 seconds. Use --sync to force sequential."
- `--sync` flag forces synchronous regardless of task count. For debugging, for watching individual calls, for small interactive jobs.
- `--batch` flag forces batch regardless of task count. For when you know you want batch on a small job (e.g., testing the batch path).

The threshold of 10 is a design-time default. It may change after empirical testing. The principle: small interactive jobs are synchronous, bulk operations are batched, the user always knows which mode they're in.

## Origami Reprocessing Example

19 principles × 10 calls per principle × 3 drafts = 570 generation requests. Current V2 pipeline: 570 sequential calls, hitting rate limits, taking ~15 minutes. With batch: one JSONL file, one upload, one submission. Results back in seconds to minutes. Then one embedding batch for all candidates. Then local convergence math. Then one gate batch. Total wall time: under a minute instead of fifteen.

## Implementation Notes

`api.py` gains a batch dispatch path alongside the existing synchronous path. The pipeline's `mld()` function gains a `dispatch` parameter (sync | batch | auto). The auto mode counts tasks and selects. The batch path:

1. Build JSONL lines with the prompt + payload for each call
2. Write to a temporary file
3. Upload via Files API
4. Submit batch via Batches API
5. Poll for completion (with exponential backoff)
6. Download results
7. Parse responses by custom_id
8. Feed into convergence geometry

The synchronous path is unchanged. Both paths produce the same data structures downstream. The convergence algorithm doesn't know or care whether candidates arrived synchronously or from a batch.

## Anthropic Batching

Anthropic's Message Batches API follows a similar pattern. Gate and selection calls that go to Anthropic models can be batched the same way. The Opus selection call — used when the candidate set is ambiguous — is the most expensive per-call operation. Batching it across functions reduces cost and avoids per-model rate limits.

## Cost Projection

A 500-function repo at batch pricing:
- Generation: 500 functions × 5 calls × ~1000 input tokens/call = 2.5M input tokens at $0.05/MTok = $0.125
- Embedding: 500 functions × 15 candidates × ~50 tokens/candidate = 375K tokens at $0.01/MTok = $0.00375
- Gate: 500 functions × 1 call × ~500 tokens/call = 250K tokens at $0.05/MTok = $0.0125
- Total: ~$0.14 (vs ~$0.28 synchronous)

At this price, re-index on every PR.
