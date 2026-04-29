# Tooling v0.2 — Design

## Mandate

v0.1 built the engine. v0.2 packages it. The MLD pipeline works, the ChromaDB store works, Origami is compressed, four skills are validated. What doesn't exist: the write model that v0.1's CRISPR-for-everything exposed as broken, the prompt format that Anthropic's own guidance says is correct, the batch dispatch that eliminates rate limiting, the CLI that makes the engine usable, or the packaging that makes it portable. v0.2 delivers Pidgin — not as a concept, but as a Python library and CLI that an engineer outside this repo can install and run.

## Ground Truth

### What v0.1 proved (carry forward, do not revisit)

- Soft budgets (generous ceiling + conciseness instruction) eliminate truncation. Not debatable.
- Three-draft generation (3 drafts × 5 calls = 15 candidates) produces natural variation. Not debatable.
- LLM validation gates replace the grammar filter. The grammar filter rejected 0/140 candidates. Dead code.
- Structured outputs via response_format eliminate partial-JSON parse failures. Not debatable.
- ChromaDB as sole store. Amendment 2 killed SQLite. No sync bugs, no joins needed. Not debatable.
- GPT-4.1 nano for generation. 22/22 convergences (18 V1 + 4 V2) at $0.006/probe. GPT-5 nano failed — reasoning models exhaust the token budget on deliberation before producing output. Pattern completion doesn't benefit from deliberation.
- Skills in dependency order. /embed → /digest → /dissect → /technologic. Every pipeline flaw surfaced early. Validated.
- Single embedding provider. OpenAI text-embedding-3-small at 256 dimensions. Voyage was killed in Amendment 1 before any mission touched it. One provider, one model, one dimension.
- Origami compression. 19/19 converged. 16 at 1.00, 3 at 0.80. The 0.80 signals were correct — the algorithm identified ambiguity the operator resolved in favor of the compression.

### What v0.1 disproved (do not repeat)

- CRISPR for everything. 660 lines to build a markdown file through a surgical editor. New files don't need hash verification. Document generation doesn't need line-character precision. The write model needs modes.
- Operation-level git commits. Comment stripping on one file produces 20-40 commits. The bracket wraps the file, not each operation.
- GPT-5 nano for MLD generation. ~1,472 tokens of internal deliberation, zero output tokens. PhD dispatched to mop a floor.
- Legacy compatibility shims. Five indexed files, one operator, v0.1. There is no backwards.
- Dual stores. ChromaDB + SQLite sync is a bug class, not a feature.

### What emerged from v0.1 but was not built (this sprint's work)

The v2-founding-record names eight things that outgrew v0.1. Three are foundational (they change how existing code works), three are extensions (they add new capability), and two are speculative (they require empirical validation before committing to).

**Foundational:**
1. Write model — four modes with distinct commit semantics
2. XML prompt format — structural migration of all prompts and artifacts
3. Pidgin CLI and packaging — the identity, the verbs, the permissions, the nest convention

**Extensions:**
4. Batch dispatch — OpenAI Batch API integration with auto-threshold
5. Adaptive candidate counts — expansion logic for marginal convergence
6. Nested nest discovery — parent repo finds child `.pidgin/nest/` directories

**Speculative:**
7. Bidirectional MLD — description→code convergence (geometry unvalidated in code embedding space)
8. Sprint plan as multi-pass artifact — depends on bidirectional MLD

## Architecture

### The Three-Layer Stack

This hierarchy was established during v0.1 execution. v0.2 formalizes it.

- **Origami** — the philosophy. Compressed principles. Ships as a document (ORIGAMI.md). Read by humans and injected selectively into agent preambles. Never ships as code.
- **Pidgin** — the tool. The MLD pipeline, the store, the CLI, the verb vocabulary. Ships as a Python package (`pip install pidgin`). This is what v0.2 builds.
- **Marionette** — the executor. Remote MCP server that uses Pidgin internally. Ships as a container. Not in scope for v0.2.

### Pidgin Package Structure

```
pidgin/
├── __init__.py              # version, top-level API
├── __main__.py              # CLI entry point
├── cli.py                   # argparse, verb dispatch
├── verbs/
│   ├── __init__.py
│   ├── converge.py          # MLD convergence (both directions)
│   ├── gate.py              # pass/fail/unsure with justification
│   ├── rank.py              # order N candidates by criterion
│   ├── summarize.py         # compress to target density
│   ├── classify.py          # assign to N categories
│   └── extract.py           # structured data from unstructured input
├── pipeline/
│   ├── __init__.py
│   ├── mld.py               # core MLD algorithm (from tools/mld/pipeline.py)
│   ├── batch.py             # batch dispatch (new)
│   ├── candidates.py        # adaptive candidate logic (new)
│   └── geometry.py          # antipode test, cosine sim, centroid (from tools/mld/probe.py)
├── store/
│   ├── __init__.py
│   ├── nest.py              # ChromaDB store operations (from tools/store/sections_chroma.py + vectors.py)
│   ├── audit.py             # write audit trail (from tools/store/audit.py, refactored)
│   └── discovery.py         # nested nest discovery (new)
├── write/
│   ├── __init__.py
│   ├── index.py             # Mode 1: read-only against source, write to nest
│   ├── update.py            # Mode 2: CRISPR surgical edits, transaction context manager
│   ├── new.py               # Mode 3: create files from generated content
│   └── compress.py          # Mode 4: MLD-compress text to new artifact
├── prompts/
│   ├── converge.xml         # generation prompt (from tools/prompts/generate.md, rewritten)
│   ├── gate.xml             # validation prompt (from tools/prompts/validate.md, rewritten)
│   └── templates.py         # XML assembly, caching boundary management
└── utils/
    ├── __init__.py
    ├── api.py               # provider routing, embed_for_store (from tools/utils/api.py)
    ├── parser.py            # AST extraction (from tools/utils/parser.py)
    └── git.py               # git bracket operations (extracted from audit.py)
```

This is extraction, not rewrite. Every file has a provenance annotation pointing to the v0.1 source. The validated code moves; the architecture reshapes around it.

### Write Model

Four modes. Each has distinct commit semantics, permission requirements, and audit patterns. The write-model context document defines these completely. The implementation notes:

**Mode 1 — Index.** No source file writes. ChromaDB only. Permission: `--write-db`. Audit: JSONL entry. No git involvement. This is what `pidgin index .` does.

**Mode 2 — Update.** Surgical edits. The only mode that touches existing source files. Transaction context manager pattern:

```python
with pidgin.update("parser.py") as f:
    f.strip_comment(line=5)
    f.insert_tag(line=5, tag="mld:extract_ast", content=description)
    f.replace(line_start=10, line_end=12, content=new_block)
# writes file once, one pre/post git bracket, one audit entry
```

All operations accumulate in memory. One write, one bracket, one audit entry. Permission: `--write-source`. This replaces v0.1's per-operation git commits.

**Mode 3 — New.** Create complete files. No hash verification, no pre-write commit. One git commit after the batch. Permission: `--write-source`. This replaces the 660-line origami_reprocess.py workaround.

**Mode 4 — Compress.** Mechanically identical to Mode 3 on the write side. Semantically distinct: records input `source_hash` for lineage tracing. Permission: `--write-db` + `--write-source`.

The seed-empty workaround is dead on arrival. `artifact_write` handles Modes 3 and 4. CRISPR (`crispr_write` / `crispr_edit`) is retained exclusively for Mode 2, gaining the transaction context manager.

### XML Prompt Format

All Pidgin prompts become XML documents. The structural argument from xml-prompt-format.md is sound: XML tags are explicit structure that models parse directly; markdown headers are visual formatting that models must infer structure from. In a crowded context window, unambiguous boundaries matter.

The caching architecture falls out naturally:

```xml
<pidgin_prompt verb="converge" doc_type="function_description">
  <role>...</role>
  <principles>...</principles>         <!-- MLD-compressed, ~45 tokens for 3 principles -->
  <rules>...</rules>
  <examples>...</examples>
  <!-- everything above this line is the cached preamble -->
  <payload>
    <function file="..." name="..." line_start="...">
      <!-- function body — varies per call -->
    </function>
  </payload>
  <output_schema>...</output_schema>
</pidgin_prompt>
```

The migration path: rewrite `generate.md` and `validate.md` as XML. Update `preamble.py` to assemble XML blocks. Update section storage to store XML-formatted documents. Source annotations gain XML boundary markers. Sprint plan templates use XML structure with per-pass read/write regions.

This is prompt engineering work. It touches every template but no pipeline logic.

### Batch Dispatch

OpenAI Batch API integration. The economics: 50% cost discount, separate higher rate limits, identical preambles with varying payloads — this is the ideal batch workload.

**Auto-threshold:** under 10 tasks synchronous, over 10 batch. The user sees which mode they're in. `--sync` forces sequential. `--batch` forces batch. The threshold of 10 is a design-time default subject to empirical tuning.

**Two-round-trip pattern for MLD:**
1. Generation batch — one JSONL file, all function payloads, one upload, one submission
2. Embedding batch — all candidates from round 1, one JSONL, one submission
3. Local convergence math — numpy, no API call
4. Gate batch (optional) — if gate calls exceed threshold

**Implementation:** `pipeline/batch.py` gains a batch dispatch path alongside the existing synchronous path. The `mld()` function gains a `dispatch` parameter (`sync | batch | auto`). Both paths produce identical data structures downstream. The convergence algorithm doesn't know or care where candidates came from.

**Anthropic batching:** Message Batches API follows the same pattern. Gate and selection calls that go to Anthropic models can be batched. The Opus selection call is the most expensive per-call operation — batching it across functions reduces cost and avoids per-model rate limits.

### Adaptive Candidates

The expansion logic from adaptive-candidates.md, integrated into `pipeline/candidates.py`:

- 5/5 or 4/5: accept. Clear convergence.
- 3/5: run 5 more calls (15 more candidates). Retest against the full 30. Accept at 7/10 or better. Flag non-convergent otherwise.
- Below 3/5: flag non-convergent immediately.

This is a loop around the existing convergence test, not a new code path. The thresholds are configurable. The 7/10 expanded-set threshold is more lenient because 30 candidates have more natural variation than 15. Interacts well with batch dispatch — expansion calls collect into a second batch.

v0.2 must track convergence ratios (not just converged/not-converged) to build empirical data on trigger frequency. v0.1 didn't track this.

### Nested Nest Discovery

`pidgin init` at a parent repo scans for child `.pidgin/nest/` directories and registers them as namespace pointers. A query with namespace `.` searches all nests. Implementation in `store/discovery.py`.

This enables fe-toolkit (containing watchtower, switchboard, marionette as sub-repos) to discover and cross-query all child nests from one command.

## Decisions

### Decision 1: Bidirectional MLD is a validation target, not a committed feature

The geometry should work in both directions. Code→description is validated (22/22 runs). Description→code has zero empirical runs. The code embedding space may behave differently — variable names, control flow patterns, and formatting create syntactic structure that natural language doesn't have.

**The validation plan:** take 5 MLD descriptions from v0.1 (embed, main, apply, merge, plus one complex function), run description→code convergence at N=10 with budget_range=(50, 200). Check whether converged implementations are (a) syntactically valid, (b) semantically correct against the original, (c) stable across runs.

Reduced probe matrix: 2 budgets (50, 200 — extremes only) × 2 stability runs × 5 probes × 10 candidates = 200 generation calls. Under $1.00 via batch.

**The gate:** if 4/5 probes produce stable, correct implementations, bidirectional MLD is validated and the sprint plan as multi-pass artifact becomes a committed feature. If fewer than 3/5 produce stable results, the direction needs a different embedding model or similarity metric, and the sprint-plan feature is deferred to v0.3.

**No code is committed to bidirectional MLD until the validation probes pass.** The sprint plan includes the validation mission. It does not include the sprint-plan-as-artifact missions unless the gate clears.

### Decision 2: Extraction, not rewrite

The validated v0.1 code moves into the Pidgin package structure. Functions that work don't get rewritten. The architecture reshapes around them. Every file in `pidgin/` has a provenance comment pointing to its v0.1 source. Diffs should be structural (moved, renamed, re-imported) not behavioral (logic changed).

Exceptions: `audit.py` gains the transaction context manager (new behavior required by Mode 2). `pipeline.py` gains the batch dispatch path (new behavior required by batch). `sections_chroma.py` and `vectors.py` merge into `nest.py` (structural consolidation, no behavior change).

### Decision 3: XML migration is a prompt engineering sprint

The XML prompt format changes templates, not pipeline logic. `generate.md` → `converge.xml`. `validate.md` → `gate.xml`. `preamble.py` assembles XML blocks instead of markdown sections. Section storage returns XML fragments. Source annotations use XML boundary markers.

The pipeline functions that call the API don't care whether the prompt is markdown or XML — they pass a string. The change is in what string they pass.

### Decision 4: CLI ships with four verbs and three flags

The Pidgin CLI is defined completely in pidgin-architecture.md. Four verbs: `index`, `update`, `new`, `compress`. Three permission flags: `--write-db`, `--write-source`. Default is read-only.

```
pidgin index .                              # index current repo
pidgin index ./src --write-db               # index with store writes
pidgin query "what handles retry"           # search the nest
pidgin update ./parser.py --write-source    # surgical edit
pidgin new origami                          # generate new file
pidgin compress manifesto.md                # MLD-compress text
pidgin init                                 # discover nested nests
```

The CLI is the packaging. The verbs map 1:1 to the `verbs/` module. The flags map to the permission model. `python -m pidgin` is the entry point.

### Decision 5: Open source prep but no public release in v0.2

The repo structure, the MIT license header, the README-as-blog-post, the namespace reservation on PyPI — all of this is scoped work. The public release is not. v0.2 delivers a package that works internally. The release engineering (Go rewrite consideration, CI/CD, documentation site, Medium post) is a separate sprint after six months of internal use. The pidgin-architecture.md is clear: "push code after V2 closes and extraction is clean."

### Decision 6: Embedding strategy stays unified

One provider. One model. One dimension. OpenAI text-embedding-3-small at 256 dimensions for everything — ephemeral MLD geometry and stored nest vectors. Voyage was killed. The convergence algorithm is validated against this model. Changing it requires re-validation. Constants live at `utils/api.py`. The `embed_for_store()` helper is the single entry point.

## Phase Structure

The sprint is phased by dependency, not by feature. Each phase validates the layer the next phase depends on.

### Phase 1 — Foundation

The write model and XML prompt migration. These change how existing code operates before adding new capability.

**Missions:**
- **M1: Write model — artifact_write.** Implement `write/new.py` and `write/compress.py`. Batch file creation, one git commit per batch, one audit entry. Test: create three files in one batch, verify one commit and one audit record.
- **M2: Write model — transaction context manager.** Refactor `write/update.py` from v0.1's `crispr_write`/`crispr_edit`. All operations accumulate in memory. One write, one git bracket per file. Test: queue 5 edits on one file, verify one pre-commit, one post-commit, one audit entry listing all 5 operations.
- **M3: XML prompt — converge.xml.** Rewrite `generate.md` as `prompts/converge.xml`. Cached preamble above `<payload>`, variable payload below. Test: Capture convergence results and compare against v0.1 baseline. SOFT fail on count difference — the regression test is whether XML migration changed convergence behavior, not whether all probes converge.
- **M4: XML prompt — gate.xml.** Rewrite `validate.md` as `prompts/gate.xml`. Structured output schema in XML. Test: run gate on 4 v0.1 converged descriptions, verify all pass.
- **M5: XML assembly.** `prompts/templates.py` — build XML prompts from template + principles + payload. Selective principle injection from the principle registry. Test: assemble a preamble with principles [1, 3, 7], verify total token count is ~45 tokens for principles (vs ~600 for full bodies).

### Phase 2 — Infrastructure

Batch dispatch and adaptive candidates. New capability layered on validated foundation.

**Missions:**
- **M6: Batch dispatch — generation path.** `pipeline/batch.py` — JSONL construction, file upload, batch submission, polling, result parsing. Auto-threshold at 10. Test: batch 20 generation requests, verify results match synchronous output for the same inputs.
- **M7: Batch dispatch — embedding path.** Extend `pipeline/batch.py` for embedding batches. Two-round-trip pattern: generation batch → embedding batch → local geometry. Test: full MLD pipeline on 5 functions via batch, verify convergence results.
- **M8: Adaptive candidates.** `pipeline/candidates.py` — expansion logic, ratio tracking. Test: synthesize a 3/5 convergence scenario, verify expansion triggers, verify 7/10 acceptance threshold.
- **M9: Anthropic batch integration.** Message Batches API path for gate and selection calls. Test: batch 10 gate calls, verify results match synchronous.

### Phase 3 — Packaging

CLI, nest convention, package structure. The v0.1 tools become Pidgin.

**Missions:**
- **M10: Package extraction.** Move validated v0.1 code into the `pidgin/` package structure. Provenance comments on every file. No behavior changes. Test: all existing v0.1 tests pass against the new import paths.
- **M11: CLI — four verbs.** `cli.py` and `__main__.py`. Argparse with subcommands for `index`, `update`, `new`, `compress`, `query`, `init`. Permission flags. Test: `python -m pidgin index . --write-db` indexes the current repo.
- **M12: Nest convention.** `.pidgin/nest/` as the store path. `.pidgin/CLAUDE.md` auto-generated by `pidgin index`. Test: `pidgin index .` creates `.pidgin/nest/` with ChromaDB files and `.pidgin/CLAUDE.md` with the query instructions.
- **M13: Nested nest discovery.** `store/discovery.py` — `pidgin init` finds child nests, registers namespace pointers, `.` queries all. Test: create two child repos with nests, run `pidgin init`, verify cross-nest query returns results from both.

### Phase 4 — Validation

Bidirectional MLD empirical probes. This phase produces data, not features.

**Missions:**
- **M14: Bidirectional MLD — probe design.** Select 5 MLD descriptions from v0.1. Define the probe parameters (N=10, budget_range=(50, 200), embedding model). Write the probe harness.
- **M15: Bidirectional MLD — execution.** Run 5 probes. Record: convergence ratio per probe, syntactic validity of converged implementations, semantic correctness against originals, stability across 3 repeated runs.
- **M16: Bidirectional MLD — gate decision.** Evaluate results against the gate criteria from Decision 1. If 4/5 probes pass: bidirectional MLD is validated, unlock Phase 5. If fewer than 3/5: defer to v0.3, document findings, close the sprint.

### Phase 5 — Sprint Plan as Artifact (conditional on Phase 4 gate)

Only if bidirectional MLD validates.

**Missions:**
- **M17: Sprint plan XML template.** Define the four-pass XML structure: `<description>` (human), `<compressed>` (Pidgin compress), `<implementation>` (Pidgin expand), `<validation>` (human review).
- **M18: Multi-pass processor.** Each pass reads its input tag, writes its output tag, leaves all other tags untouched. Test: process a 3-mission sprint plan through passes 2 and 3, verify the document accumulates state.
- **M19: Integration validation.** Run the full four-pass cycle on a real sprint plan (v0.2's own plan). The sprint validates itself.

## Sprint Governance

### Who judges what

- **Design architect (this document's author):** owns the design, judges the sprint plan and sprint runner, resolves ambiguity in mission specs, holds the Phase 4 gate decision.
- **Sprint planner:** translates this design into executable mission specs with inputs, outputs, validation criteria, and dependency declarations. Answers to the design architect.
- **Sprint runner:** executes missions in order, reports results, stops on RED. Answers to the sprint planner and, through the planner, to the design architect.

### Escalation

The sprint runner escalates to the sprint planner on: mission ambiguity, unexpected failures, results that contradict the design. The sprint planner escalates to the design architect on: mission specs that don't map cleanly to the design, Phase 4 gate decisions, scope changes.

### Sprint plan format

The sprint plan is a well-formed XML document (`sprint.xml`)
conforming to the mission grammar at
`rf-edge/marionette/mission-grammar.md`. The root element is
`<sprint>`. Each mission is a `<mission>` element with `n`, `tier`,
and `review` attributes, containing the standard inner tags
(`<context>`, `<objective>`, `<specification>`, `<steps>`, `<report>`).
Code-heavy content uses CDATA sections. The sprint plan is authored
by `/new-sprint` — not by hand.

### Constraints

- Total API spend target: under $2.00 for the full sprint (v0.1 was under $0.50; v0.2 adds batch and bidirectional probes).
- No behavior changes to validated v0.1 pipeline code during Phase 1-3 extraction. Structural changes only.
- Phase 5 missions do not begin until the Phase 4 gate decision is issued by the design architect.
- Every mission produces a validation artifact (test output, probe result, or operator confirmation) before the next mission dispatches.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Bidirectional MLD fails validation | Medium | Phase 5 deferred to v0.3 | Phase 4 is isolated. No code depends on it until the gate clears. |
| XML prompt migration degrades convergence quality | Low | M3-M4 RED, prompt revision needed | Probes compare directly against v0.1 baselines. Regression is detectable. |
| Batch dispatch polling adds latency to interactive workflows | Low | UX degradation for small jobs | Auto-threshold ensures small jobs stay synchronous. |
| Package extraction breaks import paths | Medium | All downstream tests fail | M10 runs all existing tests against new paths before M11 begins. |
| Adaptive expansion triggers too frequently on real codebases | Unknown | Cost increase, not correctness issue | Ratio tracking in M8 provides data. Threshold is configurable. |

## Success Criteria

v0.2 is GREEN when:

1. `python -m pidgin index . --write-db` indexes fe-toolkit into `.pidgin/nest/` and generates `.pidgin/CLAUDE.md`.
2. `python -m pidgin query "what handles embedding"` returns relevant results from the nest.
3. The write model's four modes each produce the correct number of git commits (0 for index, 2 per file for update, 1 per batch for new/compress).
4. Batch dispatch processes 20+ generation requests in one round trip with results identical to synchronous.
5. All XML prompts produce convergence results matching or exceeding v0.1 baselines.
6. Phase 4 gate decision is issued with data, regardless of outcome.

v0.2 is COMPLETE when all GREEN criteria are met and the design architect confirms disposition.
