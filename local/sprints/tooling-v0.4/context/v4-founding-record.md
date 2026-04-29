# v0.4 Founding Record

## What v0.3 Delivered

Sprint v0.3: 19 missions, all GREEN, 6 patches. Phase 4 gate UNLOCK at 4/5 on
bidirectional MLD probes (budget increase 1000→2000, tool-use envelope, probe
definition fixes). Phase 5 shipped: SFT training data collection and full cleanup.

Key deliverables:
- Batch chunking (100 requests per JSONL, 2 concurrent, pipelined submission)
- Error surfacing with first_error propagation through FunctionMldResult
- Nest at git root (find_project_root)
- dotenv resolved via environment / load_dotenv(), not hardcoded path
- File filtering with --exclude globs and git boundary detection
- Killed compress verb; index defaults to write; --dry-run with cost estimate
- Query normalization (imperative rewrite for human queries via nano)
- Summarize verb (single-file MLD to stdout, markdown/xml)
- Egg verb (generate CLAUDE.md discovery files from nest data)
- Depends verb (import graph from AST, minimal inline extraction)
- Draft stratification (per-draft centroid tracking and tightness metrics)
- Import and signature tracking during AST walk (stored in imports.json + nest metadata)
- Idempotency via source hash (skip unchanged, prune deleted)
- Adaptive stopping (centroid delta convergence, earliest stop at batch 2)
- Bidirectional MLD validated at b=2000 with tool-use envelope
- SFT training data collection as index byproduct (.pidgin/training-data.jsonl)
- pidgin/ fully independent of tools/ at runtime
- Installed as editable package via pyproject.toml

## What Broke (Post-Sprint Real-World Use)

### The critical failure: long-running index jobs are not resumable

Operator attempted to index the full OpenAI Python SDK (4930 functions after
excluding types/). Two runs failed:

**Run 1:** Ran in VS Code terminal. After ~40 minutes, 3-5 batches completed
(~300 functions processed). Operator hit Ctrl+C to move the job to a background
Mac terminal. All results lost — the pipeline holds everything in memory and
writes the nest only at the very end. Those 300 functions' worth of API calls
were wasted.

**Run 2:** Restarted in Mac terminal. Idempotency reported `unchanged=0 new=4930`
because the nest was never written from Run 1. Operator cancelled again after
learning the results would take ~27 hours via batch API and wanting to wait for
reliability improvements.

The OpenAI batches from Run 1 completed on their servers (results available for
24 hours) but Pidgin has no mechanism to retrieve abandoned batch results.

**Root cause:** The pipeline architecture is all-or-nothing. Generation, embedding,
convergence testing, and nest writing happen in a single pipeline call that must
complete fully for any results to persist. A 27-hour job that fails at hour 26
loses everything.

### Additional operational issues

- **No progress indication.** Terminal is silent for hours during batch polling.
  No way to know if the job is running, stuck, or making progress.
- **Messy Ctrl+C output.** KeyboardInterrupt produces a long traceback instead
  of a clean shutdown message.
- **Batch API throughput is unpredictable.** Observed 3-5 batches completing in
  40 minutes (~10 min per batch of 100). At that rate, 247 batches = 27 hours.
  No SLA from OpenAI — can be faster or slower depending on load.
- **2M enqueued token limit per org.** With 7.5K token preamble per request,
  only ~266 requests can be enqueued simultaneously. The pipelined 2-concurrent
  strategy stays under this, but it throttles throughput.

### Successful real-world runs (sync path)

Two sync runs completed successfully before the batch scaling attempts:
- `resources/chat/`: 79 functions, 72 converged (91%), queryable
- `resources/responses/`: 150 functions, 94 converged (63%), queryable

Total: 166 converged examples across two SDK surfaces. These nests still exist
and are queryable. They also represent the first batch of SFT training data.

## Operator's Priorities for v0.4

The operator was explicit: **do not run big index jobs until incremental writes,
graceful shutdown, and progress tracking are solid.** These are the blocking items.

The operator also wants:
- Abandoned batch recovery (check OpenAI for completed batches from prior runs)
- Fine-tuning when training data reaches ~500 examples
- Status bar / progress bar during all long-running operations
- converge.xml prompt audit using the cleanup-prompt skill
- Model routing experiments (gpt-5.4-mini for gate, gpt-5.1-none for flock)
- Tree-sitter for Rust (Watchtower repo)
- Skills rewrite against the new Pidgin verb surface

The operator's design philosophy: Pidgin is an LLM tool that can be used as a CLI.
Humans run init, index, query, summarize. Everything else is LLM infrastructure.
Default behavior is human-friendly; --raw and --xml flags for LLM callers.

## v0.3 Carry-Forward Debt

- M13: Identity key uses absolute file path — nest not portable across machines
- M13: function_dict_hash diverges from function_source_hash (whitespace triggers re-MLD)
- candidates.py:86 + templates.py:96: hardcoded /Users/elliotwillis paths
- tools/ cannot be deleted (5 skill files depend on it)
- mld.py:15: stale DEPENDS comment
- P1 probe description still admits surface forms (3/6 match)

## Architecture Notes

### Provider Strategy (validated through v0.2 and v0.3)

- OpenAI for all volume work: generation (gpt-4.1-nano), embeddings (text-embedding-3-small), batch
- Anthropic for judgment only: gate validation (claude-haiku-4-5), architecture (Opus via Claude Code)
- Model selector at local/scratch/model_selector.xml has full OpenAI entries; Anthropic entries being added separately

### The Flock/Architect Split

The flock (nano) generates candidates — pattern completion at scale. The architect
(haiku for gates, Opus for reasoning) evaluates whether those candidates are correct.
Validated empirically: nano hallucinated on gate validation (M4 of v0.2), confirming
that judgment tasks must route to reasoning-capable models.

### Batch Economics

OpenAI Batch API: 50% discount, separate rate limits, auto-caching of preamble.
Observed: 300 gen + 300 embed = $0.03 at 325s wall time (M15 of v0.2).
At scale (4930 functions): estimated $1.70-2.00 total, 27 hours wall time.
Fine-tuning would eliminate the 7.5K token preamble, cutting batch payload size
~50x and potentially reducing cost to $0.10-0.20 for the same run.

### SFT Data Pipeline

Every index run now collects training data in .pidgin/training-data.jsonl:
- Converged winners → "positive" SFT examples
- Non-converged candidates → "negative" examples  
- Gate calls → (description, valid/invalid, reason) triples

Current training data: ~166 examples from OpenAI SDK sync runs. Need ~500 for
a first fine-tune. Indexing more SDK subdirectories (embeddings, files, batches,
completions) plus the operator's own repos (fe-toolkit, rf-edge, watchtower)
would reach that threshold.
