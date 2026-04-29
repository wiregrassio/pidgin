# Verb Redesign

## Current Verbs (v0.2)

| Verb | Status | Audience |
|------|--------|----------|
| index | Working (batch bug) | Human + LLM |
| query | Working | Human + LLM |
| init | Working (fixed post-sprint) | Human |
| compress | TO KILL | — |
| new | Stub (write model wired) | LLM |
| update | Stub (write model wired) | LLM |

## v0.3 Target Verbs

| Verb | Audience | Description |
|------|----------|-------------|
| init | Human | Bootstrap .pidgin/nest/, write CLAUDE.md, discover child nests |
| index | Human + LLM | Walk source, MLD each function, write file summaries, build import graph, write to nest |
| query | Human + LLM | Semantic search across registered nests. Human queries auto-normalized to imperative form |
| summarize | Human + LLM | Single-file MLD to stdout. Markdown default, --xml flag. No nest, no embedding. Pipe-friendly |
| egg | Human (pre-push) | Generate/update CLAUDE.md files in every directory from indexed nest data |
| depends | Human + LLM | Show import/export graph for a single file from nest metadata |
| new | LLM | Artifact write (Mode 3) |
| update | LLM | Transaction edit (Mode 2) |

## Kill List

**compress** — solution looking for a problem. File-level summaries are a byproduct of index. No user story for standalone file description.

## Flag Conventions

- Default is human-intended. --raw / --xml for LLM callers.
- index defaults to WRITE (not dry-run). --dry-run with cost estimate.
- --sync forces sync path (batch workaround).
- --budget, --candidates, --temperature are power-user flags.
- --exclude glob for skipping directories (generated code, vendored deps).

## Query Normalization

Stored descriptions are imperative: "Parse CSV file and return rows as dictionaries."
Human queries are interrogative: "How do I parse a CSV?"

These are geometrically distant in embedding space. Fix: before embedding, pass human queries through gpt-4.1-nano with "Rewrite as an imperative function description: {query}". One nano call, ~100ms, negligible cost.

--raw skips normalization (for LLM callers whose queries are already imperative).

## Nest Location Fix

The nest always lives at the git root, regardless of which subdirectory is indexed. Walk up to .git (same as PD1's _find_project_root). One repo = one nest. Index of a subdirectory writes to the repo-level nest.
