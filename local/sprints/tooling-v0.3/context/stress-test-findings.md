# Stress Test Findings

First real-world Pidgin run: OpenAI Python SDK, April 27 2026.

## Environment

- Repo: openai-python (cloned to local/repos/openai-python)
- Pidgin installed editable via pyproject.toml
- venv: tools/.venv (Python 3.14, openai 2.32.0)

## Test 1: Full repo index (6530 functions)

```
pidgin index . --write-db
```

Result: `Error: <html><head><title>413 Payload Too Large</title></head>...`

Root cause: 6530 × 5 calls = 32,650 JSONL lines. Each line includes full converge.xml preamble (~30KB). Total payload ~980MB. Cloudflare rejects at upload.

## Test 2: Resources subdirectory (1698 functions)

```
pidgin index ./src/openai/resources --write-db
```

Result: `[index] Converged: 0/1698` — instant return, no wait.

Root cause: Same 413. Batch submitted, immediately failed. run_batch_generation returned all results with error fields. Index verb reported "Converged: 0/1698" with no error message. Silent failure.

OpenAI batch listing confirmed: `batch_69efc000... failed total=0`

## Test 3: Chat subdirectory (79 functions, batch path)

```
pidgin index local/repos/openai-python/src/openai/resources/chat --write-db
```

Result: `[index] Converged: 0/79` — instant return.

Root cause: Same payload size issue. 79 × 5 = 395 lines × 30KB ≈ 12MB. Still too large.

## Test 4: 2 functions, forced sync

```python
results = run_embedding_mld_pipeline_for_functions(funcs[:2], dispatch='sync')
```

Result: 2/2 converged. Chat: cluster=8, AsyncChat: cluster=11. 15 candidates each. Pipeline works perfectly.

Proof: the core pipeline is sound. The bug is exclusively in batch payload sizing.

## Test 5: Chat subdirectory (79 functions, forced sync)

```
pidgin index local/repos/openai-python/src/openai/resources/chat --write-db --sync
```

Result: IN PROGRESS at time of writing. Expected: ~5 min for 79 functions sequential.

## Secondary Findings

1. **Nest location wrong.** Index created nest at `./src/openai/resources/chat/.pidgin/nest/` instead of repo root. Nest should follow git root.

2. **init didn't bootstrap.** Fixed live by adding ensure_nest() and CLAUDE.md write to init verb.

3. **dotenv path.** batch.py hardcodes absolute path. Works for fe-toolkit only. Should use env vars directly.

4. **6530 functions is too many.** OpenAI SDK has thousands of auto-generated Pydantic stubs. Need --exclude globs and/or file-type filtering. Real client code is ~200-300 functions.

5. **pyproject.toml needed for installation.** Created with setuptools, packages.find restricted to pidgin*. Editable install works. pidgin.egg-info added to .gitignore.

## Batch Size Analysis

What works:
- 10 requests per batch: all sprint batches completed (10+ successful runs)
- 20 requests: M6 live test, 20/20 completed
- 75 requests: M7 live test, 75/75 completed
- 300 requests: M15 mega-batches, 300/300 completed

What fails:
- 6530 functions (32,650 requests): "The batch input file is larger than the 209715200 maximum for the gpt-4.1-nano model." 200MB file size limit.
- 1698 functions (8,490 requests): "Enqueued token limit reached for gpt-4.1-nano in organization. Limit: 2,000,000 enqueued tokens." Org-level queue limit.

Two independent ceilings:
1. **File size:** 200MB per batch file. With ~30KB preamble per request, max ~6600 requests per file.
2. **Enqueued tokens:** 2M tokens across ALL active batches per org. With 7.5K token preamble, max ~266 requests enqueued simultaneously. This is the binding constraint.

Chunking design must respect both: small files (100 requests each) AND pipelined submission (wait for completions before submitting more chunks).
