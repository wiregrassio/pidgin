# Tooling V1 — Design

## Goal

Build the MLD pipeline that powers all FE-Toolkit skills. A shared
primitive for consensus-driven description generation using geometric
convergence in embedding space. Two flagship skills that validate the
method. A Python tool layer of composable file-processing primitives.

After this sprint: /technologic actively produces minimum lossless
descriptions, re-documents source files, and enforces compliance
across any codebase. /digest passively produces architectural
understanding documents from source code without leaking
implementation. Every skill that follows inherits the MLD pipeline.

## Current State

Skills are written as monolithic SKILL.md files that describe
workflows for Claude Code to execute directly. No API calls, no
parallelism, no model tiering. A compliance check on a 50-file
repo runs sequentially in one context window at whatever model
the operator's session is using. A documentation pass over an
external SDK happens the same way.

`tools/` contains `embed.py` — a single embedding utility. No
parsing, no chunking, no comment manipulation. Everything upstream
of embedding is manual.

## Target State

A three-layer architecture:

```
Skills (pipeline scripts — coordinate, don't compute)
  ├── /technologic    — active: MLD descriptions, re-comment, index, enforce
  ├── /digest         — passive: understand, document, no source in output
  ├── /embed          — vectorize: chunk, embed, write embedding.json
  ├── /consolidate    — synthesize: merge prose from multiple sources into one
  ├── /new-sprint     — updated: MLD-based code generation (future)
  └── /run-sprint     — updated: MLD for mission execution (future)
      │
Tools (Python primitives — parse, transform, no LLM)
  ├── strip_comments.py
  ├── extract_functions.py
  ├── chunk_md.py
  ├── chunk_py.py
  ├── chunk_rs.py
  └── embed.py (exists)
      │
Utils (shared infrastructure)
  ├── mld.py          — MLD pipeline: generate, filter, embed, converge, validate
  ├── api.py          — provider routing, caching, parallel dispatch, cost tracking
  ├── parser.py       — language detection, AST helpers
  └── sidecar.py      — embedding.json read/write
```

---

## Decisions

### Decision 1: The MLD Pipeline

The core primitive is Minimum Lossless Description — a
consensus-driven compression pipeline that finds the minimum token
budget at which an LLM reaches stable semantic consensus about an
input. The full method is documented in `docs/mld.md`.

Two files implement it:

**`utils/mld.py`** — the pipeline itself:

```python
async def mld(
    input_text: str,       # the function body, prose passage, etc.
    prompt: str,           # cached instruction (grammar, format rules)
    budget_range: tuple = (8, 32),  # token budget search space
    budget_step: int = 8,  # budget tier increments
    n: int = 10,           # candidates per budget tier
    temperature: float = 0.8,
    model: str = "gpt-5-nano",
    embed_dim: int = 128,  # embedding dimension for convergence geometry
    schema: dict = None,   # structured output schema
) -> MLDResult:
    """
    Find the minimum lossless description of an input.

    Pipeline:
    1. Generate N candidates at each budget tier (parallel)
    2. Grammar filter — reject non-compliant candidates, rerun
    3. Embed all passing candidates (parallel)
    4. Antipode convergence test per tier
    5. Binary search toward minimum convergent budget
    6. Validate: centroid-nearest + alternatives → reasoning model
    """
```

Returns an `MLDResult`:

```python
@dataclass
class MLDResult:
    description: str          # the MLD itself
    token_count: int          # minimum convergent budget
    complexity_score: int     # same as token_count — free metric
    confidence: float         # convergence speed (0-1)
    converged: bool           # False = non-convergence (structural signal)
    candidates_generated: int # total across all tiers
    candidates_filtered: int  # rejected by grammar
    validation_rationale: str # reasoning model's explanation
    cost: CostSummary         # tokens, dollars, cache hit rate
```

**`utils/api.py`** — the transport layer:

```python
async def generate(
    prompt: str,
    content: str,
    model: str = "gpt-5-nano",
    temperature: float = 0.8,
    max_tokens: int = 32,
    schema: dict = None,
    n: int = 1,
) -> list[str]:
    """
    Send a cached prompt + variable content to a model.
    Handles provider routing, cache headers, retries.
    """

async def generate_batch(
    prompt: str,
    contents: list[str],
    **kwargs,
) -> list[list[str]]:
    """
    Parallel dispatch of generate() across multiple inputs.
    Bounded concurrency. Cost tracking.
    """
```

The separation is important. `api.py` handles transport — caching,
routing, retries, cost tracking. `mld.py` handles the pipeline —
generation, filtering, embedding, convergence geometry, validation.
Skills call `mld.mld()` for description generation and `api.generate()`
for non-MLD calls (Opus analysis in /digest, Sonnet review).

### Decision 2: The Tier Map

```
GPT-5 Nano ($0.05/MTok, ~$0.005 cached)
  — MLD generation tier. Highest volume. Per-function candidates.
  — Run 10+ per budget tier with temperature 0.8.
  — Cached prompt is identical across all functions AND all budget
    tiers — only the function body and max_tokens change.
  — Grammar filter rejects non-compliant candidates.

text-embedding-3-small (via embed.py)
  — MLD convergence tier. Embed all passing candidates.
  — Dimension tuned for convergence: 64-128 (not 1536).
  — Same model as RAG, different --dim.
  — Empirically validate dimension during Phase 2.

Haiku ($1/MTok, $0.10 cached)
  — MLD validation tier. Receives centroid-nearest + alternatives.
  — Judges; does not create. One call per function.
  — Single run, low temperature.

Sonnet ($3/MTok, $0.30 cached)
  — Review tier. Validates batches of MLD results.
  — "These 12 functions did not converge. Examine."
  — Single run, low temperature.

Opus ($5/MTok, $0.50 cached)
  — Full corpus. One call with the complete structured input.
  — Only used by /digest.
  — "Here is every function name and its MLD. Here is the
     dependency graph. Produce the architecture."
  — Single run, temperature 0.
```

The MLD pipeline uses two embedding dimensions:
- **Convergence (64-128):** discrimination between short candidate
  descriptions of the same function. Tuned empirically in Phase 2.
- **RAG (1536):** corpus-scale search. Used by /embed, unchanged.

### Decision 3: /technologic Is Active

/technologic replaces the old /index (/finalize). It is the one
skill that modifies source files. The workflow:

1. **Extract** — `extract_functions.py` parses every tracked source
   file into a list of `{name, signature, body, line_range}`.

2. **Strip** — `strip_comments.py` removes all existing comments
   from each function body, leaving markers for reinsertion.

3. **MLD** — For each function, run the MLD pipeline. The cached
   prompt contains the Origami grammar: single imperative verb,
   concrete nouns, no hedging, no interpretive slack. Budget range
   8-32 tokens. All budget tiers run in parallel. All functions
   run in parallel. Convergence produces the MLD and a complexity
   score per function.

4. **Re-comment** — Insert the winning MLDs as inline contracts.
   The format: module header (MODULE / DOES / EMITS / READS /
   DEPENDS) plus per-function docstrings.

5. **Format** — Run through `black` (Python), `rustfmt` (Rust),
   or equivalent.

6. **Index** — Build CLAUDE.md tiered discovery indexes from the
   MLDs. The descriptions ARE the index entries.

7. **Complexity report** — Surface the compression complexity
   scores. Functions converging at 8 tokens are clean primitives.
   Functions requiring 32+ are doing too much. Non-convergent
   functions are structural liabilities.

8. **Report** — Structured output: files modified, functions
   documented, complexity distribution, non-convergent functions
   flagged, cost summary.

### Decision 4: /digest Is Passive

/digest never modifies source. It produces understanding documents
in `docs/` with no source code in the output. An engineer reading
the output can work with the SDK, plan a refactor, or do a clean
room rewrite without reading the source.

The workflow:

1. **Extract** — Same tools as /technologic. Parse every function
   across the entire codebase.

2. **MLD** — Same pipeline as /technologic. Per-function MLDs with
   convergence. Produces the same corpus of structured function
   metadata with complexity scores.

3. **Collect** — Assemble the full corpus: every function name,
   its MLD, its complexity score, module membership, dependency
   graph. No source code — MLDs and signatures only.

4. **Analyze** — Hand the full corpus to Opus in one call. The
   prompt includes: function inventory with MLDs, complexity
   scores, dependency graph, module boundaries, type signatures
   (signatures only). Opus produces:
   - `docs/modules/<module>.md` — purpose, surface, consumers, deps
   - `docs/contracts.md` — cross-module agreements
   - `docs/architecture.md` — system shape, data flow, design patterns
   - `docs/summary.md` — the "read this first" document

5. **Verify** — Confirm no source code leaked into the output.
   Scan all produced docs for code blocks longer than a signature.
   Flag any that appear.

**`--anonymize` flag:** For clean room rewrites. When set, Opus
is instructed to rename functions and types to generic descriptive
names, merge conceptually similar functions, and reorganize modules
by concern rather than preserving the original structure. The output
describes WHAT the system does, not HOW this specific implementation
does it. Function names become verbs describing behavior. Module
names become nouns describing responsibility. Implementation
heritage is erased.

Output:

```
docs/
├── modules/           # one file per module
│   ├── <module-a>.md
│   └── <module-b>.md
├── contracts.md       # cross-module type/protocol/error agreements
├── architecture.md    # dependency graph, data flow, system shape
└── summary.md         # read this first
```

### Decision 5: The Python Tool Layer

Composable primitives. No LLM calls. Each tool does one thing.

**strip_comments.py** — Remove all comments from source code. Leave
markers (`# [COMMENT_SLOT:<id>]`) where comments were. Output: the
stripped source and a manifest of removed comments with their slot
IDs. Language-aware: Python docstrings, Rust `///` and `//`, JS
`/** */` and `//`.

**extract_functions.py** — Parse source into structured function
records: `{name, signature, body, line_range, module, visibility}`.
Language-aware: Python `def`/`class`, Rust `pub fn`/`pub struct`/
`pub enum`/`pub trait`, JS/TS `export function`/`export class`.
Uses AST parsing where available (Python `ast` module), regex
fallback for others.

**chunk_md.py** — Chunk markdown on document structure. Hierarchical:
H3 chunks carry H2 and H1 in `header_chain`. Code blocks and tables
get their own chunks. Short files embedded whole.

**chunk_py.py** — Chunk Python source on function/class boundaries.
Each chunk: the function signature, docstring, and body.

**chunk_rs.py** — Chunk Rust source on `pub` item boundaries. Each
chunk: the item signature, doc comments, and body.

**utils/mld.py** — The MLD pipeline. Generation, grammar filtering,
embedding, antipode convergence test, budget search, validation.

**utils/api.py** — Provider routing (Anthropic, OpenAI), prompt
caching (cache_control headers), parallel dispatch (asyncio bounded
concurrency), structured output parsing, cost tracking, retry with
backoff.

**utils/parser.py** — Language detection by extension. Shared AST
helpers. Import graph extraction.

**utils/sidecar.py** — Read/write `embedding.json` files.
Per-directory format: one JSON file containing chunks from every
source file in that directory.

### Decision 6: The Grammar Filter

The grammar filter sits between MLD generation and embedding. It is
the Origami enforcement layer within the pipeline — mechanical,
deterministic, no LLM involved.

A candidate passes if:
- Starts with an imperative verb
- Contains no hedging words (may, might, could, possibly, generally,
  typically, arguably, perhaps)
- Contains no filler (basically, essentially, effectively, simply,
  just, really)
- Contains no passive voice constructions
- Falls within the budget's token count
- Conforms to the structured output schema (if specified)

Reject rate is a calibration signal:
- High reject rate (>50%) — grammar too tight OR function too complex
  for the budget tier OR prompt needs tuning
- Low reject rate (<10%) — grammar may be too loose, candidates may
  be trivially similar

The filter is a Python function in `utils/mld.py`, not a separate
tool. It's internal to the pipeline.

### Decision 7: Shared Prompts

Cached prompts are load-bearing infrastructure. They are the
instruction set that GPT-5 Nano executes against. Each prompt is a
markdown file in the skill's `prompts/` directory.

The MLD generation prompt must be ≥4,096 tokens to qualify for
caching on the Anthropic API (Haiku validation tier). OpenAI's
caching threshold may differ. The prompt is padded with useful
context — Origami principles, grammar rules, formatting examples,
the controlled vocabulary — not filler.

Prompts shared between /technologic and /digest:

**generate.md** — The MLD generation prompt. Cached across all
functions AND all budget tiers. Contains: grammar rules (imperative
verb, no hedging, no filler), structured output schema, Origami
principles relevant to description quality, examples of good and
bad descriptions at various token budgets. The variable suffix is
the function signature + body.

**validate.md** — The reasoning model prompt. Receives
centroid-nearest candidate + alternatives. "Evaluate each candidate.
Select the best. Explain why. Respond with structured JSON."

Prompts specific to /technologic:

**recomment.md** — "Here is a function with its comments stripped.
Here is the MLD for this function. Write the inline contract.
Respond with: `{slots: [{id: string, comment: string}]}`."

Prompts specific to /digest:

**analyze.md** — "Here is the complete function inventory for a
codebase. Each function has its MLD and complexity score. [inventory].
Here is the dependency graph. [graph]. Produce: modules (one per
logical grouping), contracts (cross-module agreements), architecture
(system shape), summary (read-this-first). No source code in output.
MLDs and signatures only."

**analyze_anonymized.md** — Same as analyze.md but with additional
instruction: "Rename all functions and types to generic descriptive
names. Merge conceptually similar functions. Reorganize modules by
concern. The output describes WHAT the system does, not HOW this
implementation does it."

### Decision 8: /new-sprint MLD (future)

/new-sprint gains MLD-based code generation when dispatching to
Marionette is not available (local mode). For each function the
sprint plan specifies:

1. Cache the implementation spec (mission context + specification).
2. Run the MLD pipeline with the spec as the "description target"
   and the function body as the output.
3. Convergence means multiple independent generation attempts
   arrived at structurally similar implementations.
4. Non-convergence means the spec is ambiguous — surface it.

This is not a V1 change. It's noted here for architectural
consistency — the MLD pipeline supports this use case by design.

### Decision 9: /embed Remains Simple

/embed wraps the chunk_* tools and embed.py. No MLD needed.
Chunking is deterministic. Embedding is deterministic. The skill
detects file types in the target directory, routes to the right
chunker, calls embed.py per chunk, and writes per-directory
embedding.json files. Embedding dimension for RAG is 1536 (default).

```
embedding.json format:
{
  "directory": "docs/modules/",
  "model": "text-embedding-3-small",
  "dimensions": 1536,
  "generated": "2026-04-23T...",
  "chunks": [
    {
      "source_file": "watchtower.md",
      "header_chain": ["Watchtower", "Public Surface"],
      "line_range": [15, 42],
      "text": "...",
      "embedding": [0.0123, ...]
    }
  ]
}
```

Gitignore pattern: `embedding.json`.

---

## Build Order

### Phase 1: Foundation

Build the MLD pipeline and the Python tool layer. No skills yet —
just the infrastructure they all depend on.

1. `tools/utils/api.py` — provider routing, caching, parallel
   dispatch, cost tracking. Supports Anthropic (Haiku, Sonnet, Opus)
   and OpenAI (GPT-5 Nano, text-embedding-3-small).
2. `tools/utils/mld.py` — MLD pipeline: generate, grammar filter,
   embed, antipode convergence, budget search, validate.
3. `tools/utils/parser.py` — language detection, AST helpers.
4. `tools/utils/sidecar.py` — embedding.json read/write.
5. `tools/strip_comments.py` — comment removal with slot markers.
6. `tools/extract_functions.py` — function extraction with AST.
7. `tools/chunk_md.py` — markdown chunking.
8. `tools/chunk_py.py` — Python source chunking.
9. `tools/chunk_rs.py` — Rust source chunking.
10. Update `tools/requirements.txt` — add anthropic, openai (update),
    numpy (for convergence geometry), asyncio deps.
11. Validate: run extract_functions against tools/embed.py itself.
    Run strip_comments. Run chunk_py. Confirm the mechanical pipeline
    works end-to-end without any LLM calls.

### Phase 2: MLD Validation

Validate the MLD pipeline against known functions before building
skills on top of it. This is the empirical foundation.

12. Run MLD against `tools/embed.py::embed()` — a known-simple
    function. Expected: converges at 8-12 tokens.
13. Run MLD against `tools/embed.py::main()` — a known-complex
    function (argument parsing, input resolution, output formatting).
    Expected: converges at 20-32 tokens.
14. Test embedding dimensions: run convergence at 64, 128, 256.
    Identify the minimum dimension where the antipode check
    discriminates between simple and complex functions.
15. Test grammar filter: measure reject rates. Tune if needed.
16. Test non-convergence: construct or find a function that should
    NOT converge (deeply coupled, unclear purpose). Verify the
    pipeline issues a receipt rather than forcing a description.
17. Cost check: log total tokens, cache hit rates, and dollar cost
    for the validation run. Verify caching is working.

### Phase 3: /technologic

Build the first MLD-powered skill. Validates the full pipeline
against this repo.

18. Write cached prompts: `generate.md`, `validate.md`, `recomment.md`.
19. Write `technologic.py` pipeline script.
20. Update `SKILL.md` to reflect MLD architecture.
21. Validate: run /technologic --verify-only against fe-toolkit.
    Verify it extracts functions from embed.py, runs MLD, produces
    complexity scores, builds CLAUDE.md indexes.
22. Cost check: log total cost for the full run.

### Phase 4: /digest

Build the second MLD-powered skill. Validates the Opus-at-the-top
pattern with MLD-produced descriptions.

23. Write cached prompts: `analyze.md`, `analyze_anonymized.md`.
24. Write `digest.py` pipeline script.
25. Write `SKILL.md` to reflect MLD architecture.
26. Validate: run /digest against rf-edge/watchtower. Verify it
    produces docs/modules/, docs/contracts.md, docs/architecture.md,
    docs/summary.md with no source code in output.
27. Validate --anonymize: run against the same target. Verify
    function names are generic, modules reorganized by concern.

### Phase 5: /embed

28. Write `embed_skill.py` pipeline script (the skill, not the tool).
29. Write `SKILL.md`.
30. Validate: run /embed against fe-toolkit/docs/. Verify it
    produces embedding.json with chunks from manifesto.md and
    other markdown files.

### Phase 6: /consolidate

31. Write `consolidate.py` pipeline script.
32. Write `SKILL.md`.
33. Validate: run against the genesis sprint package. Then validate
    against multiple scratch files to confirm general-purpose prose
    synthesis works beyond the sprint special case.

### Phase 7: Cleanup

34. Remove old /index (finalize) skill directory — replaced by
    /technologic.
35. Remove old /dissect skill directory — replaced by /digest.
36. Update all cross-references: root CLAUDE.md, .claude/CLAUDE.md,
    skills index.
37. Delete `local/scratch/session-handoff-2026-04-22.md` — all
    actionable items captured in this sprint or completed.

---

## What Is Not In Scope

- /new-sprint MLD-based code generation (noted in design, built later)
- /run-sprint MLD updates (same)
- chunk_html.py (no immediate use case — defer to V2)
- `--atlas` upload flag for embedding.json (Base Camp integration,
  separate sprint)
- Avoma API token and ingestion pipeline (external dependency)
- Vector search index creation in Atlas (5 minutes of UI work,
  not sprint material)
