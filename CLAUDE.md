# pidgin/

Write-model package for RF-Edge sprint tooling. V0.2 extraction from tools/.
Implements artifact write Modes 2, 3, 4; MLD pipeline; prompts; store; utils.

## Public API (from pidgin import ...)

| Symbol | Kind | DOES |
|--------|------|------|
| `artifact_write` | fn | Batch write files (Mode 3) with git bracket and audit. |
| `update` | fn | Return a Transaction context manager for atomic file edits (Mode 2). |
| `assemble_xml_prompt` | fn | Assemble an XML prompt template with principle injection and cache-boundary split. |
| `run_embedding_mld_pipeline_for_functions` | fn | Run the full generation + embedding MLD pipeline for a list of function dicts. |
| `nest` | module | ChromaDB sections store + function vector store (merged sections_chroma + vectors). |
| `audit` | module | JSONL audit helpers: file_hash, audit_log_path, audit_log. |

## CLI (python -m pidgin)

Wired in M11. Run `python -m pidgin --help` for full usage.

```
pidgin index <path> [--write-db] [--sync] [--batch]
pidgin update <path> [--write-source] [--edits-file FILE]   # stub M12
pidgin new <path> [--write-source]                          # stub M12
pidgin query <text>                                         # stub M12
pidgin init [path]                                          # stub M13
```

PD2: All flags are per-subcommand (after the verb).
PD3: `--sync` + `--batch` → exit 2, "Cannot specify both --sync and --batch."
PD6: `index` without `--write-db` → dry-run, zero API calls.

See `pidgin/verbs/CLAUDE.md` for verb details.

## Subpackages

| Package | DOES |
|---------|------|
| `pidgin.write` | Modes 2 (update), 3 (artifact_write), 4 (lineage-tracked write). File writes with git bracket and JSONL audit. |
| `pidgin.prompts` | XML prompt assembler (assemble_xml_prompt), converge.xml, gate.xml, PRINCIPLES registry. |
| `pidgin.pipeline` | Sync and batch MLD dispatch (mld, run_embedding_mld_pipeline_for_functions, batch, geometry, candidates). |
| `pidgin.store` | ChromaDB backend — nest.py (sections + function vectors) and audit.py (JSONL helpers). |
| `pidgin.utils` | api.py (embedding constants + OpenAI client + embed_for_store), git.py (git helpers), parser.py (AST + regex extractors + extract_public_functions). |
| `pidgin.verbs` | CLI verb implementations. index (wired); update, new, query, init (stubs). |

## Version

```python
import pidgin; pidgin.__version__  # "0.2.0"
```

## How to Navigate

1. Find the symbol in the table above.
2. Read the relevant subpackage's CLAUDE.md:
   - `pidgin/write/CLAUDE.md` — Modes 2/3/4 signatures and audit format
   - `pidgin/prompts/CLAUDE.md` — XML prompt structure and usage
   - `pidgin/pipeline/CLAUDE.md` — dispatch routing, batch surface, MLD phases
   - `pidgin/store/CLAUDE.md` — ChromaDB collections and metadata schema
   - `pidgin/verbs/CLAUDE.md` — CLI verb implementations and flag conventions
3. Use awk to find the function's start line, then read the range.

Never read an entire file. Use the index then awk then ranged read.
