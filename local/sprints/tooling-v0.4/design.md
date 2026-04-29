# Tooling v0.4 — Design

## Premise

Sprint v0.3 delivered a complete MLD pipeline: 19 missions, all GREEN, 6 patches. Batch chunking, error surfacing, adaptive stopping, bidirectional MLD validation, SFT data collection, idempotency via source hash, and the full verb surface (init, index, query, summarize, egg, depends). Pidgin is an installable editable package with runtime independence from tools/.

Then the operator pointed it at the OpenAI Python SDK (4930 functions) and reality intervened. Two runs failed. Run 1: 40 minutes, ~300 functions processed, Ctrl+C to move terminals, all results lost — the pipeline holds everything in memory and writes the nest only at completion. Run 2: restarted, idempotency showed 0 unchanged / 4930 new because nothing persisted, operator cancelled rather than burn 27 hours on an unreliable path. The OpenAI batches from Run 1 completed server-side but Pidgin has no recovery mechanism.

The pipeline is all-or-nothing. A 27-hour job that fails at hour 26 loses everything. The math works. The operational wrapper does not.

Two sync runs did succeed: chat/ (72/79 converged, 91%) and responses/ (94/150 converged, 63%). Those 166 converged examples are the current SFT training data. Three additional subdirectories (embeddings, files, batches) returned zero functions because the parser only extracts module-level `def` statements, not class methods.

v0.4 fixes the operational wrapper, consolidates to a single API provider, integrates Pidgin into agent workflows, and cleans up three sprints of accumulated debt. The theme is consolidation, not expansion.

## Scope

18 missions across 5 phases. Phase 1 is the blocking track — nothing dispatches until operational reliability is GREEN. Phase 5 is conditional on training data volume from Phase 2.

Per-mission agent termination is a design convention for this sprint: the runner dispatches one mission per agent context, the agent executes and writes its report to log.md, the next agent reads only its mission spec plus dependency log entries. Every mission spec below states what its report must contain for downstream consumers. If an agent can't proceed from the log alone, the design is wrong.

## Provider Strategy

All API calls consolidate to OpenAI. Anthropic API is dropped from the pipeline entirely.

| Task | Current | v0.4 Target | Notes |
|------|---------|-------------|-------|
| Generation (flock) | gpt-4.1-nano | gpt-4.1-nano | No change. Fine-tunable, cheapest, no reasoning overhead. |
| Gate validation | claude-haiku-4-5 | gpt-4.1-mini | -60% input cost, -68% output cost. Validated by M5. |
| Embeddings | text-embedding-3-small | text-embedding-3-small | No change. |
| Architecture | Opus via Claude Code | Opus via Claude Code | Subscription, not API. No change. |
| Sprint execution | Sonnet via Claude Code | Sonnet via Claude Code | No change. |

If gpt-4.1-mini fails the gate probes in M5, the fallback is gpt-5.4-mini (reasoning model, enforces tool-persistence). The agent file rewrite (M8) depends on M5's result to know which model to reference.

Fine-tuning path: gpt-4.1-nano is the only nano-class model with SFT/DPO/RFT support. Once training data reaches 500+ examples (M6), a first fine-tune attempt (M17) replaces the 7.5K token converge.xml preamble entirely. This eliminates the batch file size ceiling and reduces per-function cost ~50x.

## Conventions

All conventions from sprint-conventions.md apply. New for v0.4:

**Per-mission agent termination.** Each mission's report is the inter-agent communication channel. The runner dispatches one agent per mission. The agent receives: mission spec, risk review, pre-decisions, and log entries from dependency missions only. Reports must be self-contained — state what was done, what changed, what the next agent needs to know, and what was carried forward.

**Tier assignments.** Execute (Sonnet) is the default. Reason (Opus) is reserved for missions requiring architectural judgment, ambiguity resolution, or cross-cutting design decisions. Scout is not used in this sprint — the verification work is folded into execute missions with review flags.

**Review flags.** Applied to missions where the output affects multiple downstream consumers or where a wrong call is expensive to unwind: agent file rewrite (M8), ORIGAMI.md audit (M12), and the first fine-tune (M17).

**One-line fixes.** Batched into M15 (carry-forward debt cleanup). Not wrapped in individual missions.

---

## Phase 1: Operational Reliability

**Gate:** Index 50+ functions via batch, Ctrl+C mid-run, restart, verify partial results persisted and remaining functions resume as new. Clean shutdown message, progress output, exit 130.

This phase is the blocking track. The operator will not run large index jobs until these three missions ship. Nothing else in the sprint dispatches until Phase 1 is GREEN.

### M1: Incremental Nest Writes

**Tier:** execute | **Review:** no | **Depends:** none

The pipeline currently collects all results in memory and writes the nest at the end of the run. M1 changes this to write after each batch completes. After every batch chunk (~100 requests, ~20 functions), upsert converged results into ChromaDB immediately. The SFT data writer (training-data.jsonl) must also write incrementally — append after each batch, not bulk-write at end.

The current `upsert_function_descriptions` call expects all results at once. The implementation either calls it per-batch with a subset or accumulates a write queue and flushes after each batch. The choice is an implementation detail — either works, pick the simpler one.

File-level summaries should generate per-file as that file's functions complete, not in a bulk pass at the end. If a file's functions span multiple batches, the summary generates when the last function in that file completes.

**Success criteria:** Index 50 functions, Ctrl+C after batch 2 (~40 functions), verify nest contains results from completed batches. Restart same command, verify idempotency reports ~40 unchanged and ~10 new.

**Report must include:** which approach was taken (per-batch upsert vs write queue), whether SFT writer was updated, whether file-level summaries are incremental, and the Ctrl+C test results with exact counts.

### M2: Graceful Shutdown

**Tier:** execute | **Review:** no | **Depends:** M1

Catch KeyboardInterrupt at the top level of the index verb. On interrupt: cancel in-flight batch polling (don't wait), write whatever results have been collected via the incremental write path from M1, print a clean summary ("Interrupted. Wrote N/M functions to nest. Resume with the same command to continue."), and exit 130 (standard SIGINT exit code).

Suppress the `RuntimeError: Event loop is closed` async cleanup error from v0.3 stress tests. It's cosmetic but alarming — catch and silence it.

The current KeyboardInterrupt produces 50+ lines of httpx/asyncio traceback. After M2, the output is exactly one summary line.

**Success criteria:** Start an index run, Ctrl+C during batch polling, observe clean one-line summary and exit 130. No traceback. Restart, verify resume.

**Report must include:** the exact interrupt handler location, how async cleanup errors are suppressed, and the test output.

### M3: Progress Tracking

**Tier:** execute | **Review:** no | **Depends:** none (but tests should run after M1)

After each batch completes, print a progress line to stderr:

```
[batch 3/247] 300/4930 functions | 215 converged (71.7%) | ~4h 12m remaining
```

Components: batch number/total, functions processed/total, converged count and running percentage, estimated time remaining based on observed batch completion rate. Also print on batch submission:

```
[batch 4/247] submitted, polling...
```

For `--verbose` mode, print per-function results as they arrive:

```
  ✓ create (converged, cluster=8, tightness=0.94)
  ✗ AsyncChat (not converged, cluster=3)
```

The progress printing belongs in the batch pipeline, not the index verb. The pipeline already knows batch boundaries — it just doesn't emit anything.

**Success criteria:** Run an index of 50+ functions, observe batch-by-batch progress with all components. Time estimate should be within 2x of actual after the first 3 batches.

**Report must include:** where progress emission was added, whether --verbose per-function output works, and sample output from a real run.

---

## Phase 2: Scale and Consolidation

**Gate:** Class methods extractable, gate model decided, 500+ converged examples in training-data.jsonl, abandoned batch recovery operational.

Phase 2 runs after Phase 1 is GREEN. M4 and M5 have no interdependency and can execute in any order. M6 depends on M4 (needs class method extraction for full SDK coverage). M7 is independent.

### M4: Class Method Extraction

**Tier:** execute | **Review:** no | **Depends:** Phase 1 GREEN

The AST parser (parser.py) only extracts module-level `def` statements. Three OpenAI SDK subdirectories (embeddings, files, batches) returned zero functions because they're class-based. M4 extends the parser to walk class bodies and extract public methods: no leading underscore, not `__dunder__` (except `__init__` if it has meaningful logic beyond assignment).

The extracted function's identity should include the class name: `ClassName.method_name` as the function name in the nest. The module field should be the relative path from repo root (fixing the M5 carry-forward where it degrades to basename).

Also fix single-file indexing: `walk_source_files` returns nothing when given a file path instead of a directory. It should handle both.

**Success criteria:** Run `pidgin index` on openai-python/src/openai/resources/embeddings/ and get >0 functions extracted. Run on a single .py file and get results. Verify class methods appear in the nest with `ClassName.method_name` identity.

**Report must include:** how many functions the three previously-empty subdirectories now yield, the identity format for class methods, and whether single-file indexing works.

### M5: Gate Model Experiment

**Tier:** reason | **Review:** no | **Depends:** Phase 1 GREEN

Run the G1-G5 gate probes from v0.2 M4 against gpt-4.1-mini (non-reasoning, literal instruction following, tool-use structured output). Compare accuracy against the claude-haiku-4-5 baseline. If gpt-4.1-mini matches haiku accuracy (4/5 or better on bidirectional probes), recommend switching. If it doesn't, run the same probes against gpt-5.4-mini (reasoning model) as fallback.

This is reason-tier because the agent must interpret ambiguous probe results and make a judgment call on "matches accuracy." A 4/5 match is clear. A 3/5 with different failure modes requires analysis.

**Success criteria:** Probe results for gpt-4.1-mini on G1-G5. If gpt-4.1-mini fails, probe results for gpt-5.4-mini. Clear recommendation with accuracy numbers.

**Report must include:** per-probe pass/fail for each model tested, total accuracy, the recommendation (which model replaces haiku), and any behavioral differences observed (e.g., one model fails on edge cases the other handles). M8 depends on this report to know which model to reference in agent files.

### M6: Full SDK Indexing

**Tier:** execute | **Review:** no | **Depends:** M1, M2, M3, M4

The end-to-end proof that Phase 1 works at scale. Index the full OpenAI Python SDK (openai-python, --exclude "*/types/*") using the batch path. With class method extraction from M4, this should cover the full 4930+ function surface.

The mission succeeds when training-data.jsonl contains 500+ converged examples. Based on the sync runs (91% and 63% convergence rates), 4930 functions should produce 3000+ converged examples. If the run needs to be interrupted and resumed (testing M1/M2 in the wild), that's expected and fine — document the interruption and recovery.

This mission is also the first real-world test of incremental writes, graceful shutdown, and progress tracking under sustained load. Any issues discovered here are carry-forwards, not blockers — the mission succeeds on the training data criterion.

**Success criteria:** 500+ converged examples in .pidgin/training-data.jsonl. Nest is queryable. Progress output was emitted throughout. If interrupted and resumed, idempotency worked correctly.

**Report must include:** total functions discovered, total converged, convergence rate, wall time, any interruptions and recovery behavior, final training-data.jsonl line count, and any operational issues observed (carry-forwards for M15 or v0.5).

### M7: Abandoned Batch Recovery

**Tier:** execute | **Review:** no | **Depends:** M1

Before starting a new index run, check for completed OpenAI batches from prior runs. Pidgin already encodes function name + call index in `custom_id`. On startup: list recent batches (last 24h) via the OpenAI Batch API, filter by status=completed, check if any custom_ids match functions in the current run's to-index list. If matches found, download results, process them through the existing embed → converge → upsert path, then proceed with remaining unprocessed functions.

This doesn't need to be sophisticated. The happy path is: find batches, download, apply, continue. The edge cases (partial batch matches, corrupted results) can fail soft — log the issue and re-process those functions normally.

**Success criteria:** Submit a batch, kill Pidgin before it polls for results, restart, verify recovery downloads and applies the completed batch results before submitting new batches.

**Report must include:** how batch discovery works, what the custom_id matching logic is, how partial matches are handled, and the kill/restart test results.

---

## Phase 3: Integration

**Gate:** Agent files updated with correct model references and Pidgin instructions. Skills rewritten to use Pidgin verbs. No skill imports from tools/ for anything Pidgin provides.

### M8: Agent File Rewrite

**Tier:** reason | **Review:** yes | **Depends:** M5

One-shot rewrite of the Execute/Reason/Scout agent files by Opus, reviewed by a separate Opus context. Three changes per file:

1. Update model references based on M5's gate experiment result (haiku → winning model for any direct API calls in agent instructions).
2. Add Pidgin tool instructions: "Before modifying code, run `pidgin query` and `pidgin depends` for context. After modifying code, run `pidgin index --sync` on changed files."
3. Trim instructions using the prompting-reference.md best practices. Cut redundancy, add XML tags at structural boundaries, tighten language.

Do NOT restructure the Execute/Reason/Scout taxonomy. Do NOT change the tier definitions. Just make the existing files better, current, and aware of Pidgin.

The review context receives the original files and the rewritten files. Review criteria: are model references correct per M5? Are Pidgin instructions actionable? Did trimming remove anything load-bearing?

**Success criteria:** All agent files rewritten. Review PASS or CONCERNS (non-blocking). Model references match M5 recommendation. Pidgin instructions present in all files.

**Report must include:** which files were rewritten, what model references changed, the Pidgin instruction block added, what was trimmed, and the review verdict with any concerns.

### M9: Skills Rewrite

**Tier:** execute | **Review:** no | **Depends:** M4 (class methods enable full Pidgin surface)

Three skills rewritten to use Pidgin verbs: digest → `pidgin index` (with summarize output), embed → `pidgin index`, finalize → `pidgin index` + `pidgin egg` + technologic. Two skills get a review pass for where Pidgin verbs could slot in: new-sprint and run-sprint. Dissect is deferred to v0.5 (needs rethinking, which is expansion).

The key deliverable: after this mission, no skill imports from tools/ for anything Pidgin provides. Any remaining tools/ dependencies are non-Pidgin functionality that stays until tools/ is fully deprecated.

After the skill rewrites, add a note to CLAUDE.md marking tools/ as "legacy — do not add new code." (The CLAUDE.md audit in M12 will clean this up further, but the marker goes in now so any intervening work respects the boundary.)

**Success criteria:** Three skills rewritten and functional. Two skills reviewed with notes on Pidgin integration points. No skill imports from tools/ for Pidgin-provided functionality. tools/ marked legacy in CLAUDE.md.

**Report must include:** for each rewritten skill, what changed and which Pidgin verb replaced what. For reviewed skills, what integration points were identified and what's deferred. List any remaining tools/ dependencies that are not Pidgin-replaceable.

---

## Phase 4: Documentation and Cleanup

**Gate:** docs/pidgin.md written. CLAUDE.md and ORIGAMI.md audited with verification. Project restructuring complete. Carry-forward debt cleared or explicitly deferred to v0.5.

M10 and M11 have no interdependency. M12 should run after M9 (skills rewrite may change CLAUDE.md content). M13 and M14 are independent. M15 is deferrable.

### M10: docs/pidgin.md

**Tier:** reason | **Review:** no | **Depends:** Phase 3 GREEN (needs final verb surface and architecture)

Write docs/pidgin.md from scratch. This is not a sprint consolidation doc — it's product documentation. The audience is someone encountering Pidgin for the first time, including future contributors to wiregrass/pidgin. It supersedes docs/v0.md and docs/v1.md.

Contents: what Pidgin is (LLM-native toolkit for codebase indexing and semantic search), how MLD works (the consensus-driven compression pipeline, convergence testing, the flock/architect split), the verb surface (init, index, query, summarize, egg, depends), the nest (ChromaDB vector store at git root), configuration (env vars, .pidgin/ directory), and the provider strategy (why OpenAI, what gets fine-tuned).

This is reason-tier because the author needs to understand the architecture to explain it coherently, not just merge existing files.

**Success criteria:** docs/pidgin.md exists, covers all sections above, is accurate against current codebase state, and is comprehensible to someone who hasn't read three sprints of context.

**Report must include:** the document structure, any architectural questions that arose during writing (carry-forwards), and whether v0.md/v1.md should be deleted or archived.

### M11: ORIGAMI.md Audit

**Tier:** reason | **Review:** yes | **Depends:** none

Audit ORIGAMI.md using the cleanup-prompt skill. Git commit before any changes (safety net for revert). Run templates.py principle extraction before changes, capture output. Apply audit: add XML tags at structural boundaries, tighten language, prune redundancy. Run principle extraction after changes, compare output. If any principle is lost or altered, revert that change.

This is reason-tier because the parser constraint means every edit must be evaluated for downstream impact. The review context receives the before/after principle extraction output and the diff.

**Success criteria:** ORIGAMI.md audited. Principle extraction produces identical principles before and after (order may change, content must not). Git commit before changes exists as revert point. Review PASS.

**Report must include:** the before/after principle extraction output, what was changed, what was reverted due to parser breakage (if any), and the review verdict.

### M12: CLAUDE.md Audit

**Tier:** execute | **Review:** no | **Depends:** M9 (skills rewrite may add tools/ legacy marker)

Audit CLAUDE.md using the cleanup-prompt skill. Current file is 150+ lines with stale references. Target: prune to ≤150 lines. Add XML tags at structural boundaries. Remove references to deleted or moved items. Ensure the tools/ legacy marker from M9 is present and accurate. Update any model references to reflect M5's decision.

**Success criteria:** CLAUDE.md ≤150 lines. No stale references. XML tags at structural boundaries. tools/ legacy note present.

**Report must include:** line count before and after, what was removed, what was updated.

### M13: Project Restructuring

**Tier:** execute | **Review:** no | **Depends:** none

Three moves:

1. Move tools/.venv → .venv at project root. Update any references in init.sh, pyproject.toml, .gitignore, or skill files that assume the old location. Verify `pip install -e .` works from the new venv.
2. Move templates/sprint-package/ → .claude/skills/new-sprint/templates/. Update references in the new-sprint skill. Delete templates/ at root if empty after the move.
3. Delete pidgin.egg-info/ if present (recreated automatically by pip install -e, already in .gitignore).

Each is a one-session task. Batched into one mission because they're all "move thing, update references, verify."

**Success criteria:** .venv at project root and functional. Sprint template in new location and new-sprint skill works. templates/ deleted. No broken references.

**Report must include:** what was moved, what references were updated, verification results.

### M14: Carry-Forward Debt Cleanup

**Tier:** execute | **Review:** no | **Depends:** M4 (module field fix is in the parser)

Batch of accumulated fixes from v0.3 carry-forward and observed issues. Most are one-liners:

1. **Identity key uses absolute file path** (M13 carry-forward). Change to relative path from repo root. Existing nests will report all functions as "new" on next index — acceptable since M6 re-indexes the primary target anyway.
2. **function_dict_hash diverges from function_source_hash.** Whitespace-only changes trigger re-MLD. Unify to source_hash for idempotency checks.
3. **candidates.py:86 + templates.py:96:** Hardcoded `/Users/elliotwillis/` paths. Replace with dynamic resolution.
4. **mld.py:15:** Stale DEPENDS comment. Remove.
5. **P1 probe description still admits surface forms** (3/6 match). Tighten the probe wording so it rejects surface-level descriptions.

Items 3 and 4 are literal one-liners. Items 1 and 2 affect idempotency behavior — the report must document the impact on existing nests. Item 5 requires running the probe before and after to verify improvement.

**Success criteria:** All 5 items addressed. P1 probe passes at ≥5/6. No hardcoded paths remain.

**Report must include:** for each item, what changed and the verification result. For items 1 and 2, document the idempotency impact.

### M15: Architecture.md Audit (Deferrable)

**Tier:** execute | **Review:** no | **Depends:** none

**This mission drops first if the sprint runs long.**

Audit Architecture.md using the cleanup-prompt skill. Add XML tags at structural boundaries. Prune stale content. This is not a rewrite — just bring it current with the post-v0.4 state of the system.

**Success criteria:** Architecture.md audited, stale content removed, XML tags added.

**Report must include:** what was removed, what was updated.

---

## Phase 5: Experimental (Conditional)

**Gate:** Phase 5 dispatches only if M6 produced 500+ converged examples. If M6 fell short, Phase 5 is deferred to v0.5.

M16 must complete before M17 dispatches. M18 is independent of M16/M17.

### M16: Fine-Tuning Data Validation

**Tier:** execute | **Review:** no | **Depends:** M6

Validate the structure and quality of training-data.jsonl produced by M6. Check: JSONL is well-formed, each line has the expected fields (prompt, completion, metadata), no truncated entries, no duplicate function keys, token counts are within OpenAI SFT limits. Report total example count, distribution of converged vs non-converged, average token length, and any anomalies.

Do not design the fine-tuning pipeline. This mission validates the data, not the training process.

**Success criteria:** training-data.jsonl validated. Example count reported. Any structural issues identified and documented.

**Report must include:** total examples, structural validation results, token distribution statistics, and a go/no-go recommendation for M17.

### M17: First Fine-Tune Attempt

**Tier:** reason | **Review:** yes | **Depends:** M16 (go recommendation)

**Conditional:** Only dispatches if M16 reports 500+ valid examples and recommends go.

Fine-tune gpt-4.1-nano on converged MLD winners from training-data.jsonl. Use OpenAI's SFT API with default hyperparameters — this is an exploratory run, not a production deployment. After training, run the M3 probes (convergence probes from v0.2) against the fine-tuned model and compare convergence rates and cluster quality against the converge.xml + base nano baseline.

The key question: does the fine-tuned model produce MLD-quality descriptions without the 7.5K token preamble? If yes, the batch payload ceiling and preamble cost disappear. If no, document what went wrong and what the next attempt should change.

The review context receives the probe comparison data and the training configuration.

**Success criteria:** Fine-tuned model trained. M3 probes run against fine-tuned model. Comparison against baseline documented with convergence rates and cluster metrics.

**Report must include:** training configuration (example count, epochs, cost), probe results for fine-tuned vs baseline, recommendation (ship / iterate / abandon), and if iterate, what to change.

### M18: converge.xml Prompt Audit

**Tier:** reason | **Review:** no | **Depends:** none

Audit converge.xml using the cleanup-prompt skill findings from v0.3. Three targeted changes:

1. Remove the 17 anti-examples that may anchor the model on failure patterns (pink-elephant effect). Run M3 convergence probes before and after removal. If convergence rate drops, revert.
2. Replace hand-crafted examples with real converged winners from M6's run data. Have the reasoning model select the best 15-20 from the full set. Run M3 probes to verify no regression.
3. Fix the contradictory Role section framing ("increasing refinement" vs "each one sentence"). Pick one and commit.

Do not redesign the MLD pipeline. This is prompt optimization on a working system.

**Success criteria:** converge.xml updated. M3 probes show no regression in convergence rate. Anti-examples removed or impact documented.

**Report must include:** before/after probe results for each change, which examples were replaced, and the final converge.xml diff.

---

## Decision Points

These are ambiguities the commander resolves before sprint dispatch. Executors apply pre-decisions as stated.

**PD1: Gate model fallback.** If gpt-4.1-mini fails G1-G5 probes in M5, the fallback is gpt-5.4-mini. If both fail, gate calls stay on claude-haiku-4-5 and the Anthropic API dependency remains for v0.4. M8 (agent file rewrite) blocks on M5's resolution.

**PD2: Incremental write granularity.** M1 can write per-batch (~20 functions at a time) or accumulate a write queue and flush periodically. The designer recommends per-batch (simpler, matches the existing batch boundary). Commander confirms or overrides before dispatch.

**PD3: Identity key migration.** M14 changes the identity key from absolute path to relative path. Existing nests will see all functions as "new" on next index. The designer recommends accepting this — M6 re-indexes the primary target anyway, and incremental writes (M1) make re-indexing cheap. Commander confirms.

**PD4: Fine-tuning go/no-go.** M17 only dispatches if M16 reports 500+ valid examples and recommends go. If M6 produces fewer than 500 converged examples (unlikely given projected 3000+), Phase 5 reduces to M16 + M18 only.

**PD5: Architecture.md deferral threshold.** M15 drops if the sprint exceeds its time budget. The commander decides the threshold — e.g., "if Phase 4 is not GREEN by mission-day 15, drop M15."

## v0.3 Carry-Forward Addressed

| Item | Addressed In | Status |
|------|-------------|--------|
| M13: Absolute file path identity key | M14 (item 1) | Scoped |
| M13: function_dict_hash divergence | M14 (item 2) | Scoped |
| candidates.py:86 hardcoded path | M14 (item 3) | Scoped |
| templates.py:96 hardcoded path | M14 (item 3) | Scoped |
| mld.py:15 stale DEPENDS comment | M14 (item 4) | Scoped |
| P1 probe surface forms (3/6) | M14 (item 5) | Scoped |
| Module field basename degradation | M4 (parser fix) | Scoped |
| tools/ dependency from skills | M9 (skills rewrite) | Scoped |

## Not In Scope

These items appear in the wishlist or roadmap but are explicitly v0.5+:

- Dissect skill rethinking (expansion, not consolidation)
- Execute/Reason/Scout taxonomy restructure
- Pidgin write verbs (edit, commit, rollback)
- Pidgin repo separation (wiregrass/pidgin)
- Cross-repo queries
- Tree-sitter for Rust (Watchtower)
- TypeScript and Go parsers
- pidgin diff / pidgin status / pidgin review
- Draft stratification analysis (data collecting, not yet sufficient for analysis)
- Bidirectional MLD applications (design-to-sprint, intention-code validation, clean-room refactoring)
- Model routing table (waiting on empirical results from M5)
- gpt-5.1 generation experiment (deferred until fine-tuning baseline established)
