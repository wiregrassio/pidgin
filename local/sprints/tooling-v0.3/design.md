# Tooling v0.3 — Design

## Premise

v0.2 delivered a working Pidgin package with CLI, MLD pipeline, batch dispatch,
and per-repo nests. First real-world stress testing against the OpenAI Python SDK
exposed scaling bugs (batch payload limits, silent error swallowing, nest location)
and revealed the gap between "works on sprint probes" and "works on real codebases."

v0.3 fixes the scaling bugs, reshapes the verb surface for real users, adds
pipeline intelligence (draft stratification, adaptive stopping, import tracking),
and re-gates bidirectional MLD at higher budgets. The sprint also collects
fine-tuning data as a byproduct of every index run.

## Scope

19 missions across 5 phases. Each phase has a clean gate: the previous phase
must be GREEN before the next one dispatches.

## Phase 1 — Scaling Fixes (M1-M5)

These are the bugs that prevent Pidgin from indexing real codebases. Nothing
else matters until these are fixed.

### M1: Batch chunking

Split batch uploads into chunks of 100 requests per JSONL file. Submit each
as a separate OpenAI batch. Poll all concurrently. Merge results by custom_id.
Respect two ceilings: 200MB file size limit and 2M enqueued token limit per org.
Pipeline submission: submit 2 chunks, wait for one to complete before submitting
the next (stay under token ceiling).

Files: pidgin/pipeline/batch.py (run_batch_generation, run_batch_embedding)
Test: index 400+ functions via batch path without error.

### M2: Error surfacing

When ALL results from a batch have error fields set, the index verb must print
the first error message and exit 1. Never silently write an empty nest. Also:
add a --verbose flag that prints per-function status during index runs.

Files: pidgin/verbs/index.py, pidgin/pipeline/batch.py
Test: simulate a batch failure, verify error is printed.

### M3: Nest at git root

Index always resolves the nest location by walking up to .git (reuse
_find_project_root from write model, PD1 from v0.2). `pidgin index ./src/deep/path`
writes to `<repo_root>/.pidgin/nest/`, not `./src/deep/path/.pidgin/nest/`.
Query, init, egg, and depends all resolve the same way.

Files: pidgin/verbs/index.py, pidgin/store/nest.py, pidgin/verbs/query.py
Test: index a subdirectory, verify nest is at git root. Query from repo root.

### M4: dotenv and API key resolution

Remove hardcoded absolute dotenv path from batch.py. Use environment variables
directly (OPENAI_API_KEY, ANTHROPIC_API_KEY). If not in environment, try
load_dotenv() with no path argument (finds .env in cwd or parents). If still
missing, print clear error and exit 1.

Files: pidgin/pipeline/batch.py, pidgin/utils/api.py
Test: run index from a different directory with OPENAI_API_KEY exported.

### M5: File filtering and git boundary

Index should:
- Only process files with supported extensions (.py for now, .rs/.ts/.go later)
- Skip files in .pidgin/, .git/, __pycache__/, node_modules/, .venv/
- Stop at .git boundaries (don't descend into child git repos)
- Support --exclude glob flag for additional filtering
- Report file type breakdown in dry-run output

Files: pidgin/verbs/index.py, pidgin/utils/parser.py
Test: index a repo containing a child git repo, verify child is not indexed.

## Phase 2 — Verb Redesign (M6-M10)

Reshape the CLI for real users. Kill compress, add the new verbs, fix defaults.

### M6: Kill compress, fix index defaults

Remove the compress verb from cli.py and verbs/. Change index default from
dry-run to write (remove PD6 gate). Add --dry-run flag that shows: function
count, estimated API calls, estimated cost, API key status. Add file-level
summaries as a byproduct of index (synthesize from per-function descriptions).

Files: pidgin/cli.py, pidgin/verbs/index.py, delete pidgin/verbs/compress.py
Test: pidgin index . shows cost estimate and writes by default.

### M7: Query normalization

Before embedding a human query, pass it through gpt-4.1-nano: "Rewrite this
as an imperative function description: {query}". --raw flag skips normalization.
One nano call per query, ~100ms, negligible cost.

Files: pidgin/verbs/query.py
Test: "how do I create a chat completion" matches the same function as
"Create a chat completion with messages and model."

### M8: Summarize verb

Single-file MLD to stdout. Input: file path or stdin. No embedding, no nest.
Markdown output by default, --xml flag for machine consumption.
Uses converge.xml pipeline but outputs to stdout instead of nest.
For files that fit in context: single MLD pass.
For files exceeding context: chunk, summarize each chunk, summarize the summaries.

Files: pidgin/verbs/summarize.py, pidgin/cli.py
Test: pidgin summarize README.md produces coherent summary.

### M9: Egg verb

`pidgin egg .` walks an indexed repo and generates/updates CLAUDE.md discovery
files in every directory that contains indexed functions. Each CLAUDE.md lists:
file names, function names, MLD descriptions, exported symbols. Reads from the
nest, writes to filesystem. Requires repo to be indexed (error if nest empty).

Files: pidgin/verbs/egg.py, pidgin/cli.py
Test: index a repo, run egg, verify CLAUDE.md files in each directory.

### M10: Depends verb

`pidgin depends ./file.py` reads import graph from nest metadata, shows what
this file imports and what imports it. Human-readable default, --json for
LLM consumption. Requires import tracking (M12) to be implemented.

Note: depends on M12 (import tracking). If M12 is in Phase 3, either move
M10 to Phase 3 or implement a minimal import extraction in M10 directly.

Files: pidgin/verbs/depends.py, pidgin/cli.py
Test: pidgin depends on a file with known imports returns correct graph.

## Phase 3 — Pipeline Intelligence (M11-M14)

Make the pipeline smarter: track convergence rate per draft, stop early when
converged, extract structural metadata, and make index idempotent.

### M11: Draft stratification

After MLD runs, compute separate centroids for all draft_1 candidates, all
draft_2 candidates, and all draft_3 candidates across calls. Report per-draft
cluster tightness. Store the per-draft centroid data in the FunctionMldResult.
This is analysis, not a behavior change — the pipeline still uses all candidates.

Files: pidgin/pipeline/batch.py (run_embedding_mld_pipeline_for_functions)
Test: run on 10 functions, verify per-draft centroid data is populated.

### M12: Import and signature tracking

During AST walk, extract: import statements, function signatures with type hints,
parameter names and types, return type, decorators. Store as imports.json in
.pidgin/. Build a dependency graph: file A imports X from file B.

Files: pidgin/utils/parser.py, pidgin/store/nest.py
Test: parse a file with known imports, verify imports.json is correct.

### M13: Idempotency

Store source_hash (sha256 of function body) per function in the nest. On re-index:
hash unchanged → skip (zero API calls). Hash changed → re-MLD. Function deleted
→ prune from nest. Report: "N unchanged, M updated, K deleted."

Files: pidgin/verbs/index.py, pidgin/store/nest.py
Test: index, modify one function, re-index, verify only modified function re-runs.

### M14: Adaptive stopping

Replace fixed n_calls with convergence-based stopping. Compute centroid after
each batch of calls. If cosine_similarity(centroid_n, centroid_{n-1}) > 0.99,
stop. Cap at 5 batches (50 candidates max). Report convergence rate.

Files: pidgin/pipeline/batch.py (run_embedding_mld_pipeline_for_functions)
Test: simple function converges in 1-2 batches, complex function uses more.

## Phase 4 — Bidirectional Re-Gate (M15-M17)

Re-run the Phase 4 experiment from v0.2 with the scaling fixes applied.

### M15: Budget increase and envelope fix

Raise bidirectional token budget to 1000. Switch expand.xml from JSON-schema
response_format to tool-use structured output (eliminates truncation at the
JSON closing brace).

Files: pidgin/prompts/expand.xml, probes/m14-bidirectional/harness_fast.py
Test: generate a 40-line function body without truncation.

### M16: Re-run bidirectional probes

Re-run the 5 probes from v0.2 Phase 4 with the budget and envelope fixes.
Also fix P1 description (too generic) and P2 probe definition (wrong reference).
Gate criteria unchanged: 4/5 stable+correct → UNLOCK, 3/5 → AMBIGUOUS, <3 → DEFER.

Files: probes/m14-bidirectional/
Test: 5 probes, 6 runs each, 30 records total.

### M17: Gate decision

Evaluate probe results against gate criteria. Issue gate.xml verdict.
If UNLOCK → Phase 5 proceeds. If DEFER → sprint closes at Phase 4.

Files: gate.xml
Test: gate.xml is well-formed with verdict and per-probe results.

## Phase 5 — Cleanup and Integration (M18-M19)

Conditional on Phase 4 UNLOCK. If DEFER, sprint closes at Phase 4.

### M18: Fine-tuning data collection

Wire index to collect training data as a byproduct. Every converged MLD winner
becomes an SFT example. Every gate call becomes a gate-SFT example. Write to
.pidgin/training-data.jsonl. Report example count after each index run.

Files: pidgin/verbs/index.py, pidgin/store/nest.py
Test: index 50 functions, verify training-data.jsonl has entries.

### M19: Cleanup debt

- Remove 4 `from tools.` import hits in pidgin/pipeline/
- Make tools/ a thin re-export shim or delete
- Fix compress_write commit message prefix
- Bump Anthropic gate max_tokens to 512
- Fix type annotation inconsistencies
- Add .pidgin/ to repo .gitignore template
- Remove duplicate example from converge.xml

Files: various
Test: grep -r "from tools\." pidgin/ returns zero hits.

## Decisions

### Decision 1: Phase 4 gate (bidirectional)
Same criteria as v0.2: 4/5 stable+correct → UNLOCK, 3/5 → commander judgment,
<3 → DEFER. Commander decides externally.

### Decision 2: Draft stratification outcome
After M11 data is collected: if draft_3 clusters tighter than draft_1, change
the pipeline to weight draft_3 more heavily (or use only draft_3 for centroid).
If no difference, consider switching to single-draft-per-call with more calls.

### Decision 3: Model routing
After v0.3 ships, test gpt-5.4-mini for gate calls (replacing haiku) and
gpt-5.1 at effort=none for generation (replacing 4.1-nano). Not in this sprint
scope — these are post-sprint experiments.

### Decision 4: Summarize chunking strategy
M8 implements single-file summarize. Multi-file and directory summarize are
deferred to v0.4. Chunking strategy (for files exceeding context) is implemented
but marked experimental.

## Provider Strategy

Unchanged from v0.2: OpenAI for volume (generation, embedding, batch), Anthropic
for judgment (gate validation, architectural reasoning). Fine-tuning data
collection (M18) is the first step toward replacing prompts with fine-tuned
models, which would consolidate everything on OpenAI.

## Conventions

Same as v0.2: XML for structured documents, mission grammar per Marionette,
log format per v0.1/v0.2 convention, amendments numbered sequentially.
