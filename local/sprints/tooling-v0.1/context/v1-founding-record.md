# Tooling V1 — Founding Record

Executed: 2026-04-24 to 2026-04-25
Missions completed: 10 of 18 (plus 5 patch missions)
Total API spend: ~$1.15
Status: closed with honor — purpose served, superseded by design

---

## What V1 Built

The Python tool layer and the MLD proof of concept. Everything
below survives into V2 unchanged.

### Permanent Infrastructure

| File | Lines | DOES |
|------|-------|------|
| tools/utils/api.py | 390 | Provider routing (Anthropic, OpenAI), parallel dispatch, cost tracking |
| tools/utils/sections.py | 247 | Section get/put with hash idempotency, auto-versioning, language-aware wrapping |
| tools/utils/parser.py | 467 | Language detection, AST extraction for Python/Rust/TS/Go/C |
| tools/utils/sidecar.py | 102 | Embedding JSON read/write |
| tools/strip_comments.py | 282 | Comment removal with slot markers, 5 languages |
| tools/extract_functions.py | 149 | Function extraction via AST, dispatches to all 5 parsers |
| tools/chunk_md.py | 219 | Markdown chunking on heading boundaries, table detection |
| tools/chunk_py.py | 193 | Python chunking on function/class boundaries via AST |
| tools/chunk_rs.py | 134 | Rust chunking on pub item boundaries |

### Validated Prompts

| File | Tokens | Status |
|------|--------|--------|
| tools/prompts/generate.md | ~4,549 | Validated seed — 18/18 convergences with GPT-4.1 nano |
| tools/prompts/validate.md | ~1,100 | Clean |
| .claude/skills/technologic/prompts/recomment.md | ~2,400 | Clean |

### Empirical Data

| File | What it contains |
|------|-----------------|
| context/mld-validation-2026-04-24.md | 7 runs, dim sweep, model comparison |
| context/mld-validation-extended-2026-04-24.md | 47 runs, full parameter sweep |
| local/scratch/mld-validation-report-2026-04-24.md | Raw candidate descriptions, cosine matrices, failure analysis |

---

## What V1 Proved

### MLD works.
The antipode convergence geometry discriminates correctly. Degenerate
clouds get rejected. Diverse clouds converge. The minimum budget
tracks real semantic boundaries. 54 runs across 3 models, 3
dimensions, 3 n-values, 3 function complexities.

### GPT-4.1 nano is the generation tier.
18/18 convergences. $0.005/run. Non-reasoning model — direct text
output at low token budgets. Haiku failed 8/9 on identical configs
due to degenerate repetition at tight budgets.

### 256 embedding dimensions are sufficient.
No quality improvement at 512 or 768. Dimension 64 collapses
discrimination. 128 produces false convergence via truncation
artifacts. 256 is the minimum correct dimension.

### The review-patch cycle catches real bugs.
Missions 3, 4, 5, 8, 9, 10 all had review findings that led to
patch missions. 14 criticals caught across the sprint. Every one
would have been a silent bug downstream. The coordinator/executor
split and adversarial review are load-bearing.

### Agent task dispatch works.
Local mode via Claude Code task creation — each mission in its own
context window with the correct agent system prompt. The agents are
portable from Marionette. The coordinator never executes missions
in its own context.

---

## What V1 Disproved

### Hard token budgets are wrong.
Capping max_tokens at 8/16/24/32 forces mid-thought truncation.
Trailing commas, mid-word artifacts, incomplete clauses are all
consequences of the API cutting the model off. Soft budgets with
"be concise" instructions and generous ceilings let the model find
its natural stopping point.

### The mechanical grammar filter doesn't work.
0/140 candidates rejected across 54 runs. GPT-4.1 nano follows
the prompt grammar perfectly — the filter has nothing to catch.
When it should catch something (trailing commas from truncation),
it misses. The filter is checking syntax when the real question
is semantic: "Is this description complete and accurate?" That's
an LLM judgment, not a regex.

### Free-form JSON responses are fragile.
The generate.md prompt trains the model to output structured JSON
as free text. At tight budgets, truncation produces partial JSON
that falls through parsing. Structured outputs (tool calls or
response_format) eliminate this class of error entirely.

### Anthropic caching is not needed for this workload.
OpenAI automatic prefix caching has no minimum threshold, no
explicit headers, no break-even calculation. For the volume
generation tier (GPT-4.1 nano), it just works. Anthropic caching
requires 4,096 token minimum and explicit cache_control headers.
The break-even at 7 calls means: if you're calling Anthropic 7+
times with the same prompt, the task should have been routed to
a cheaper tier. Explicit caching adds complexity for a workload
that doesn't benefit from it.

### Embedding sidecars are unnecessary.
Vector search belongs in a database (ChromaDB, Atlas), not in
JSON files alongside source. The sidecar pattern was designed for
a world where the index lives with the code. The architecture
has moved to external stores.

### Technologic should be built last, not first.
V1 built /technologic first as the validation skill. But
/technologic is the most complex skill — it modifies source files,
writes CLAUDE.md indexes, runs enforcement. Building it first meant
every pipeline flaw was discovered through a 912-line orchestration
script. Building /digest or /embed first (simpler, read-only)
would have validated the pipeline with less surface area. V2
builds /technologic last, from proven components.

---

## What V2 Inherits

### From V1 sprint:
- The entire Python tool layer (9 files, ~1,800 lines)
- The validated prompts (3 files, to be revised for soft budget)
- The empirical data (54 runs, raw candidate analysis)
- Agent task dispatch infrastructure

### From design discussions (backlog documents):
- Soft budgets with LLM validation gates
- Three-draft iterative generation pattern
- Selective Origami principle injection per mission
- External documentation store (SQLite + ChromaDB)
- Cascading trust model for data access
- Mechanical audit trail (pre/post-write commits)
- Section tags as universal boundary between human/machine content
- CRISPR-style line:character operations over blind XML overwrites
- ORIGAMI.md / ARCHITECTURE.md / CLAUDE.md split
- Provider strategy: OpenAI for volume, Anthropic for trust
- Voyage AI for embeddings

### V2 design principles (from V1 failures):
- Structured outputs via tool calls, never free-form JSON
- No explicit caching — OpenAI auto-caches, Anthropic not needed
- No embedding sidecars — vectors go to a database
- No mechanical grammar filter — LLM gates for semantic validation
- Build /technologic last from proven components
- Every file operation is a CRISPR operation with hash verification
