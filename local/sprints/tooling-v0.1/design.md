# Tooling V2 — Design

## Goal

Build the production MLD pipeline and the external documentation architecture that V1 proved was possible. V1 validated the geometry, identified the generation tier, and built the Python tool layer. V2 replaces every component V1 disproved — hard budgets, the mechanical grammar filter, free-form JSON, embedding sidecars — and delivers the four skills in dependency order: /embed, /digest, /dissect, /technologic. The result is a system that can index any repository into a precision-compressed semantic store, query it by vector, and maintain it through mechanical audit.

## Current State

The Python tool layer exists and is validated: api.py (provider routing, parallel dispatch, cost tracking), sections.py (section get/put with hash idempotency), parser.py (AST extraction for Python/Rust/TS/Go/C), strip_comments.py, extract_functions.py, chunk_md.py, chunk_py.py, chunk_rs.py. Nine files, ~1,800 lines, zero known bugs after 14 critical fixes across the V1 sprint.

The MLD algorithm works. 54 runs across 3 models, 3 embedding dimensions, 3 n-values, 3 function complexities. GPT-4.1 nano converged 18/18 at $0.005/run. The antipode convergence geometry discriminates correctly: degenerate clouds get rejected, diverse clouds converge, the minimum budget tracks real semantic boundaries.

Three validated prompts exist: generate.md (~4,549 tokens, 18/18 convergences), validate.md (~1,100 tokens), recomment.md (~2,400 tokens).

What does not exist: the external documentation store, vector search, the skill pipeline (/embed → /digest → /dissect → /technologic), the Origami reprocessing, the three-draft iterative generation pattern, LLM validation gates, structured output enforcement, or the principle registry for selective injection.

## Target State

After this sprint, the repo contains:

**Pipeline layer** (tools/mld/). The MLD pipeline rebuilt for soft budgets, structured outputs, three-draft iterative generation, and LLM validation gates. generate.md revised. Grammar filter demoted to pre-check (empty strings, non-UTF-8). Semantic validation via Nano gate call. Final selection via Opus when candidate set is ambiguous.

**Storage layer** (tools/store/). SQLite documentation store with the sections schema. section_put and section_get gain a --backend flag; db is the default. ChromaDB integration for vector search — two indices (function bodies, descriptions). Voyage AI embeddings via updated embed.py with --provider flag.

**Skill pipeline** (tools/skills/ or .claude/skills/). Four skills built in dependency order:
1. /embed — vector generation and store population. Read-only against source. Simplest skill, validates the pipeline.
2. /digest — recursive summarization. Functions → modules → repo. Batch-friendly. Validates the summarization chain.
3. /dissect — behavioral spec generation. Contracts, architecture docs. Validates structured output and section primitives against the store.
4. /technologic — the judge. Index currency, description quality, surface area, staleness enforcement. Built last from proven components. The most complex skill, touching every layer.

**Origami reprocessing artifacts.** CLAUDE.md becomes a routing table. ORIGAMI.md absorbs docs/manifesto.md with every principle MLD-compressed. ARCHITECTURE.md captures the three-repo split, coordinator/executor, service map, networking. All three at repo root. Non-convergent principles are flagged for review — the tool judges the philosophy.

**Principle registry.** SQLite table or JSON file mapping principle IDs to MLD-compressed descriptions. Sprint planners annotate missions with principle lists. The runner assembles tailored preambles mechanically. Agents receive only the Origami they need.

An agent reading this sprint's output can index any repository, query it semantically, validate its documentation, and do all of this without modifying a single line of the target repo's source code.

## Decisions

### Decision 1: Soft budgets replace hard token caps

Hard-capping max_tokens at the budget value (8/16/24/32) forces mid-thought truncation. V1 produced trailing commas, mid-word artifacts ("trunc"), incomplete clauses — all consequences of the API cutting the model off mid-generation. The grammar filter could not catch these because they are syntactically ambiguous (a trailing comma is valid punctuation).

V2 sets max_tokens to a generous ceiling (64 tokens) and instructs the model to be as concise as possible. The model finds its natural stopping point. The natural output length becomes the real complexity metric — not the convergence budget, which V1 proved measures cloud tightness, not semantic complexity (main() converged at a lower budget than embed() despite being more complex).

The budget parameter in MLD shifts from "how many tokens the model is allowed" to "how concise we ask the model to be." The instruction says "describe in roughly N tokens." The ceiling says "but stop by 64 regardless." The difference eliminates truncation artifacts entirely.

Cost impact: at GPT-4.1 nano's $0.40/MTok output, doubling max_tokens from 32 to 64 adds ~$0.001 per run. Negligible.

### Decision 2: LLM validation gates replace the mechanical grammar filter

The grammar filter rejected 0/140 candidates across 54 V1 runs. It adds code and maintenance for zero empirical value. When truncation artifacts appeared (the actual quality problem), the filter missed them because it checks syntax when the real question is semantic: "Is this description complete and accurate?"

V2 demotes the grammar filter to a mechanical pre-check for obvious failures: empty strings, non-UTF-8, non-imperative starts. The real quality gate is an LLM call. The centroid-nearest candidate plus 3–4 alternatives (selected by varying axes: median length, shortest above threshold, highest internal consistency) go to a Nano gate call: "Does this description fully capture the function's behavior? Respond with {valid: bool, reason: string}." Structured output. Five cents per million tokens.

When the gate is uncertain or the candidate set is ambiguous (multiple candidates near centroid at varying lengths), the full set goes to Opus in one call. Opus sees the function body, all candidates, their lengths, their centroid distances, and makes the final selection. One Opus call per function, applied only where judgment adds value. Cheap models generate, expensive models judge.

### Decision 3: Structured outputs everywhere, no free-form JSON

V1's generate.md trained the model to output structured JSON as free text. At tight budgets, truncation produced partial JSON that fell through parsing. This class of error is eliminated by using structured outputs: tool calls or response_format with a JSON schema.

Every LLM call in V2 that expects structured data uses one of these two mechanisms. The three-draft generation call returns `{draft_1: str, draft_2: str, draft_3: str}` via response_format. The gate call returns `{valid: bool, reason: str}`. The Opus selection call returns `{selected_index: int, rationale: str}`. No prompt engineering for JSON formatting. No parsing recovery. The API enforces the schema.

### Decision 4: Three-draft iterative generation

A single Nano call produces three outputs at increasing refinement: a broad draft, a tighter rewrite, and a final form. 10 calls × 3 drafts = 30 candidates for the cost of 10 calls, one cache hit per call.

MLD computation gets natural stratification. First drafts anchor the centroid (broadest semantic spread). Second drafts tighten it (self-edited, shorter). Third drafts sharpen it (final form, most refined). Convergence can be computed within tiers and across tiers. The best shortest, best medium, and best long get handed to the validation gate.

This replaces the V1 pattern of N identical calls at a single budget tier. The model does its own editorial pass before returning, which produces higher-quality candidates at every length.

### Decision 5: Provider split — OpenAI for volume, Anthropic for trust

Validated during V1. The economics and capability split:

OpenAI GPT-4.1 nano handles all generation. Non-reasoning model, $0.10/MTok input, $0.40/MTok output, automatic prefix caching with no minimum threshold, no explicit headers, no break-even calculation. 18/18 convergences in V1. This is the volume tier.

Anthropic Haiku handles validation when call count justifies caching (≥7 calls against the same prompt for break-even at the 4,096 token cache floor). Anthropic Sonnet/Opus handles final MLD selection when the candidate set is ambiguous, full-corpus analysis (/digest), and any trust-sensitive operation. Marionette agents stay on Anthropic — tool calls against live infrastructure require higher trust.

No explicit Anthropic cache_control headers. If a workload needs 7+ identical Anthropic calls, the task belongs at a cheaper tier. OpenAI auto-caches. That's the strategy.

### Decision 6: Voyage AI for stored embeddings, OpenAI for ephemeral MLD geometry

MongoDB acquired Voyage AI (February 2025). voyage-3.5-lite at $0.02/MTok matches OpenAI text-embedding-3-small pricing with better retrieval quality on benchmarks. Atlas automatic embedding (preview) generates vectors on ingest using Voyage models — this eliminates the embed.py call for Base Camp documents entirely.

embed.py gains a --provider flag (openai, voyage), defaulting to voyage. VOYAGE_API_KEY goes into local/.env. Existing Base Camp documents re-embed on next update.

MLD convergence geometry stays on OpenAI text-embedding-3-small at 256 dimensions. These vectors are ephemeral — computed during the convergence test, never stored. No migration needed. The convergence algorithm is validated against this model and dimension; changing it requires re-validation.

### Decision 7: External documentation store — SQLite + ChromaDB

Source files carry zero documentation. All descriptions, index entries, contract annotations live in a local SQLite database (gitignored, per-operator). The sections schema:

```sql
CREATE TABLE sections (
    file TEXT,
    tag TEXT,
    content TEXT,
    version INTEGER,
    updated TEXT,
    by TEXT,
    model TEXT,
    source_hash TEXT,
    git_ref TEXT,
    PRIMARY KEY (file, tag)
);
```

section_put writes to this table. section_get reads from it. Same API surface. The XML tags in source files become optional human-readable annotations, not source of truth. section_put gains a --backend flag (file | db), defaulting to db.

ChromaDB provides vector search. Two collections: function bodies and descriptions. Two query modes: "find the function that handles X" (query against body embeddings) and "find functions similar to this one" (query against description embeddings). ChromaDB runs as a container service inside Marionette, vector files bind-mounted from the project directory. Same packaging pattern as every other RF-Edge service.

### Decision 8: CRISPR file operations with hash verification

Every file write is a CRISPR operation: line:character precision, source hash verification before and after. No blind XML section overwrites. section_put already implements hash idempotency (V1 infrastructure). V2 extends this to every write path: the pre-write hash must match the expected state, the post-write hash is recorded, and any mismatch halts the operation.

The mechanical audit trail wraps every write in a two-commit bracket:
1. `git commit` pre-write: "pre-write: {file} by {agent}"
2. Perform the write
3. `git commit` post-write: "post-write: {file} by {agent}"

Rollback is `git revert` on the post-write commit. Every action writes a structured record to TimescaleDB (already running in RF-Edge). The audit trail is queryable, not a log file.

### Decision 9: Skills built in dependency order, /technologic last

V1 built /technologic first because it was the validation target. This was wrong — /technologic is the most complex skill (912 lines in V1), touching every pipeline component. Every pipeline flaw was discovered through it. Building simpler skills first would have validated each layer with less surface area.

V2 build order:
1. **/embed** — vector generation and store population. Read-only against source. Exercises: embed.py, ChromaDB writes, Voyage AI integration, store schema. Simplest skill. If /embed doesn't work, nothing downstream works.
2. **/digest** — recursive summarization (functions → modules → repo). Exercises: MLD pipeline (soft budgets, three-draft, convergence), Nano generation, batch dispatch. The core MLD pipeline is validated here.
3. **/dissect** — behavioral spec generation (contracts, architecture docs). Exercises: structured outputs, section primitives against SQLite store, Opus judgment calls. The store read/write path is validated here.
4. **/technologic** — enforcement and indexing. Exercises: everything. Built from proven components. By the time /technologic is scoped, every layer it depends on has been validated independently.

### Decision 10: Selective Origami principle injection

Every agent gets a tailored preamble, not the full manifesto. The sprint planner annotates each mission with relevant principle IDs: "principles: [1, 3, 7]". The runner looks up those IDs in the principle registry and concatenates the MLD-compressed descriptions into a preamble.

The principle registry is a SQLite table (or JSON file — format is a sprint-time decision):

```
principle_id | title | mld_description | mld_budget | convergence_score
```

Benefits: smaller preambles (cheaper cached prompts), relevant principles only (less noise, better adherence), and architectural incapacity through selective knowledge — a Wildebeest Mode executor doesn't know about documentation standards, a documentation agent doesn't know about Wildebeest Mode.

Depends on Origami reprocessing: MLD must process the manifesto's 19 principles before the registry can be populated.

### Decision 11: Origami reprocessing — the ouroboros

After the MLD pipeline is validated through /embed and /digest, it processes Origami itself. The deliverables:

CLAUDE.md becomes a routing table: "Read ORIGAMI.md for philosophy, ARCHITECTURE.md for decisions." Entrypoint only.

ORIGAMI.md absorbs docs/manifesto.md. Every principle is MLD-compressed to its minimum lossless description. Non-convergent principles are flagged — if a principle resists compression, it is ambiguous or overloaded. The tool judges the philosophy that created it. Each pass produces a sharper Origami.

ARCHITECTURE.md captures the three-repo split (FE-Toolkit / RF-Edge / Marionette), coordinator/executor relationship, service map, config surfaces, networking. Technical decisions that change when the system changes.

All three files live at repo root. The constitution. Everything else is legislation.

After reprocessing, docs/manifesto.md is deleted (absorbed into ORIGAMI.md). All CLAUDE.md cross-references are updated.

### Decision 12: Degenerate cloud handling

V1 identified two degenerate-cloud failure modes: full degeneracy (all candidates identical, avg_cosine_sim = 1.0) and near-degeneracy (4/5 candidates identical, algorithm cannot converge because the antipode test fails on near-point clouds the same way it fails on single points).

V2 adds two pre-checks before the antipode test:
1. If avg_cosine_sim > 0.999, return converged=False immediately. Avoids floating-point edge cases on fully degenerate clouds.
2. If >50% of candidates are textually identical (string equality before embedding), deduplicate and rerun generation once. This helps models with low variance without changing the algorithm.

The three-draft pattern partially mitigates this — three drafts per call produce natural variation that a single-draft call at tight budgets does not.

### Decision 13: The converged=False path must be empirically validated

V1 never triggered a genuine converged=False result on a semantically equivocal function. Every False was a degenerate cloud. V2 must exercise this path with a purpose-built test case: a function with genuinely equivocal semantics where N≥10 candidates at every budget tier produce varied phrasings that never converge. Suggested probe: `def merge(a, b, prefer_b=True): return {**a, **b} if prefer_b else {**b, **a}` at budget_range=(8,12). This validates that non-convergence is a real signal, not just a degenerate-cloud artifact.
