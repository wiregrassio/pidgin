# Pipeline Improvements

## Batch Chunking (CRITICAL — blocks all scale work)

Current: all requests go in one JSONL upload. Fails at ~350+ requests because converge.xml preamble (~30KB) is duplicated in every line.

Fix: split into chunks of 100 requests. Submit each as a separate batch. Poll all concurrently. Merge results by custom_id. Implementation: ~30 lines in batch.py's run_batch_generation and run_batch_embedding.

Secondary optimization: OpenAI file-reference or preamble dedup could cut payload 50-100x. Not required for v0.3 — chunking alone solves it.

## Error Surfacing

Current: when a batch fails, run_batch_generation returns all results with error fields. Index verb reports "Converged: 0/N" with no error. The user has no idea the pipeline didn't execute.

Fix: in index verb, if ALL results have errors, print the first error and exit 1. Don't silently write an empty nest.

## Draft Stratification (Per-Draft Centroid Tracking)

Each API call produces draft_1 (120 max tokens), draft_2 (80), draft_3 (60). They are sequential refinements — draft_3 has draft_1 and draft_2 in context.

Proposed: across N calls, compute separate centroids for all draft_1s, all draft_2s, all draft_3s. Measure cluster tightness per draft number. If draft_3 centroids are tighter, within-call refinement works and draft_3 is the strongest signal. If equal, drafts are just shorter, and single-draft-per-call with more calls would be more efficient.

This is free analysis on existing data — retroactively applicable to M3 probe results.

## Adaptive Stopping

Current: fixed N calls per function (default 5, producing 15 candidates).

Fix: compute centroid after each batch of calls. Measure cosine_similarity(centroid_n, centroid_n-1). If sim > 0.99, stop — more candidates won't change the answer. If sim < 0.95 after batch 3, flag for expansion. Cap at 5 batches (50 candidates max).

Implementation: change the generation loop in pipeline/mld.py from fixed count to while loop with convergence check. Per-batch centroid is already computed — just save and compare.

## Import and Signature Tracking

Current: AST walk extracts public function names and bodies. Discards everything else.

Fix: during the same walk, also extract:
- Import statements → dependency graph (file A imports X from file B)
- Function signatures with type hints
- Parameter names and types
- Return type annotation
- Decorators

Store as structured metadata in the nest alongside MLD descriptions. Output as imports.json in .pidgin/. Enables the `depends` verb and cross-module contract analysis.

## Tree-Sitter for Multi-Language

Current: Python's ast module. Python only.

Fix: tree-sitter with Python bindings. Add parser modules per language:
- parser_rust.py (pub fn declarations) — needed for Watchtower
- parser_typescript.py (export function/const) — nice to have
- parser_go.py (func with capital first letter) — nice to have

The MLD pipeline is language-agnostic. Only the parser is language-specific.

## Fine-Tuning Data Collection

Every MLD run produces training data as a side effect:
- Converged winners → "good" examples for SFT
- Non-converged candidates → "bad" examples
- Gate calls → (description, valid/invalid, reason) triples for gate SFT
- Ranked candidates by centroid distance → preference data for DPO

Collect into a JSONL file in .pidgin/ as index runs. When dataset reaches ~2000 examples, fine-tune a nano-class model. If it matches converge.xml+nano accuracy, it replaces the prompt entirely — the fine-tuned model IS the prompt.

## Idempotency

Index should store source_hash (sha256 of function body) per function in the nest. On re-index:
- Hash unchanged → skip (zero API calls)
- Hash changed → re-MLD and update
- Function deleted → prune from nest

Safe for CI, git hooks, repeated runs. Only new/modified code costs money.

## Budget Increase for Bidirectional

Current: b=50/200 (inherited from v0.1 description budgets).
Fix: b=1000+ for bidirectional (description→code). Code bodies are structurally longer than descriptions.
Also: switch expand.xml from JSON-schema response_format to tool-use structured output. Every Phase 4 truncation was the JSON envelope's closing brace.

Cost at b=1000: ~5x current per-candidate. Still negligible — M15 ran 600 calls for $0.03.
