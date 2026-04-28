# pidgin/pipeline/

Batch and sync dispatch paths for MLD generation and embedding. V2 pipeline with
auto-threshold routing (DP4: n_tasks >= 10 → batch; n_tasks < 10 → sync).
Anthropic batch path (M9) added for gate-style structured-output requests.

## Files

### batch.py
OpenAI and Anthropic Batch API dispatch for generation and embedding requests — build
JSONL, submit, poll, and parse results. Anthropic path uses tool-use structured output
with ephemeral cache_control on the system block.

| Symbol | Kind | DOES |
|--------|------|------|
| `GenerationRequest` | type | Hold custom_id, preamble, payload, model, max_tokens, and optional response_format for one OpenAI batch request. |
| `GenerationResult` | type | Hold custom_id, drafts list, raw_response dict, and optional error string for one OpenAI batch result. |
| `EmbeddingRequest` | type | Hold custom_id and text for one embedding batch request. |
| `EmbeddingResult` | type | Hold custom_id, vector (length 256 or None), and optional error string for one embedding result. |
| `FunctionMldResult` | type | Hold function name, 15 candidate descriptions, parallel vectors, cluster_size, and converged flag. |
| `AnthropicBatchRequest` | type | Hold custom_id, cached_preamble (→ system block with cache_control), payload, model, max_tokens, and optional response_schema for one Anthropic batch request. |
| `AnthropicBatchResult` | type | Hold custom_id, text (None when tool_use path), parsed (dict from tool input), raw_response, and optional error string for one Anthropic batch result. |
| `build_jsonl` | fn | Build a JSONL string from GenerationRequest objects; each line is a POST to /v1/chat/completions with system=preamble, user=payload. |
| `build_embedding_jsonl` | fn | Build a JSONL string from EmbeddingRequest objects; each line is a POST to /v1/embeddings with text-embedding-3-small at 256 dims. |
| `should_use_batch` | fn | Return True if the OpenAI Batch API should be used; auto mode uses DP4 threshold (n_tasks >= 10). |
| `parse_batch_results` | fn | Parse output and error JSONL from a completed generation batch into GenerationResults using four-shape draft fallback. |
| `parse_embedding_results` | fn | Parse output and error JSONL from a completed embedding batch into EmbeddingResults using four-shape vector fallback. |
| `run_batch_generation` | fn | Submit generation requests to OpenAI Batch API, poll until terminal status, download output, and return parsed GenerationResults. |
| `run_batch_embedding` | fn | Submit embedding requests to OpenAI Batch API, poll until terminal status, download output, and return parsed EmbeddingResults. |
| `run_embedding_mld_pipeline_for_functions` | fn | Run the full generation + embedding MLD pipeline for a list of function dicts; returns one FunctionMldResult per function. |
| `run_anthropic_batch` | fn | Submit AnthropicBatchRequests to the Anthropic Batches API, poll until ended, stream results, and return AnthropicBatchResults in input order. |

### geometry.py
Cosine similarity, centroid, and antipode cluster test helpers for the MLD
convergence pipeline. Extracted from tools/utils/mld.py v0.1.

| Symbol | Kind | DOES |
|--------|------|------|
| `cosine_similarity` | fn | Compute cosine similarity between two float vectors; returns float in [-1, 1]. |
| `centroid` | fn | Compute the element-wise mean of a list of float vectors. |
| `spherical_variance` | fn | Return 1 - ||mean(unit_vectors)||; 0 = perfect consensus, 1 = scatter. |
| `convergence_verdict` | fn | Return ("CONVERGED"\|"DIVERGENT"\|"AMBIGUOUS", sv_dict) by comparing spherical variance across draft_1, draft_2, draft_3 tier groups. |

### candidates.py
Adaptive candidate generation with expansion policy — generate an initial batch,
evaluate cluster convergence ratio, optionally expand with a second pass, and
append a JSONL audit entry. Implements adaptive-candidates.md.

| Symbol | Kind | DOES |
|--------|------|------|
| `ExpansionConfig` | type | Hold accept_ratio, expand_ratio, expanded_accept_ratio, initial_n_calls, expansion_n_calls, and drafts_per_call; validates thresholds at construction. |
| `CandidateEvaluation` | type | Hold function_name, initial_ratio, expanded flag, expanded_ratio, converged flag, n_candidates_total, cluster_size, candidates list, and vectors list for one evaluation result. |
| `evaluate_with_expansion` | fn | Run adaptive candidate generation for one function: generate initial batch, branch on ratio vs. thresholds, optionally expand, append JSONL audit entry, return CandidateEvaluation. |

### mld.py
V2 MLD pipeline extracted from tools/mld/pipeline.py with dispatch parameter.
Adds `dispatch: Literal["auto","sync","batch"]` to the `mld()` entry point.
Sync and batch paths produce identical downstream shape — convergence math unchanged.

| Symbol | Kind | DOES |
|--------|------|------|
| `MLDResult` | type | The chosen description for an input plus pipeline-stage metadata. |
| `mld` | fn | Find the V2 minimum lossless description for input_text via parallel/batch generation, embedding, antipode convergence, and validation. |

## How to Navigate

1. Find the symbol in the table above.
2. Use awk to find its start line:
   `awk '/^def build_jsonl/{ print NR; exit }' pidgin/pipeline/batch.py`
3. Use awk to find where the next symbol starts.
4. Read the range: lines START..END-1.

## Dispatch Decision (DP4)

```
should_use_batch(n_tasks, "auto") → True  iff n_tasks >= 10
should_use_batch(n_tasks, "sync") → False  (always sync)
should_use_batch(n_tasks, "batch") → True  (always batch)
```

## Four-Shape Draft Fallback (parse_batch_results)

1. `{"draft_1":..,"draft_2":..,"draft_3":..}` — observed in live test (gpt-4.1-nano)
2. `{"drafts":[..]}` — dict with drafts list
3. `[...]` — bare JSON array
4. Bare string split on `\n\n`

## Four-Shape Embedding Response (parse_embedding_results)

1. `{"data":[{"embedding":[...]}]}` — standard OpenAI response shape
2. `{"embedding":[...]}` — flat dict with embedding key
3. `[...]` — bare vector list
4. `{"vector":[...]}` — dict with vector key

## convergence_verdict Draft-Decay Test

Computes `spherical_variance` (1 - ||mean(unit_vectors)||) independently for
each of the three draft tiers (draft_1, draft_2, draft_3). Strictly decreasing
sv1 > sv2 > sv3 = CONVERGED. Strictly increasing = DIVERGENT. Non-monotone =
AMBIGUOUS. No threshold — the monotone relationship between the three values
is the test. Both batch and sync paths use this function; `FunctionMldResult`
stores the verdict string plus sv1/sv2/sv3 floats.

## Anthropic Batch Surface (M9)

`run_anthropic_batch` uses `client.messages.batches.create(requests=[...])`.
Each request carries:
- `system`: list with one `{"type":"text","text":preamble,"cache_control":{"type":"ephemeral"}}` block
- `messages`: `[{"role":"user","content":payload}]`
- When `response_schema` is set: `tools=[{"name":"gate_verdict","input_schema":schema}]`
  and `tool_choice={"type":"tool","name":"gate_verdict"}`

Polling checks `processing_status` field; terminal values: `"ended"`, `"canceling"`, `"expired"`.
Results are streamed via `client.messages.batches.results(batch_id)` — each item has `.custom_id`
and `.result`. Succeeded results carry `.result.message` with `.content` blocks; tool_use blocks
expose `.input` as the parsed dict.

### Gate Call Pattern

```python
requests = [
    AnthropicBatchRequest(
        custom_id="gate-00",
        cached_preamble=gate_preamble,  # gate.xml above CACHE BOUNDARY
        payload=gate_payload,           # gate.xml <payload> block with vars filled
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        response_schema={"type":"object","properties":{"valid":{"type":"boolean"},"reason":{"type":"string"}},"required":["valid","reason"]},
    )
]
results = run_anthropic_batch(requests)
# results[0].parsed == {"valid": True, "reason": "..."}
```

### Live Test (M9, 2026-04-27, claude-haiku-4-5-20251001)

10 gate requests, gate.xml preamble cached ephemerally:

| ID | valid | reason (excerpt) |
|----|-------|-----------------|
| gate-00 | True | Imperative verb "Call"; names delegate function |
| gate-01 | True | Imperative verb "Merge"; faithful to body |
| gate-02 | True | (no reason) |
| gate-03 | True | Imperative verb "Return"; accurate |
| gate-04 | True | Imperative verb "Compute"; no hedging |
| gate-05 | False | Starts with "The" — criterion 1 violated |
| gate-06 | False | Trailing comma — truncated mid-clause |
| gate-07 | True | Imperative verb "Deeply" |
| gate-08 | False | Criterion 4: unfaithful to function body |
| gate-09 | True | Imperative verb "Build"; faithful |

Wall time: ~472s (Anthropic batch API processes asynchronously)
