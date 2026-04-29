# Current State

## Repository

Location: ~/Desktop/pidgin (GitHub: wiregrassio/pidgin)
Layout: src/pidgin/ (standard Python src layout)
Venv: .venv/ (Python 3.14)
Install: pip install -e . (editable)

## Directory Structure

```
pidgin/                         ← repo root
├── src/pidgin/                 ← package code
│   ├── cli.py                  ← CLI entry, 8 verbs
│   ├── pipeline/
│   │   ├── batch.py            ← batch + sync dispatch, incremental writes
│   │   ├── candidates.py       ← adaptive expansion
│   │   ├── geometry.py         ← spherical_variance, convergence_verdict (BROKEN)
│   │   └── mld.py              ← single-function MLD path
│   ├── prompts/
│   │   ├── converge.xml        ← generation prompt (still 3-draft schema)
│   │   ├── gate.xml            ← validation prompt
│   │   ├── expand.xml          ← bidirectional expansion
│   │   └── templates.py        ← XML assembly, principle injection
│   ├── store/
│   │   ├── nest.py             ← ChromaDB per-repo nest
│   │   ├── audit.py            ← JSONL audit trail
│   │   ├── discovery.py        ← nested nest discovery
│   │   └── sft.py              ← SFT training data collection
│   ├── utils/
│   │   ├── api.py              ← OpenAI client, embedding
│   │   ├── git.py              ← commit brackets, repo detection
│   │   └── parser.py           ← AST extraction (Python + class methods)
│   ├── verbs/
│   │   ├── index.py, query.py  ← core verbs
│   │   ├── summarize.py        ← single-file MLD to stdout
│   │   ├── egg.py              ← generate CLAUDE.md from nest
│   │   ├── depends.py          ← import graph
│   │   ├── init.py             ← nest bootstrapping
│   │   ├── new.py, update.py   ← write verbs (LLM-facing)
│   └── write/                  ← write model core
├── scripts/
│   ├── calibrate.py            ← calibration experiment runner
│   ├── analyze_calibration.py  ← calibration analysis
│   └── load_calibration.py     ← load winners into nest
├── .claude/
│   └── mission-grammar.md      ← sprint mission schema
├── .pidgin/
│   └── nest/                   ← self-indexed nest (126 functions from calibration)
├── local/
│   ├── sprints/                ← v0 through v0.4.1 sprint history
│   └── templates/              ← sprint package template
├── calibration-data.json       ← 12,600 calls metadata
├── calibration-vectors.npz     ← 37,638 embedding vectors
├── analysis-results.txt        ← calibration analysis output
├── pyproject.toml
├── CLAUDE.md
└── .env
```

## What Works

- `pidgin init` — bootstraps .pidgin/nest/
- `pidgin query "..."` — searches nest, returns ranked results (tested: 0.833 on "compute spherical variance")
- `pidgin index . --sync` — walks files, generates candidates, embeds, upserts. Incremental writes, graceful shutdown, progress tracking all functional.
- `pidgin egg` — generates CLAUDE.md from nest data
- `pidgin depends` — shows import graph
- `pidgin summarize` — single-file MLD to stdout
- `scripts/load_calibration.py` — loads pre-computed calibration data into nest (126 functions, zero API calls)

## What's Broken

- **Convergence test:** convergence_verdict() in geometry.py uses sv1 > sv2 > sv3 (draft decay). Calibration proved draft 3 is WORSE. Pipeline reports ~0-7% convergence on real code. Descriptions are correct; the flag is wrong.
- **Three-draft generation:** converge.xml still asks for 3 drafts. Pipeline still generates 3 per call. Should be 1.
- **Temperature:** Not locked at 0.3. Each call uses whatever the default is.
- **No rate limit handling:** 429 errors silently drop candidates.

## Nest State

126 functions indexed from calibration data via load_calibration.py.
- 102 CONVERGED (sv < 0.10)
- 19 AMBIGUOUS (sv 0.10-0.15)
- 5 DIVERGENT (sv > 0.15): classify_batch_results, MLDResult, AssembledPrompt, generate, EditOp

These descriptions were generated at mixed temperatures and all 3 drafts,
then post-hoc filtered to t=0.3 draft_1 for convergence scoring and
centroid selection. The descriptions are good. The nest is queryable.
After the convergence fix, `pidgin index . --sync` should produce similar
results from scratch.

## Provider Configuration

- Generation: gpt-4.1-nano (OpenAI)
- Embeddings: text-embedding-3-small, 256-dim (OpenAI)
- Gate validation: gpt-4.1-mini (OpenAI, switched from haiku in v0.4 M5)
- No Anthropic API dependency

## The 5 Divergent Functions

These need human review — the divergence is likely a code quality signal:

1. **MLDResult** (sv=0.28) — dataclass with many fields and complex metadata
2. **generate** (sv=0.19) — multi-purpose: handles schema, structured output, async, cost tracking
3. **classify_batch_results** (sv=0.19) — unclear why divergent, may need clearer naming
4. **EditOp** (sv=0.18) — multi-step: replace lines, handle payload, manage offsets
5. **AssembledPrompt** (sv=0.15) — borderline, dataclass with preamble/payload split

The operator's stance: "cattle, not pets, understandable, modular." If these
functions can be simplified, simplify them. If they're genuinely complex,
accept the divergence and document it.
