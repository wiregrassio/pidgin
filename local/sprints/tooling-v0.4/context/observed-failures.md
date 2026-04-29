# Observed Failures — OpenAI SDK Indexing

Raw failure log from real-world indexing attempts, April 27-28 2026.

## Environment

- Target: openai-python (cloned to local/repos/openai-python)
- Pidgin v0.3 (post-sprint, all 19 missions applied)
- Python 3.14, tools/.venv, openai 2.32.0
- .env symlinked from local/.env to project root (later moved to root)

## Run 1: Full repo via batch (FAILED — 413)

```
pidgin index . --write-db
```
- Discovered 6530 public functions
- Batch upload rejected: "The batch input file is larger than the 209715200
  maximum for the gpt-4.1-nano model"
- Error swallowed — reported "Converged: 0/6530" with no error message
- This was pre-M2 (error surfacing). Would now show the actual error.

## Run 2: Resources subdirectory via batch (FAILED — 413)

```
pidgin index ./src/openai/resources --write-db
```
- Discovered 1698 public functions
- Same 413 failure, same silent swallowing
- Additionally hit: "Enqueued token limit reached for gpt-4.1-nano.
  Limit: 2,000,000 enqueued tokens."
- Two independent ceilings confirmed:
  - 200MB file size limit per batch
  - 2M enqueued tokens per org across all active batches

## Run 3: Chat subdirectory via batch (FAILED — 413)

```
pidgin index local/repos/openai-python/src/openai/resources/chat --write-db
```
- Discovered 79 public functions
- Still 413 — 79 × 5 calls × 30KB preamble ≈ 12MB
- Reported "Converged: 0/79" silently

## Run 4: 2 functions via sync (SUCCESS)

```python
results = run_embedding_mld_pipeline_for_functions(funcs[:2], dispatch='sync')
```
- 2/2 converged. Chat: cluster=8, AsyncChat: cluster=11
- Proof that the core pipeline works; batch upload is the only problem

## Run 5: Chat subdirectory via sync (SUCCESS)

```
pidgin index local/repos/openai-python/src/openai/resources/chat --write-db --sync
```
- 72/79 converged (91%). Nest written, queryable.
- Query "create chat completion" returned correct result at 0.764 similarity.

## Run 6: Responses subdirectory via sync (SUCCESS)

```
pidgin index local/repos/openai-python/src/openai/resources/responses --write-db --sync
```
- 94/150 converged (63%). Nest written, queryable.
- Async cleanup error on exit (cosmetic — Event loop is closed)

## Run 7: Other subdirectories via sync (EMPTY)

```
pidgin index .../embeddings --write-db --sync → 0 functions
pidgin index .../files --write-db --sync → 0 functions  
pidgin index .../batches --write-db --sync → 0 functions
```
- Parser found 0 public functions in each
- Root cause: these are single-file modules or class-only modules where
  the AST parser doesn't extract class methods, only module-level functions
- Known limitation: parser.py only extracts `def` at module level

## Run 8: Full repo with exclude via batch (POST-v0.3, CANCELLED)

```
pidgin index local/repos/openai-python --exclude "*/types/*" --exclude "*/types/**"
```
- Discovered 4930 public functions (types excluded)
- Batch chunking (M1) working — submitted in chunks of 100
- 3-5 batches completed in ~40 minutes (~300 functions)
- Operator Ctrl+C'd to move to background terminal
- ALL RESULTS LOST — nest writes are end-of-run only
- Restarted: idempotency showed 0 unchanged, 4930 new (nothing persisted)
- Operator cancelled second run, decided to wait for reliability fixes

## Key Metrics

| Run | Functions | Converged | Rate | Path | Duration |
|-----|-----------|-----------|------|------|----------|
| 5   | 79        | 72        | 91%  | sync | ~10 min  |
| 6   | 150       | 94        | 63%  | sync | ~15 min  |
| 8   | ~300/4930 | unknown   | —    | batch| ~40 min (cancelled) |

## Batch API Observations

- 100 requests per batch takes ~10 minutes to complete (observed)
- 2 concurrent batches = ~200 requests every 10 minutes
- 4930 functions × 5 calls = 24,650 requests = 247 batches
- Estimated total: ~20-27 hours for full SDK via batch
- Sync path: ~1 function per 8 seconds = ~11 hours for 4930 functions
- Neither path is fast. Fine-tuning (eliminating 7.5K preamble) would
  dramatically reduce batch payload size and potentially speed up processing.

## Nest Discovery Issues

- init max_depth=4 didn't reach nests created deep in subdirectories
  (chat nest was at depth 7 from fe-toolkit root)
- Empty parent nest shadowed populated child nests in discovery
- Fixed for v0.3 by M3 (nest at git root), but the depth limit and
  shadowing are worth revisiting
