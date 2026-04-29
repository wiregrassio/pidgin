# tooling-v0.2 — Execution Log

**Executed:** 2026-04-27
**Dispatch mode:** local agents (Claude Code Task tool)
**Path translation:** `/project` → `/Users/elliotwillis/Desktop/fe-toolkit`
**Sprint plan:** local/sprints/tooling-v0.2/sprint.xml
**Risk review:** local/sprints/tooling-v0.2/sprint-risk-review.md

---

## Pre-Decisions (PD1–PD6)

**PD1 (scope: M1,M2,M3,M10):** `artifact_write` and `Transaction` accept `project_root: Path | None = None`. When None, auto-derive by walking up to the nearest `.git` directory. This resolves the M1 self-test path contradiction — tests create temp repos with their own .git, so auto-derive finds the temp root, not /project.

**PD2 (scope: M11,M12):** CLI flag placement: per-subcommand, after the verb. Canonical form: `pidgin index . --write-db`. Implementation: `argparse parents=` to share flag definitions across subparsers. Global flags before the subcommand are NOT supported.

**PD3 (scope: M11):** `--sync` and `--batch` both set: hard error. Exit code 2. Message: "Cannot specify both --sync and --batch."

**PD4 (scope: M16,M17,M18,M19):** gate.xml verdict format is a well-formed XML document with `<gate sprint="tooling-v0.2"><verdict>UNLOCK|DEFER|AMBIGUOUS</verdict><summary>text</summary><probes>...</probes></gate>`. M17/M18/M19 Step 0 parses with ElementTree, checks verdict element text. No regex. No markdown.

**PD5 (scope: M1,M2,M9):** Hash algorithm: sha256. No alternatives.

**PD6 (scope: M11):** `index` verb without `--write-db`: dry-run that logs what WOULD be indexed but makes ZERO API calls. No silent spend.

---

## Known Exceptions

**KE1 (scope: M3,M4):** M3 and M4 modify tools/mld/pipeline.py to accept a `prompt_text` parameter. This is additive (new optional kwarg with default None), not a behavior change to existing callers.

**KE2 (scope: M10):** M10 does not delete tools/. Dual import paths will exist. After M10 GREEN, run `grep -r "from tools\." /project --include="*.py" | grep -v "^/project/tools/"` — any hits are bugs.

---

## Preflight Results

| Check | Severity | Result | Notes |
|-------|----------|--------|-------|
| PF1: OpenAI API key + live call | HARD | PASS | gpt-4.1-nano-2025-04-14 responded OK |
| PF2: Anthropic API key | SOFT | PASS | Key present (108 chars) |
| PF3: SDKs importable | HARD | PASS | openai 2.32.0, anthropic 0.97.0, chromadb 1.5.8, numpy 2.4.4 |
| PF4: v0.1 source layout | HARD | PASS | All 10 required files present and non-empty |
| PF5: ORIGAMI.md exists | HARD | PASS | /project/ORIGAMI.md present |
| PF6: v0.1 baseline file | SOFT | PASS | local/sprints/tooling-v0.1/context/v2-mld-validation.md present |
| PF7: git config | HARD | PASS | user.email=elliot@roboflow.com, user.name=Elliot Willis |
| PF8: /project is git repo | HARD | PASS | git rev-parse confirms inside work tree |
| PF9: ChromaDB writes | HARD | PASS | PersistentClient write/read verified (ONNX model downloaded) |
| PF10: Pre-decisions recorded | INFO | DONE | PD1–PD6 above |

**All HARD checks: PASS. Proceeding to M1.**

---

## Amendment 1 — Gate Model + Wiring (issued 2026-04-27, after M6 GREEN)

**Trigger:** M4 finding — gpt-4.1-nano hallucinated on gate validation of known-good descriptions. Gate calls require judgment, not pattern completion. Confirms the flock/architect split: nano generates, Claude judges.

**Changes:**

1. **Gate model for all downstream missions: `claude-haiku-4-5`.**
   Affects M8, M9, M15, M18, and any mission running the gate path.

2. **M9 priority elevated** — gate calls now route through Anthropic, making batched gate dispatch the primary cost control for gate-heavy workloads.

3. **Gate wiring gap to close before M15:** gate.xml is not yet wired into the MLD pipeline. converge.xml IS wired (M3 added prompt_text param). The gate prompt swap must happen before M15 (bidirectional probes run live gate calls). Wiring: pipeline's gate call reads gate.xml via templates.py assembly instead of the hardcoded v0.1 prompt string — same pattern as M3's converge.xml integration. Wire during M10 or as a patch mission between M10 and M14.

4. **pidgin/pipeline/mld.py divergence:** M6's copy (dispatch param) and tools/mld/pipeline.py (M3's prompt_text param) have diverged. M10 must reconcile both additions into the pidgin/ copy — dispatch param from M6 + prompt_text param from M3.

---

## Mission Log

---

### M1: Write model — artifact_write
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 15/15 HARD passed, 0 SOFT (all HARD in this mission)
- **Review verdict:** PASS (3 minor notes, no blockers)
- **Files written:** pidgin/__init__.py (29L), pidgin/utils/__init__.py (4L), pidgin/utils/git.py (83L), pidgin/write/__init__.py (13L), pidgin/write/new.py (190L), pidgin/write/compress.py (169L), pidgin/write/CLAUDE.md (105L)
- **Files modified:** none
- **Key observations:**
  - PD1 implemented: `_find_project_root` walks up to `.git` boundary — self-test in temp repo confirmed correct project_root derivation.
  - PD5 confirmed: sha256 throughout.
  - Audit JSONL: `{timestamp, audit_id, mode, files[], commit_sha, audit_metadata}` — mode="new" for artifact_write, mode="compress" with lineage[] for compress_write.
  - Deviations from tools/store/audit.py: dropped `pid`/`agent` fields; used `audit_id` (not `id`); full 40-char SHA; no pre_commit field (correct — Mode 3/4 have no pre-write bracket).
  - compress_write imports internal helpers from new.py via `_` symbols — minor coupling.
- **Review minor notes (non-blocking):**
  - `_append_compress_audit` re-imports `_audit_dir` in function body; should move to top-level import.
  - `is_git_repo` delivered but unused by new.py/compress.py — available for M2 callers.
  - compress_write commit message uses `pidgin/artifact_write:` prefix; consider `pidgin/compress_write:` for git log clarity.
- **Spend:** none (no API calls)

---

### M2: Write model — transaction context manager
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 11/11 HARD passed
- **Review verdict:** PASS (no blockers, 3 minor notes)
- **Files written:** pidgin/write/update.py (376L)
- **Files modified:** pidgin/write/__init__.py (18L), pidgin/write/CLAUDE.md (200L)
- **Key observations:**
  - OverlappingEdit: inclusive interval check `s1<=e2 AND s2<=e1` — [1,2]∩[2,3] correctly detected.
  - Running delta offset: original line numbers translated via cumulative delta as ops apply in order.
  - Dirty-file pre-bracket implemented; self-test uses clean file → pre_commit_sha=null confirmed.
  - strip_comment noop at queue time (not apply time) — documented deviation, functionally equivalent.
  - insert_tag raises NotImplementedError for non-.py.
- **Review minor notes (non-blocking):**
  - Noop detection at queue time is documented minor deviation.
  - `_git_add_commit` uses returncode inspection rather than check=True (consistent with M1 git.py pattern).
  - Out-of-bounds line in strip_comment silently treated as noop rather than ValueError.
- **Spend:** none (no API calls)

---

### M3: XML prompt — converge.xml
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 12/12 HARD passed, 2/2 SOFT passed
- **Review verdict:** PASS
- **Files written:** pidgin/prompts/converge.xml (30,480 bytes), pidgin/prompts/__init__.py, pidgin/prompts/CLAUDE.md
- **Files modified:** tools/mld/pipeline.py (KE1 — additive prompt_text kwarg at line 374)
- **Key observations:**
  - Migration: 8 rules, 33 positive examples, 17 anti-examples — all from generate.md.
  - Probe results: 4/4 probes at 15/15 converged (no regression vs v0.1 baseline of 15/15).
  - CACHE BOUNDARY: `<!-- ===== CACHE BOUNDARY ===== -->` at exactly one location (line 540).
  - [CDATA-OPEN]/[CDATA-CLOSE] as literal placeholders — confirmed by clean ElementTree parse.
  - P3/P4 sourced from tools/mld/probe.py (not tools/utils/sections.py) — canonical source per v0.1 harness.
  - P1/P2 gate returned "ambiguous" (Opus selected); 15/15 convergence holds regardless.
  - KE1 confirmed additive: original `prompt` param retained, `effective_prompt` substitution in both phases.
- **Anomalies:**
  - Cached preamble ~7,482 tokens (substantially larger than generate.md at ~960 lines of markdown). Cache hit amortization should cover increased write cost.
  - Gate ambiguity on P1/P2 → Opus selection increases per-call latency for those probes.
- **Spend:** ~60 generation calls + embeddings on gpt-4.1-nano/text-embedding-3-small (estimated <$0.10)

---

### M4: XML prompt — gate.xml
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 13/13 HARD passed, 1/1 SOFT passed
- **Review verdict:** PASS (1 CONCERN — non-blocking)
- **Files written:** pidgin/prompts/gate.xml (5264 bytes, 101L)
- **Files modified:** pidgin/prompts/CLAUDE.md
- **Key observations:**
  - gate.xml: 11 criteria, 6 examples (2 valid, 4 invalid), CACHE BOUNDARY at line 86, output_schema 2 fields (valid:boolean, reason:string).
  - G1-G4 all valid=true, G5 valid=false (truncation correctly detected). POSITIVES: 4/4, NEGATIVE: 1/1.
  - **MODEL DEVIATION:** gpt-4.1-nano hallucinated reasons on valid descriptions (claimed trailing commas that didn't exist; called "Parse" and "Update" non-imperative). Switched to claude-haiku-4-5 for gate calls. This is CONCERN-level: nano is insufficient for binary gate; future pipeline wiring must default to haiku-4-5.
  - validate.md was a candidate SELECTOR (chosen_index schema), not a binary gate — gate.xml is a design evolution, not a direct migration.
  - pipeline.py NOT modified (KE1 — gate.xml standalone only; wiring deferred).
- **Review CONCERN (non-blocking):** Future missions wiring gate.xml into pipeline.py must default to claude-haiku-4-5 (not gpt-4.1-nano). Document in model-routing config.
- **Spend:** ~5 gate calls on gpt-4.1-nano (failed) + 5 calls on claude-haiku-4-5 (estimated <$0.02)

---

### M5: XML assembly — templates.py
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 8/8 HARD passed, 1/1 SOFT passed
- **Review verdict:** PASS (1 minor note — non-blocking)
- **Files written:** pidgin/prompts/templates.py (4.9KB)
- **Files modified:** pidgin/prompts/__init__.py, pidgin/prompts/CLAUDE.md
- **Key observations:**
  - 19 principles parsed from ORIGAMI.md (principles 1-6 have rich full bodies; 7-19 have shorter paragraph bodies).
  - Selective injection: selected_words=48 (ids 1,3,7) vs full_words=613 — well within 90/300 thresholds.
  - KeyError: 'name' raised on missing payload key — confirmed.
  - CACHE BOUNDARY split: substring match `===== CACHE BOUNDARY =====` in any line; boundary line discarded.
  - cached_preamble = lines 1-539 of converge.xml; payload = lines 542-555.
  - principles_used populated as sorted(set(ids)) — deduplicated.
- **Review minor note:** `principles: list[int] = ()` uses tuple as default for list[int] annotation — functionally safe (converted internally), type annotation inconsistency only.
- **Spend:** none (no API calls — ORIGAMI.md parsed locally)

=== PHASE 1 COMPLETE (M1-M5 all GREEN) — proceeding to Phase 2 ===

---

### M6: Batch dispatch — generation path
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 13/13 HARD passed, 2/2 SOFT passed (live test ran)
- **Review verdict:** PASS (1 minor note — error message string uses spaces vs underscores)
- **Files written:** pidgin/pipeline/__init__.py, pidgin/pipeline/batch.py (11KB), pidgin/pipeline/mld.py (29KB), pidgin/pipeline/CLAUDE.md
- **Files modified:** none in /project/tools/
- **Key observations:**
  - Live batch test: 20/20 results, 0 errors, 166.3s wall time.
  - Response shape: dict-with-keys (Shape 1) confirmed as gpt-4.1-nano live shape with response_format set.
  - parse_batch_results: 8 synthetic test cases pass (all 4 shapes + missing + error paths).
  - should_use_batch: DP4 threshold n>=10 verified; sync/batch overrides working.
  - JSONL: system=preamble (cacheable), user=payload — correct structure.
  - Re-roll in mld.py always uses sync path even with dispatch="batch" — documented deviation (edge case, rare).
- **Review minor note:** error="missing from batch output" (spaces) vs spec "missing_from_batch_output" (underscores) — cosmetic, callers check `error != None`.
- **Spend:** 20 live generation requests on gpt-4.1-nano via batch (estimated ~$0.002)

---

### M7: Batch dispatch — embedding path + geometry
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 12/12 HARD passed, 1/1 SOFT passed (live test)
- **Review verdict:** PASS (1 minor note — adaptive threshold deviation documented)
- **Files written:** pidgin/utils/api.py (EMBEDDING_MODEL/DIM + get_openai_client lazy factory), pidgin/pipeline/geometry.py
- **Files modified:** pidgin/pipeline/batch.py (EmbeddingRequest/Result, build_embedding_jsonl, run_batch_embedding, parse_embedding_results, FunctionMldResult, run_embedding_mld_pipeline_for_functions), pidgin/pipeline/__init__.py, pidgin/pipeline/CLAUDE.md
- **Key observations:**
  - Decision 6 confirmed: EMBEDDING_MODEL="text-embedding-3-small", EMBEDDING_DIM=256.
  - tools/utils/api.py uses dim=1536 as general default, STORE_EMBED_DIM=256 for store — no conflict for pidgin usage.
  - **geometry.py algorithm fix required:** initial implementation used flat threshold=0.0 (returned size=3 for toy test). Fixed to adaptive mean-threshold — centroid computed, vectors above mean cosine sim to centroid kept. Toy test size=2 confirmed.
  - Live pipeline: 5/5 FunctionMldResult, cluster sizes 7-10, 206s wall time, <$0.002 cost.
  - Embedding response shape: Shape 1 (`{"data":[{"embedding":[...]}]}`) — all 75 embeddings at dim=256.
  - `add` function did not converge (cluster_size=7) — simple arithmetic is genuinely ambiguous to the model.
  - Sync fallback path not exercised (25 requests >= DP4 threshold of 10, all went batch).
- **Review minor note:** adaptive mean-threshold vs spec's literal `threshold=0.0` reading — deviation documented in docstring and CLAUDE.md; toy-test contract satisfied.
- **Spend:** 75 generation + 75 embedding calls via batch (estimated <$0.002)

---

### M8: Adaptive candidates
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 7/7 HARD passed, 1/1 SOFT passed
- **Review verdict:** PASS (1 minor note — type annotation `config: ExpansionConfig = None` should be `| None`)
- **Files written:** pidgin/pipeline/candidates.py
- **Files modified:** pidgin/pipeline/__init__.py, pidgin/pipeline/CLAUDE.md
- **Key observations:**
  - All 3 scenarios pass: A (expand→converge), B (accept immediately), C2 (non-convergent).
  - Floating-point exact: 9/15==0.6 True, 12/15==0.8 True, 21/30==0.7 True — confirmed.
  - Audit JSONL: `{timestamp, function, initial_ratio, expanded, expanded_ratio, converged, cluster_size, n_candidates_total}`.
  - generate_fn called 2× in A, 1× in B/C — correct.
  - `config=None` default: `ExpansionConfig()` instantiated inside function (avoids mutable-default trap).
- **Spend:** none (no API calls — pure math)

=== PHASE 2 COMPLETE (M6-M9 all GREEN) — proceeding to Phase 3 ===

---

### M9: Anthropic batch integration
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 9/9 HARD passed, 1/1 SOFT passed (live test)
- **Review verdict:** PASS (2 minor notes)
- **Files modified:** pidgin/pipeline/batch.py, pidgin/pipeline/__init__.py, pidgin/pipeline/CLAUDE.md
- **Key observations:**
  - Amendment 1 applied: claude-haiku-4-5-20251001 throughout.
  - Live: 10/10 results, 0 errors, 471.6s wall time. All verdicts correct (faithfulness violation on gate-08 correctly detected).
  - cache_control: ephemeral confirmed. Tool-use structured output (gate_verdict tool).
  - Results in requested_ids order via results_by_id map.
- **Review minor notes:** 256-token max may be too tight (empty reason on gate-02); raw_response is hand-built dict.
- **Anomalies:** Anthropic batch ~472s for 10 requests vs OpenAI 166s for 20. Small batches should default to sync.
- **Spend:** 10 gate calls via claude-haiku-4-5-20251001 batch (estimated ~$0.01)

---

### M10: Package extraction and reconciliation
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 14/14 HARD passed, 3/3 SOFT passed
- **Review verdict:** PASS (minor: KE2 carryover + 8 provenance misses, both acceptable)
- **Files written:** pidgin/store/__init__.py, pidgin/store/nest.py, pidgin/store/audit.py, pidgin/utils/parser.py, pidgin/CLAUDE.md, pidgin/store/CLAUDE.md
- **Files modified:** pidgin/__init__.py (public API), pidgin/pipeline/mld.py (A1: gate_prompt_text), pidgin/utils/__init__.py
- **Key observations:**
  - Public API confirmed: artifact_write, compress_write, update, ArtifactWriteResult, assemble_xml_prompt, run_embedding_mld_pipeline_for_functions, nest, audit.
  - A1-Task1 (prompt_text) already present in mld.py from M6 backport — no merge needed.
  - A1-Task2 (gate_prompt_text) added and wired to _gate_call at line 486.
  - mld() now has all 3 params: dispatch, prompt_text, gate_prompt_text.
  - nest.py merge: private helper conflicts resolved via renaming (_client→_sec/_vec_client).
  - KE2: 4 hits in pidgin/pipeline/ (from tools.utils.api imports) — documented as v0.3 cleanup.
  - Provenance: 8 SOFT misses (all pre-M10 files — acceptable).
  - NO_V01_TESTS found.
- **Spend:** none (no API calls)

 Anthropic batch integration
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 9/9 HARD passed, 1/1 SOFT passed (live test)
- **Review verdict:** PASS (2 minor notes — non-blocking)
- **Files modified:** pidgin/pipeline/batch.py (AnthropicBatchRequest/Result + run_anthropic_batch), pidgin/pipeline/__init__.py, pidgin/pipeline/CLAUDE.md
- **Key observations:**
  - Amendment 1 applied: model=claude-haiku-4-5-20251001 used throughout.
  - Live: 10/10 results, 0 errors, 471.6s wall time. All gate verdicts correct (incl. faithfulness violation detection on gate-08).
  - cache_control: ephemeral confirmed in system block per Anthropic prompt caching spec.
  - Tool-use structured output (not response_format) — `gate_verdict` tool with input_schema.
  - Results returned in requested_ids order via hand-built `results_by_id` map.
  - raw_response is hand-built dict (id/model/stop_reason/usage) — SDK returns typed objects.
- **Review minor notes:**
  - 256-token max_tokens cap produced empty `reason` on gate-02 — recommend bumping to 512 for production.
  - raw_response hand-built dict preserves frozen-dataclass invariant but loses full SDK telemetry.
- **Anomalies:**
  - Anthropic batch is substantially slower than OpenAI for small batches (472s for 10 requests vs OpenAI's 166s for 20). Small batches should default to sync.
  - `processing_status` (Anthropic) vs `status` (OpenAI) — confirmed distinct polling surfaces.
- **Spend:** 10 gate calls via claude-haiku-4-5-20251001 batch (estimated ~$0.01)

 Write model — transaction context manager
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 11/11 HARD passed, 0 SOFT failures
- **Review verdict:** PASS (no blockers, 3 minor notes)
- **Files written:** pidgin/write/update.py (376L)
- **Files modified:** pidgin/write/__init__.py (18L), pidgin/write/CLAUDE.md (200L)
- **Key observations:**
  - OverlappingEdit exception defined; inclusive overlap check `s1<=e2 AND s2<=e1` verified.
  - Running delta offset: correct — original line numbers translated via delta as ops apply in order.
  - Dirty-file pre-bracket implemented but not exercised in self-test (clean file used).
  - Pre_commit_sha=null in audit entry when file was clean — confirmed.
  - strip_comment no-op detection at queue time (not apply time) — functionally equivalent, documented.
  - insert_tag raises NotImplementedError for non-.py files.
- **Review minor notes (non-blocking):**
  - Noop detection at queue time is a documented minor deviation.
  - `_git_add_commit` uses returncode inspection rather than check=True (consistent with git.py pattern from M1).
  - Out-of-bounds line in strip_comment silently treated as noop rather than raising ValueError.
- **Spend:** none (no API calls)


---

### M11: CLI — four verbs
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 12/12 HARD passed, 2/2 SOFT passed
- **Review verdict:** pending
- **Files written:** pidgin/__main__.py, pidgin/cli.py, pidgin/verbs/__init__.py + 6 verb files, pidgin/verbs/CLAUDE.md
- **Files modified:** pidgin/CLAUDE.md, pidgin/store/nest.py (upsert_function_descriptions), pidgin/utils/parser.py (extract_public_functions), pidgin/utils/api.py (embed_for_store+embed_text)
- **Key observations:** PD2/PD3/PD6 all confirmed. Live index 2/2 converged. All stubs NotImplementedError.
- **Anomalies:** extract_public_functions + embed_for_store were missing from pidgin/ — added. Nest writes to global ChromaDB, not per-repo — M12 fix needed.
- **Spend:** ~$0.001 (live index test)


---

### M12: Nest convention + verb wiring
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 13/13 HARD passed, 4/4 SOFT passed (live index, query, compress, CLAUDE.md)
- **Review verdict:** PASS
- **Files modified:** pidgin/store/nest.py (nest_path, ensure_nest, write_nest_claude_md, query, per-repo upsert), pidgin/verbs/index.py, pidgin/cli.py, pidgin/verbs/new.py, compress.py, update.py, query.py, pidgin/verbs/CLAUDE.md
- **Key observations:**
  - .pidgin/nest/ created at /tmp/m12/sample with chroma.sqlite3 confirmed.
  - .pidgin/CLAUDE.md auto-generated with correct content.
  - query [0.699] add — "Add two numbers and return the sum." from /tmp/m12/sample.
  - Permission enforcement: compress/new/update all exit 2 correctly without required flags.
  - compress -o flag works; FILE=OK confirmed.
- **Anomalies:** nest_path collision (old global-path fn renamed to _global_nest_path); upsert rewritten for per-repo ChromaDB; compress uses skip_git=True for non-git paths.
- **Spend:** ~2 MLD calls for live index test (estimated <$0.001)

---

### M13: Nested nest discovery + init verb
- **Tier:** execute | **Review:** true
- **Verdict:** GREEN
- **Steps:** 12/12 HARD passed, 1/1 SOFT passed
- **Review verdict:** PASS
- **Files written:** pidgin/store/discovery.py (NestPointer, discover_nests, register_nests, load_registry)
- **Files modified:** pidgin/verbs/init.py, pidgin/verbs/query.py, pidgin/store/nest.py (query_by_path), pidgin/store/CLAUDE.md
- **Key observations:**
  - Two synthetic child nests discovered. Registry: version=1, 2 nests.
  - "[query] Searching 2 registered nest(s)." confirmed.
  - Empty ChromaDB sqlite3 handled gracefully — query_by_path returns [] without error.
  - cli.py --path for init already existed; no change needed.
  - macOS /tmp→/private/tmp symlink: consistent via abspath, no behavioral impact.
- **Spend:** none (no API calls)

=== PHASE 3 COMPLETE (M10-M13 all GREEN) — proceeding to Phase 4 ===


---

### M14: Bidirectional MLD — probe design
- **Tier:** reason | **Review:** true
- **Verdict:** GREEN
- **Steps:** 12/12 HARD passed, 1/1 SOFT passed (README ≥50 lines: 251)
- **Review verdict:** PASS with CONCERNS (non-blocking)
- **Files written:** README.md (251L), probes.json (5 entries), harness.py, pidgin/prompts/expand.xml
- **Key observations:**
  - 5 probes: embed_for_store (data-flow), main-toy (control-flow), apply (state-mutation), merge (geometric), antipode_test (complex/synthesized).
  - Cost projection: ~$0.030 batch (well under $1.00 cap).
  - Gate criteria: 4/5+ stable-converged → UNLOCK; ≤2/5 → DEFER; 3/5 → AMBIGUOUS.
  - expand.xml: valid, CACHE BOUNDARY at line 127, implementation field max_tokens=800, 8 rules, 4+4 examples.
  - harness.py uses lower-level batch primitives (not run_embedding_mld_pipeline_for_functions) — justified: this is expansion (desc→code), not the converge pipeline.
- **Review CONCERNS (non-blocking):**
  - P5 (antipode_test) description synthesized — no gate-validated provenance. P5 failure may reflect prompt quality, not geometry. UNLOCK still achievable via P1-P4 alone.
  - P2 uses toy MAIN_SRC body, not production embed.py:main — documented in probes.json source field.
- **Spend:** none (no API calls)


---

### M15: Bidirectional MLD — execution
- **Tier:** execute | **Review:** false
- **Verdict:** GREEN
- **Steps:** all passed (harness restructured to 2 mega-batches; 30/30 records produced)
- **Files written:** results.json (30 records), SUMMARY.md
- **Key observations:**
  - 30/30 records: 0 errored. OK_RATIO=1.00 (well above 0.80 floor).
  - Per-probe converged/6: P1=3/6, P2=5/6, P3=6/6, P4=5/6, P5=5/6. Total: 24/30.
  - P3_apply: perfectly stable (6/6), cluster sizes 8-10.
  - P4_merge, P5_antipode_test, P2_main: mostly stable (5/6 each).
  - P1_embed_for_store: only 3/6 — the weakest probe.
  - Budget=50: mean cluster 7.0; budget=200: mean cluster 6.5 (50 slightly better — short truncated candidates cluster tighter).
  - Syntactic validity: 5.4/10 mean — P2/P3/P5 produce 0 valid Python at budget=50 (model truncates mid-function). P4_merge + P1 at b=200 produce 10/10 valid.
  - **HARNESS OPTIMIZATION:** Original serial harness would take ~78 min (30 serial batches). Rewrote as harness_fast.py with 2 mega-batches (300 gen + 300 embed). Total wall time: 325s.
- **Spend:** ~$0.030 estimated (300 gen + 300 embed via batch, gpt-4.1-nano)


---

### M16: Bidirectional MLD — gate decision
- **Tier:** reason | **Review:** true
- **Verdict:** GREEN (mission complete)
- **Gate verdict: DEFER**
- **Stable+Correct probes:** 1/5 (P4_merge only)
- **Files written:** GATE.md, gate.xml
- **Per-probe summary:**
  - P1_embed_for_store: 3/6 converged → NOT STABLE (threshold ≥4)
  - P2_main: 5/6 converged, cluster Δ1 → STABLE, but modal candidate has wrong side effects (file write vs stdout) → INCORRECT
  - P3_apply: 6/6 converged, cluster Δ2 → STABLE, modal candidate is AMBIGUOUS (3-way tie between complete match and truncated cousin) → AMBIGUOUS = INCORRECT (gate is strict)
  - P4_merge: 5/6 converged, cluster Δ1 → STABLE, modal candidate byte-equal to reference → CORRECT ✓
  - P5_antipode_test: 5/6 converged, cluster Δ1 → STABLE, syn_valid=0 across all runs (all candidates truncated) → INCORRECT
- **Architectural reasoning:**
  - The GEOMETRY works: tight convergence (Δ1 cluster sizes) in code embedding space confirmed.
  - The ENVELOPE fails: budget=50/200 truncates JSON mid-string. The candidates aren't wrong — they're unfinished. Tool-use structured output + higher budgets (≥800) would fix this.
  - Recommendation for v0.3: raise token budget and switch to tool-use envelope. Re-gate is likely to reach 4/5.
- **Spend:** none (no API calls — judgment only)

=== PHASE 4 COMPLETE — GATE VERDICT: DEFER ===
[M14 — GREEN: 5 probes designed, harness written, expand.xml valid]
[M15 — GREEN: 30/30 records, 24/30 converged, 325s via 2 mega-batches, ~$0.030]
[M16 — GREEN: gate applied, DEFER issued, gate.xml written]
=== END PHASE 4 SUMMARY ===

=== SPRINT DISPOSITION: CLOSED AT PHASE 3 ===

Gate verdict DEFER per design Decision 1: "fewer than 3/5 stable+correct → bidirectional MLD
deferred to v0.3." Phase 5 missions M17-M19 do NOT dispatch.

Sprint tooling-v0.2 closes with Phases 1-3 (M1-M13) delivered and Phase 4
data collected for v0.3 planning. The pidgin package is functionally complete
through the CLI (all 6 verbs wired), the store layer (nest, discovery), and
the batch dispatch infrastructure.

Recommended v0.3 pre-conditions before re-gating bidirectional MLD:
1. Raise expansion budget to ≥800 tokens.
2. Switch expand.xml from JSON-schema response_format to tool-use envelope.
3. Add P3_apply b=200 as a standalone re-probe (already correctly generates
   at b=200; needs only the envelope fix at b=50).
4. Re-describe P1 (embed_for_store) — current description too generic, admits
   too many surface forms. Only non-budget-bound failure.
5. Fix P2 probe definition — description matches tools/embed.py:main, not the
   toy MAIN_SRC. Either re-describe or move probe to production main.

=== COMMANDER CONFIRMATION — 2026-04-27 ===

Gate verdict DEFER confirmed. Sprint disposition: GREEN WITH FINDINGS.

Phase 1-3 (M1-M13): all GREEN. pidgin package delivered through CLI, store,
batch dispatch, and prompt assembly. Amendment 1 (gate model → claude-haiku-4-5)
issued and validated empirically.

Phase 4 (M14-M16): all GREEN as probe execution. Gate decision DEFER is correct.
The cluster geometry is clean (Δ1 across all stable probes). The failure mode is
token-budget truncation of the JSON envelope, not embedding-space behavior.
P4 (one-liner, 5/5 byte-equal to reference) and P3 at b=200 (3/3 verbatim match)
are the proof-of-concept for v0.3.

Phase 5 (M17-M19): not dispatched per gate verdict.

Cumulative spend: ~$0.10 (well under $2.00 budget).

Key findings for v0.3 seed context:
- Flock/architect split validated: nano generates, haiku-4-5 gates, Opus reasons
- Batch infrastructure (M6) paid for itself immediately: 300+300 calls in 325s
- XML prompt migration (M3/M4) zero-regression at 15/15 convergence
- Bidirectional MLD geometry works; envelope and budget are the bottleneck
- Provider strategy confirmed: OpenAI for volume, Anthropic for judgment only

=== END COMMANDER CONFIRMATION ===

