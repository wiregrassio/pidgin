# Context Index — Tooling V2

Read these documents in order before writing the design.

## Founding Records (what was built and what was learned)

1. `v1-founding-record.md` — What tooling-v1 built, what it proved,
   what it disproved, and what V2 inherits. Start here.

2. `mld.md` — The Minimum Lossless Description method. The core
   algorithm. Read the full document.

3. `mld-validation-report.md` — Raw candidate descriptions, cosine
   similarity matrices, failure analysis from 54 MLD runs. The
   empirical evidence. Read the case studies.

## Design Input (what V2 should implement)

4. `backlog-mld-tuning.md` — Soft budgets, LLM validation gates,
   provider strategy, Voyage AI migration. The MLD pipeline redesign.

5. `backlog-selective-injection-iterative-mld.md` — Three-draft
   generation pattern, gate verb as model call, batch economics,
   selective principle injection. The ensemble evolution.

6. `backlog-external-docs-architecture.md` — SQLite documentation
   store, ChromaDB vectors, cascading trust model, mechanical audit
   trail. The external store architecture.

7. `backlog-origami-reprocessing.md` — ORIGAMI.md / ARCHITECTURE.md /
   CLAUDE.md split. MLD processing Origami itself. The ouroboros.

## Key Constraints

- Structured outputs via tool calls or response_format. Never
  free-form JSON.
- No explicit Anthropic caching. OpenAI auto-caches. If you need
  7+ identical Anthropic calls, the task belongs at a cheaper tier.
- No embedding sidecars. Vectors go to ChromaDB or Atlas.
- No mechanical grammar filter. LLM gates for semantic validation.
- Build /technologic last from proven components.
- Every file operation is a CRISPR operation: line:character
  precision, hash verification, not blind XML section overwrites.
- Provider split: OpenAI for volume generation, Anthropic for
  trust-sensitive operations (Marionette, Opus reasoning).
