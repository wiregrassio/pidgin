# Pidgin Roadmap

## v0.4 — Reliability and Integration

The sprint where Pidgin becomes usable at scale. Every item serves one goal:
index full SDKs reliably and start using Pidgin in our own workflows.

### Blocking Track (Phase 1 — nothing else until these ship)

- **Incremental nest writes.** Write results after each batch completes. Ctrl+C
  loses at most one batch (~20 functions), not the entire run.
- **Graceful shutdown.** Catch KeyboardInterrupt, write partial results, print
  clean summary ("Interrupted. Wrote N/M. Resume with same command."), exit 130.
- **Progress tracking.** After each batch: `[batch 3/247] 300/4930 | 215 converged (71.7%) | ~4h remaining`
- **Abandoned batch recovery.** On startup, check OpenAI for completed batches
  from prior runs. Download results, apply to nest, then continue with remaining.

### Model Consolidation (Phase 2)

- **Gate model experiment.** Run G1-G5 gate probes against gpt-4.1-mini. If it
  matches haiku accuracy, switch. Drop Anthropic API dependency entirely.
- **Agent file rewrite.** One-shot by Opus, reviewed by different Opus context.
  Update model references, add Pidgin tool instructions, trim with prompting
  reference. Markdown with XML tags. Not a taxonomy rethink — just make them
  better and current.
- **Per-mission agent termination.** Sprint runner dispatches one mission per
  agent. Agent executes, writes report to log.md, terminates. Next mission gets
  fresh context with: mission spec, risk review, pre-decisions, and dependency
  log entries only. The log is the inter-agent communication channel.

### Pidgin Integration (Phase 3)

- **Agents use Pidgin for context.** Before modifying code: `pidgin query` +
  `pidgin depends`. After modifying code: `pidgin index --sync` on changed files.
  Prompt-time injection of relevant SDK documentation via nest queries.
- **Class method extraction.** Parser walks class bodies, extracts public methods.
  Unblocks indexing of SDKs that are class-based (embeddings, files, batches).
- **Skills rewrite.** digest → pidgin index. embed → pidgin index. finalize →
  pidgin index + pidgin egg + technologic. Mark tools/ as legacy.

### Documentation and Cleanup (Phase 4)

- **docs/pidgin.md.** What is Pidgin, how it works, what it can do. Include MLD
  documentation. Not a sprint log. Supersedes docs/v0.md and docs/v1.md.
- **CLAUDE.md / ORIGAMI.md / Architecture.md audit.** Run through cleanup-prompt.
  Add XML tags at structural boundaries. Prune CLAUDE.md to 150-line budget.
  Don't restructure ORIGAMI.md without testing principle extraction.
- **Move venv to .venv at project root.** One-time migration.
- **Move sprint template into new-sprint skill directory.** Delete templates/ at root.
- **v0.3 carry-forward debt.** Absolute-path identity key, hardcoded paths,
  function_dict_hash divergence.

### Experimental (Phase 5, conditional)

- **Fine-tuning data validation.** Verify training-data.jsonl structure and
  quality on the ~166 existing examples.
- **First fine-tune attempt.** If data reaches 500+ examples from SDK indexing,
  fine-tune gpt-4.1-nano on converged MLD winners. Compare against
  converge.xml+nano baseline on M3 probes.
- **converge.xml prompt audit.** Remove anti-examples, test impact. Replace
  hand-crafted examples with real converged winners from runs.

---

## v0.5 — Pidgin as Agent Infrastructure

The sprint where Pidgin becomes the primary tool for agent workflows.

### Write Operations Through Pidgin

- `pidgin edit` — file modification with MLD-aware audit trail. Before writing,
  query the nest for the function being modified, include the description in
  the commit message, track description delta.
- `pidgin commit` — git commit with automatic description update for changed
  functions. Re-index only the changed files.
- `pidgin rollback` — revert to a previous audited state using the JSONL trail.

### Context Injection

- **Prompt-time SDK documentation.** Agent is about to call `openai.batches.create()`.
  Pidgin queries the openai-python nest, finds the function description and
  signature, injects it into the agent's context. No hallucinated parameters.
- **Cross-repo queries.** Agent working in fe-toolkit can query the openai-python
  nest, the anthropic-python nest, and fe-toolkit's own nest in one call.

### Sprint Infrastructure

- **Per-mission fresh context.** Formalize the v0.4 per-mission termination
  pattern into the mission grammar. Each mission's context is: spec + risk
  review + pre-decisions + dependency log entries + relevant nest queries.
- **Pidgin-native mission reports.** Mission reports written via `pidgin new`
  with audit trail and commit brackets.

### Parser Expansion

- **Tree-sitter for Rust** (Watchtower repo).
- **TypeScript and Go** parsers.
- **Decorator and attribute extraction** for richer metadata.

### Agent Taxonomy Rethink

- What does Execute/Reason/Scout mean when the model routing has changed?
- Should agents be task-typed (coder, reviewer, planner) rather than tier-typed?
- How do OpenAI background agents (gpt-5.4-mini, gpt-4.1) interact with
  Claude Code's interactive agents (Sonnet, Opus)?

---

## v0.6 — Pidgin Standalone

The sprint where Pidgin becomes publishable as wiregrass/pidgin.

### Decouple from fe-toolkit

- Pidgin gets its own repo with its own pyproject.toml
- Default principles baked into prompts; fe-toolkit overrides via config
- Standard conventions: env vars for API keys, ~/.pidgin/ for global config
- Remove all fe-toolkit-specific paths and assumptions

### Clean-Room Refactoring (Bidirectional MLD Application)

- Index entire repo → cluster descriptions → identify redundancy
- Generate new implementations from descriptions
- Behavioral equivalence via test suite (original code as oracle)
- The refactoring-as-a-service product

### Fine-Tuned Model Stack

- Generation: fine-tuned gpt-4.1-nano replaces converge.xml entirely
- Gate: fine-tuned gpt-4.1-mini replaces gate.xml
- Embedding: evaluate voyage-code-3 or gemini-embedding-001 against
  text-embedding-3-small for code-description workloads
- The prompt IS the model. Zero preamble. Maximum batch throughput.

---

## v1.0 — The Vision

Pidgin is an open-source LLM-native toolkit that makes any codebase
queryable, self-documenting, and refactorable. You run `pidgin index`
and your code explains itself. You run `pidgin query` and find what you
need in 500ms. You run `pidgin egg` and every directory has accurate,
current documentation. You run `pidgin refactor` and the codebase
restructures itself while preserving behavior.

The sprint infrastructure (Marionette, mission grammar, commander protocol)
is the closed-source orchestration layer. It uses Pidgin's primitives to
plan, execute, and validate changes at scale. The flock generates, the
architect judges, and Pidgin is the toolkit that connects them.

Agents don't grep. They don't guess at parameter names. They don't
hallucinate API calls. They query the nest, get the description and
signature, and proceed with confidence. Every edit is audited. Every
description is empirically converged. Every commit carries the semantic
diff alongside the textual one.

The economic model: fine-tuned nano models eliminate prompt preambles,
making indexing nearly free. A full SDK indexes for pennies. The batch
API handles scale. The nest handles storage. Git handles history. Pidgin
handles everything else.
