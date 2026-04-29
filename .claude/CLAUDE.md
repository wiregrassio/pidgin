# Pidgin

LLM-native toolkit for indexing codebases via MLD (Minimum Lossless
Description). Source code in `src/pidgin/`. Install with `pip install -e .`.

## Quick Reference

```bash
pidgin init              # bootstrap .pidgin/nest/
pidgin index . --sync    # index all public functions, write to nest
pidgin query "..."       # semantic search across nests
pidgin summarize file.py # single-file MLD to stdout
pidgin egg .             # generate CLAUDE.md files from nest
pidgin depends file.py   # show import graph
```

## Structure

```
src/pidgin/
├── cli.py              # CLI entry, argparse
├── pipeline/           # MLD pipeline: batch dispatch, geometry, convergence
├── prompts/            # converge.xml, gate.xml, expand.xml, templates.py
├── store/              # ChromaDB nest, audit trail, discovery, SFT collection
├── utils/              # OpenAI client, AST parser, git helpers
├── verbs/              # CLI verb implementations
└── write/              # atomic file writes with audit + commit brackets
```

## Conventions

- Python 3.11+. Type hints on public functions.
- One file, one responsibility. If a module does two things, split it.
- Public functions have imperative docstrings (what it does, not what it is).
- Tests: not yet formalized. Verification is via `pidgin index . --sync` + `pidgin query`.

## Provider Configuration

- Generation: gpt-4.1-nano (OpenAI)
- Embeddings: text-embedding-3-small, 256-dim (OpenAI)
- Gate validation: gpt-4.1-mini (OpenAI)
- OPENAI_API_KEY must be in environment or .env at repo root

## Sprint Infrastructure

- Mission grammar: `.claude/mission-grammar.md`
- Agents: `.claude/agents/` (execute, reason, scout)
- Skills: `.claude/skills/new-sprint/`, `.claude/skills/run-sprint/`
- Sprint history: `local/sprints/`
- Sprint template: `local/templates/sprint-package/`
