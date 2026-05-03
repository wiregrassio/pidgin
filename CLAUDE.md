# pidgin

Code-access library for LLM agents. Owns the OpenAI routing layer plus nine
verbs: index, search, graph, egg, get, put, assert, score, rank. This is a
library — orchestration and sprint infrastructure live in wiregrass.

## Package layout

```
src/pidgin/
├── __init__.py       # re-exports all public names
├── __main__.py       # python -m pidgin entry
├── cli.py            # argparse dispatcher (nine subparsers)
├── api.py            # OpenAI routing: generate(), embed_text(), cost tracking
├── nest.py           # .pidgin/nest/ storage layout (LanceDB + import graph)
├── extract.py        # AST extraction of functions, classes, methods
├── index.py          # index a file or directory into LanceDB
├── search.py         # semantic search over the LanceDB symbol store
├── graph.py          # import-graph queries: blast-radius, depends, cycles
├── egg.py            # generate CLAUDE.md from indexed symbol records
├── get.py            # extract a named symbol from source via AST
├── put.py            # rewrite a symbol in source, fidelity/prudence gated
├── edit.py           # EditContext: context-manager for multi-symbol edits
├── flush.py          # flush staged edits from an EditContext to disk
├── resolve.py        # input resolution: files, dirs, git refs, stdin, literals
├── skill_runner.py   # boilerplate for eval/reasoning skill scripts
├── assert_.py        # binary verification verb
├── _assert.py        # internal assert helper, used by assert_.py
├── score.py          # cardinal scoring verb (1-10)
├── rank.py           # ordinal ranking verb
└── prompts/          # XML prompt templates
```

## Install

```bash
cd /path/to/pidgin
python3 -m venv .venv
.venv/bin/pip install -e .
```

## CLI

```bash
pidgin index <path>        # index source into LanceDB
pidgin search <query>      # semantic search over symbols
pidgin graph <file>        # blast-radius / depends / cycles
pidgin egg <dir>           # write CLAUDE.md from index
pidgin get --name <name> --file <file.py>   # extract a symbol
pidgin put ...             # rewrite a symbol
pidgin assert ...          # binary verification
pidgin score ...           # cardinal scoring
pidgin rank ...            # ordinal ranking
```

## Version

```python
import pidgin; pidgin.__version__  # "0.6.0a1"
```

## Provider config

- Generation: gpt-4.1-mini / gpt-4.1-nano (via api.py)
- Embeddings: text-embedding-3-small, 256-dim
- OPENAI_API_KEY must be set in the environment
