# Tooling v0.3 — Seed Context

Items collected during the v0.2 design session for future work.
Nothing here is committed. This is the backlog.

## Vocabulary

- **Flock** — casting N candidates and converging geometrically.
  "Release a flock of 10." The batch generation unit.
- **Egg** — a CLAUDE.md left behind by `pidgin index` as a
  discovery artifact. Any model can read it without Pidgin installed.
  MLD descriptions of the directory contents as an index.
- **Nest** — the ChromaDB store at `.pidgin/nest/`. The queryable
  index of a repo's code and documentation.

## Pidgin product statement

Pidgin is `ls`, `grep`, `cat`, `sed`, and `find` — rebuilt for
models. The nest is the filesystem index. The egg is the README
that writes itself. MLD is `man` pages generated from the code.
CRISPR is `sed` with semantic targeting. Query is `grep` over
embeddings instead of strings.

Pidgin is a toolkit, not an agent. Agents decide what to do.
Toolkits do what they're told. Pidgin does what Marionette tells it.

## The flock/architect split

Nano models: volume generation, mechanical elaboration, convergence.
Opus: design fidelity, architectural judgment, intent preservation.

Pipeline: Opus writes intent → flock elaborates → Opus validates.
Pidgin is the flock. Origami is the philosophy Opus operates under.

## Research: divergent risk analysis

For each mission after selection:
1. Generate 10 "what could go wrong" candidates at max temperature
2. Embed all 10, pick the 3 furthest from centroid (most divergent)
3. Hand the 3 weirdest scenarios to Opus: "Are any real? What else?"

The flock finds the edge cases. Opus judges which ones matter.
Not built. Requires temperature control (gpt-5.4 supports it,
gpt-5 doesn't).

## Research: design-level convergence

The v0.2 experiments converged at the sprint plan level (mechanical
translation). The real leverage is converging at the design level —
"how many missions" and "what does each one do." Sprint plans are
formatting. Designs are decisions.

Cast a flock of design variants from the same context documents.
Converge geometrically. Pick or synthesize. Then the sprint plan
becomes a single deterministic translation.

## Research: code↔description embedding proximity

Take the 22 converged functions from v0.1. Embed each function
body. Embed its MLD description. Compute cosine similarity between
the pair. Does well-structured code embed near its description?

If yes: MLD finds the nearest natural language point to the code
in embedding space. The compression algorithm bridges modalities.

If no: code and text occupy different subspaces. Bidirectional MLD
needs a cross-modal embedding model or different similarity metric.

Either result is publishable. 5-minute experiment with existing data.

### Three-axis MLD selection

For the code↔description experiment, Opus selection across:
- Shortest description (compression)
- Centroid-nearest (consensus)
- Code-nearest (fidelity)

These are genuinely different axes. Opus synthesizes a Pareto-optimal
description balancing all three.

## Research: temperature sweep

Temperature as independent variable against convergence tightness.
Run MLD at temperature 0.2, 0.5, 0.8, 1.0 with the same functions.
Does lower temperature produce tighter clusters? Does it sacrifice
diversity needed for the antipode test?

## Infrastructure: document chunking

AST parsing handles code (Python, Rust, TS, JS, Go). XML, markdown,
and HTML need a different chunking strategy — section headers for
markdown, tag hierarchy for XML/HTML. Required for indexing
documentation, config files, and sprint artifacts into the nest.

## Infrastructure: auto-principle injection

Embed the mission payload, query the principles collection for the
3 nearest, inject them. The embedding space does the selection.
No manual principle ID lists. Works automatically for new principles
added to the store.

## Infrastructure: EC2 dev environment

Stop developing on laptop. EC2 instance as canonical dev machine:
- Laptop MCPs to it
- Nests live there permanently
- Cron keeps nests fresh (re-index on git pull)
- Base Camp Atlas connection is local network hop
- n8n handles orchestration
- Functionally Marionette without waiting for Marionette

## Infrastructure: PRISM connection

The convergence geometry (Z-buffer membership, centroid selection,
antipode checking, health mesh proximity) is PRISM applied to text.
Multi-model convergence tests (do Opus and GPT-5 converge to the
same region?) test the PRISM thesis: intent convergence is
model-independent. The geometry is a property of the specification,
not the model.
