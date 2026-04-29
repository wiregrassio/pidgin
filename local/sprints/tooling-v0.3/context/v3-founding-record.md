# v0.3 Founding Record

What v0.2 proved, what broke, and what v0.3 must do.

## What v0.2 Delivered

Pidgin is a working Python package with a CLI, installed editable via pyproject.toml. 16 missions executed, 13 shipped (Phases 1-3), 3 probe-only (Phase 4). All GREEN. $0.10 total spend. One amendment issued mid-sprint (gate model → claude-haiku-4-5).

### The Package (pidgin/)

```
pidgin/
├── cli.py, __main__.py          # CLI: 6 verbs via argparse
├── pipeline/
│   ├── batch.py                 # OpenAI + Anthropic batch dispatch
│   ├── candidates.py            # Adaptive expansion (n=10→15→30)
│   ├── geometry.py              # cosine_similarity, centroid, antipode_test
│   └── mld.py                   # Full MLD pipeline
├── prompts/
│   ├── converge.xml             # Generation prompt (33 pos, 17 neg examples)
│   ├── gate.xml                 # Validation prompt (11 criteria)
│   ├── expand.xml               # Bidirectional expansion prompt
│   └── templates.py             # XML assembly, principle injection, cache split
├── store/
│   ├── audit.py                 # JSONL audit trail
│   ├── discovery.py             # Nested nest discovery + registry
│   └── nest.py                  # Per-repo ChromaDB (.pidgin/nest/)
├── utils/
│   ├── api.py                   # OpenAI client, embedding constants
│   ├── git.py                   # Commit brackets, repo detection
│   └── parser.py                # AST extraction (Python only)
├── verbs/
│   ├── index.py, query.py       # Core verbs
│   ├── compress.py              # TO BE KILLED in v0.3
│   ├── new.py, update.py        # Write verbs (LLM-facing)
│   └── init.py                  # Nest bootstrapping (fixed post-sprint)
└── write/
    ├── new.py, compress.py      # Write model core
    └── update.py                # Transaction context manager
```

### What Was Validated

- **Flock/architect split:** gpt-4.1-nano generates, claude-haiku-4-5 gates, Opus reasons. Empirically confirmed when nano hallucinated on gate validation (M4).
- **Provider routing:** OpenAI for volume (auto-cache, batch discount), Anthropic for judgment only.
- **XML prompt migration:** converge.xml achieved 15/15 convergence on all 4 M3 probes — zero regression vs v0.1.
- **Batch infrastructure:** 300+300 calls in 325s at $0.03 (M15 mega-batches).
- **Adaptive candidates:** expand→converge→accept pipeline with convergence ratio thresholds.
- **Per-repo nests:** ChromaDB at .pidgin/nest/ with nested discovery and registry.
- **Write model:** Modes 2/3/4 with atomic writes, sha256 hashing, git commits, JSONL audit.

### Phase 4 Gate: DEFER

Bidirectional MLD (description→code) deferred. The geometry works — tight cluster convergence (Δ1) across all stable probes. But the JSON response envelope truncates at budgets of 50/200 tokens. P4 (one-liner) passed 5/5 byte-equal. P3 at b=200 matched reference verbatim 3/3. P5 (40-line function) never produced valid Python. The bottleneck is budget + envelope, not embedding space. Five pre-conditions before re-gating (see log.md commander confirmation).

## What Broke (Stress Testing)

First real-world run: indexing the OpenAI Python SDK (~6500 public functions in full repo, ~1700 in resources/, 79 in resources/chat/).

### Bug 1: Batch payload too large (CRITICAL)

Each JSONL line includes the full converge.xml preamble (~30KB). For N functions × 5 calls:
- 79 functions = 395 lines ≈ 12MB → 413 from Cloudflare
- 1698 functions = 8490 lines → 413 from Cloudflare
- The sprint's 20-call batches worked because 20 × 30KB ≈ 600KB

**Fix:** Chunk batches to 50-100 requests per upload. Submit chunks separately, poll concurrently, merge results. Also consider: the preamble is identical across all lines — deduplication or file-reference could cut payload 50-100x.

### Bug 2: Silent error swallowing (CRITICAL)

When the batch fails (413 or OpenAI rejection), run_batch_generation returns all results with error fields set. The index verb sees 0 converged and reports "Converged: 0/79" as if it's a normal result. No error message, no indication that the pipeline didn't actually run. The verb should detect when ALL results have errors and print the first error message.

### Bug 3: Nest location follows args.path, not git root (HIGH)

`pidgin index ./src/openai/resources/chat --write-db` creates the nest at `./src/openai/resources/chat/.pidgin/nest/`, not at the repo root. The nest should always be at the git root (walk up to .git, same as PD1's _find_project_root). One repo = one nest.

### Bug 4: dotenv relative path (MEDIUM)

batch.py hardcodes `load_dotenv('/Users/elliotwillis/Desktop/fe-toolkit/local/.env')`. This works for fe-toolkit but not for Pidgin as a general tool. Should resolve relative to the pidgin package install location, or use OPENAI_API_KEY from environment directly (standard pattern — user exports it in their shell profile or .env).

### Bug 5: init didn't bootstrap (FIXED)

init only discovered existing nests, didn't create one. Fixed post-sprint by adding ensure_nest() and CLAUDE.md write to verbs/init.py. This fix is live in the editable install.

### Bug 6: Parser Python-only (KNOWN LIMITATION)

utils/parser.py uses Python's ast module. Rust, TypeScript, Go need tree-sitter. Not a bug — a known scope boundary. v0.3 should add at least Rust (for Watchtower).

## Design Decisions Made Post-Sprint

### Verb Redesign

**Kill compress.** No user story. File-level summaries should be a byproduct of index, not a separate verb.

**Add summarize.** Single-file MLD to stdout. No embedding, no nest. Pipe-friendly. Input: file, stdin, URL. Output: structured summary (markdown default, --xml flag). Use case: ingesting external docs, SDK guides, web content. n8n/Slack pipeline integration.

**Add egg.** `pidgin egg ./path` walks an indexed repo and generates/updates CLAUDE.md discovery files in every directory. Reads from the nest, writes to the filesystem. The Daft Punk Path made mechanical.

**Add depends.** `pidgin depends ./my_func.py` reads imports.json from the nest, shows what this file imports and what imports it. Single-file, human-readable.

**Four human verbs:** init, index, query, summarize. Everything else is LLM-facing infrastructure.

### Flag Conventions

- Human-friendly defaults, --raw and --xml for LLM callers
- index defaults to write (not dry-run). --dry-run with cost estimate replaces PD6.
- --budget, --candidates, --temperature are power-user flags
- --sync forces sync path (workaround for batch bugs)

### Query Normalization

Human queries ("how do I parse a CSV?") are geometrically distant from stored descriptions ("Parse CSV file and return rows as dictionaries.") in embedding space. Fix: preprocess human queries through gpt-4.1-nano with "Rewrite as imperative function description: {query}". --raw flag skips this for LLM callers whose queries are already imperative.

### Draft Stratification

Within a single API call, draft_1/draft_2/draft_3 are sequential refinements (output_schema: 120/80/60 max tokens). The model has previous drafts in context when writing later ones. Proposed analysis: compute per-draft centroids across all calls. If draft_3 clusters tighter than draft_1, within-call refinement works and we should always use draft_3. If not, drafts are just shorter, not better, and we should generate one draft per call.

### Adaptive Stopping

Don't hardcode 3 drafts or N calls. Compute centroid after each batch of calls. If centroid delta < threshold, stop early. Cap at 5 batches (50 candidates). The API cost is negligible — wall time is the constraint, and batch dispatch handles that.

### Import and Signature Tracking

During AST walk, extract: import statements (build dependency graph), function signatures with type hints, parameter names, return types. Store as structured metadata in the nest alongside MLD descriptions. Enables `pidgin depends` and cross-module contract analysis.

### Fine-Tuning Data Collection

Every MLD run produces labeled training data for free: converged winner = "good", non-converged candidates = "bad". Indexing 4 SDKs at n=10 candidates per function = 20,000-30,000 training examples. OpenAI SFT minimum is a few hundred. Gate calls similarly produce (description, valid/invalid, reason) triples. Endgame: fine-tuned nano replaces converge.xml prompt entirely.

### Git Boundary Detection

If index hits a .git directory inside its walk, stop at that boundary. Don't descend into child repos. The current git ls-files scope may already handle this — verify.

### Idempotency

index should check source hash before MLD-calling a function. If body unchanged, skip. If changed, re-index. If deleted, prune from nest. Safe to run repeatedly — in CI, in git hooks, after every commit.

### Model Routing Changes Under Consideration

- Replace haiku gate calls with gpt-5.4-mini or gpt-4.1 (consolidate to single provider)
- Test gpt-5.1 at reasoning_effort=none as flock replacement (is 4.1-nano still optimal?)
- Model selector at local/scratch/model_selector.xml has OpenAI entries; Anthropic entries TBD

### Skills Rewrite

- digest and embed are dead → both are `pidgin index`
- finalize → pidgin index + pidgin egg + technologic
- cleanup-prompt is shipped as a skill (.claude/skills/cleanup-prompt/)
- new-sprint and run-sprint stay but should call pidgin verbs where applicable
- dissect needs rethinking — cross-module contracts may become pidgin depends + a thin skill

### External SDK Indexing

Priority targets: openai-python, anthropic-python, both agent SDKs. Every function becomes queryable. CLAUDE.md can reference nests for accurate, version-pinned documentation. Stress-tests Pidgin at scale.

## Cleanup Debt from v0.2

- 4 `from tools.` import hits in pidgin/pipeline/ (KE2)
- tools/ directory has diverged copies — make thin re-export shim, then delete
- compress_write commit message prefix should be pidgin/compress_write:
- Anthropic gate max_tokens 256→512 (M9 finding)
- Type annotation inconsistencies (tuple-as-list-default, config: ExpansionConfig = None)
- Duplicate example in converge.xml (ex5 and ex_rust_simple are same function)
- converge.xml anti-examples may anchor model on failure patterns (test removal)
- pyproject.toml and pidgin.egg-info need to be in .gitignore

## What v0.3 Must Do

### Mechanical (fast, low risk)
- Batch chunking (100 per batch, 5 concurrent)
- Surface batch errors (don't swallow)
- Nest location at git root, not args.path
- dotenv resolution (use env vars directly, not hardcoded path)
- Idempotency via source hash
- Skip non-source files (markdown, json, yaml, .pidgin/)
- Git boundary detection
- Budget increase to 1000+ for bidirectional
- Clean out tools/ (thin shim → deprecate → delete)

### New Verbs
- summarize (single-file MLD to stdout)
- egg (generate CLAUDE.md from nest)
- depends (show import graph from nest metadata)
- Kill compress

### Pipeline Improvements
- Draft stratification (per-draft centroid tracking)
- Adaptive stopping (centroid delta threshold)
- Import/signature extraction during AST walk
- Query normalization for human input
- Tree-sitter for Rust support (Watchtower)

### Experimental
- Fine-tuning data collection as index byproduct
- Prompt audit via cleanup-prompt skill (converge.xml, gate.xml, expand.xml)
- Bidirectional MLD re-gate at 1000+ budget with tool-use envelope
- Per-draft centroid analysis on existing M3 data
- gpt-5.4-mini vs gpt-4.1-nano for gate calls

### External
- Index openai-python, anthropic-python, agent SDKs
- Skills rewrite against new verb surface
