# v0.4 Wishlist

Everything beyond the operational reliability blocking track. These are accumulated
from v0.2, v0.3, and the post-sprint design session. The designer should prioritize
and scope — not everything here needs to be in v0.4.

## Fine-Tuning (First Pass)

**Status:** SFT data collection is wired (M18 of v0.3). Training data accumulates
in .pidgin/training-data.jsonl as a byproduct of every index run.

**Current data:** ~166 converged examples from OpenAI SDK sync runs (chat + responses).
Need ~500 for a meaningful first fine-tune. OpenAI SFT documentation says a few
hundred is minimum, a few thousand is good.

**Path to 500:** Index more OpenAI SDK surfaces (when reliability track is done),
index anthropic-python, index operator's own repos (fe-toolkit pidgin/, rf-edge,
watchtower). Diverse codebases matter more than count.

**What gets fine-tuned:**
- Generation model: converged MLD winners as "good" outputs. Replaces the 7.5K
  token converge.xml preamble entirely. The fine-tuned model IS the prompt.
- Gate model: (description, valid/invalid, reason) triples from gate calls. Could
  replace claude-haiku-4-5 with a fine-tuned OpenAI mini, consolidating providers.

**Impact:** Eliminates preamble from batch payloads (50-100x size reduction),
potentially reduces cost from $1.70 to $0.10 for a full SDK index, and removes
the batch file size ceiling entirely.

## Prompt Audit

converge.xml was audited during the v0.3 session using the cleanup-prompt skill.
Findings:

1. 17 anti-examples may anchor the model on failure patterns (pink-elephant effect).
   Test: remove anti-examples, run M3 probes, compare convergence.
2. Duplicate example (ex5 / ex_rust_simple removed in M19 — one copy remains).
3. Role section has contradictory framing ("increasing refinement" vs "each one sentence").
4. No explicit stopping condition for drafts.
5. 33 positive examples may be more than needed. Could get same signal with 15-20
   using real examples from actual runs instead of hand-crafted ones.
6. Have haiku select the best converged winners from run data as replacement examples.

gate.xml and expand.xml should get the same audit treatment.

## Model Routing Experiments

**Gate calls:** Currently claude-haiku-4-5. Test gpt-5.4-mini (reasoning model,
cheap, enforces tool-persistence discipline). Also test gpt-4.1 with tool-use
(non-reasoning, literal instruction following). Run M4's G1-G5 gate probes
against each. If either matches haiku accuracy, consolidate to single provider.

**Generation:** Currently gpt-4.1-nano. Test gpt-5.1 at reasoning_effort=none
(direct 4.1 successor, better calibration). Question: does improved calibration
reduce candidate diversity? Run M3 probes, compare convergence rates and cluster
spread.

**Code generation (bidirectional):** gpt-5.4 fits the gated mission style better
than gpt-5.3-codex. The model selector says 5.4 enforces tool-persistence and
honors phase distinctions. gpt-5.3-codex is for autonomous multi-hour sessions
without interruption — opposite of the coordinator/executor split.

**Model selector:** local/scratch/model_selector.xml has full OpenAI entries.
Anthropic entries being added in a separate operation. No routing table yet —
will be added once empirical testing establishes model-task mappings.

## Parser Improvements

**Class method extraction:** The current AST parser only extracts module-level
`def` statements. Three OpenAI SDK subdirectories (embeddings, files, batches)
returned 0 functions because they're class-based. The parser needs to walk
class bodies and extract public methods (no leading underscore, not __dunder__
unless __init__).

**Tree-sitter for Rust:** Watchtower is Rust. The MLD pipeline is language-agnostic
but the parser is Python-only. tree-sitter with Python bindings is the standard
approach. Extract `pub fn` declarations. One parser module per language
(parser_rust.py, parser_typescript.py, parser_go.py).

**Module field:** M5 carry-forward — module field degrades to basename when
walk_source_files yields individual files. Should always be the relative path
from repo root.

**Single-file indexing:** walk_source_files returns nothing when given a file
path instead of a directory. Should work on both.

## Skills Rewrite

With Pidgin providing primitives, existing skills are redundant or thin wrappers:

- `/digest` → `pidgin index . --summarize` (or just `pidgin index` with file summaries)
- `/embed` → `pidgin index .`
- `/dissect` → needs rethinking; cross-module contracts via `pidgin depends` + queries
- `/finalize` → `pidgin index` + `pidgin egg` + `technologic`
- `/cleanup-prompt` → stays as-is (not Pidgin-dependent)
- `/new-sprint` and `/run-sprint` → stay, but should call Pidgin verbs where applicable

## Draft Stratification Analysis

M11 (v0.3) added per-draft centroid tracking. The data is being collected but
hasn't been analyzed yet. First real-world run with this data will show whether
draft_3 clusters tighter than draft_1 across functions.

The operator's hypothesis: if variance decreases from draft_1 → draft_2 → draft_3,
within-call refinement is working. If both transitions decrease: CONVERGED. One
decreases one increases: AMBIGUOUS. Both increase: DIVERGENT. This could complement
or replace the antipode test.

A separate research conversation is evaluating the mathematical rigor of the
antipode test and alternative convergence metrics.

## v0.3 Carry-Forward Debt

- M13: Identity key uses absolute file path (nest not portable across machines)
- M13: function_dict_hash diverges from function_source_hash (whitespace re-MLD)
- candidates.py:86 + templates.py:96: hardcoded /Users/elliotwillis paths
- tools/ cannot be deleted (5 skill files depend on it)
- mld.py:15: stale DEPENDS comment
- P1 probe description still admits surface forms (3/6 match)

## Bidirectional MLD Applications (Future)

The operator identified three products enabled by bidirectional MLD:

1. **Design-to-sprint:** Convert design document intentions into code/mission specs.
   Validate via round-trip: generated code compressed back to description should
   match original intention.

2. **Intention-code validation:** Given a document with both stated intention and
   code block, run bidirectional MLD both ways and check for match. Static analysis
   that works across languages.

3. **Clean-room refactoring:** Index entire repo (function → description). Cluster
   descriptions to find redundancy and misplacement. Regenerate functions from
   descriptions into a new structure. Original code is the test oracle —
   behavioral equivalence via test suite, not textual matching.

These are v0.5+ but inform the design of v0.4's fine-tuning and parser work.

## External SDK Indexing

Priority targets once reliability track ships:
- openai-python (4930 functions post-exclude, partially indexed)
- anthropic-python
- OpenAI Agent SDK
- Anthropic Agent SDK

Each indexed SDK becomes queryable documentation. CLAUDE.md can reference nests
for version-pinned, hallucination-free API documentation. Also produces training
data for fine-tuning.

## Operator Design Preferences

- Pidgin is an LLM tool that can be used as a CLI
- Human-friendly defaults; --raw and --xml for LLM callers
- Four human verbs: init, index, query, summarize
- Everything else is LLM-facing infrastructure
- "I don't give a shit about ceremony" — pragmatic over process when the answer is obvious
- $200/month API budget, expandable to $2000+ if justified by output quality
- Tokens are cheap; developer time is expensive
- Single source of truth (the will of Origami)
