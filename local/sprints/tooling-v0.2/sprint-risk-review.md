# Sprint Risk Review — tooling-v0.2

**Reviewer:** claude-opus-4-7 (fresh instance)
**Date:** 2026-04-27 09:58
**Plan reviewed:** sprint.xml

---

## M1: Write model — artifact_write

### Blockers
- Step 12 self-test calls `artifact_write(files, {"mission": "M1-selftest"})` with files outside `/project`, but the spec says paths must be "under project_root" and the function defaults audit to `/project/.pidgin/audit/`. The test comment admits this — "executor: adapt and document" — meaning the spec is incomplete. Either `project_root` must be a kwarg from the start, or the function must derive root by walking up to `.git`. Pre-decide before dispatch.
- Step 12's self-test asserts the audit JSONL lives at `<d>/.pidgin/audit/artifact_write.jsonl` (under the temp dir), but the spec text hard-codes `/project/.pidgin/audit/artifact_write.jsonl`. Contradiction.

### Fragile Steps
- Step 1: `cp -r /project/tools/store /tmp/m1/store_backup 2>/dev/null || true` — silently succeeds even if tools/store doesn't exist. The "rollback" depends on this backup; rollback restoration of tools/store is meaningless if the cp failed silently.
- Step 12: depends on `git config user.email/user.name` succeeding; if executor's git is configured globally with conflicting hooks (signing, pre-commit), the commit fails and the test reports a non-deterministic error.
- Atomic write via `os.replace` will EXDEV on cross-filesystem temp paths (already noted in risk register but not mitigated).

### Underspecified
- Hash algorithm: spec says "sha256" but report asks "blake2?" — pre-decide sha256.
- `commit_message` default ("derived from audit_metadata") — derivation rule undefined.
- What happens if `/project` isn't a git repo and `skip_git=False`? Implicit failure mode.
- Audit JSONL line ordering when concurrent calls happen (none expected in v0.2 but worth noting).

### Cross-Mission
- M2 imports `OverlappingEdit` from `pidgin.write` (Step 5), which M2 itself defines. Fine, but M2's `__init__.py` edit must not clobber M1's exports.
- M10's "tools/store/audit.py extracted" depends on M1 having taken only the artifact_write path; M2 takes the transaction path; what's left for M10 to extract? Verify nothing falls between the cracks.

---

## M2: Write model — transaction context manager

### Blockers
- Step 9 imports `OverlappingEdit` from `pidgin.write` but M2 Step 5 only adds it to `__init__.py` after Step 4 writes update.py. Step 5 must run before Step 9 — verify executor doesn't reorder.
- Spec says `replace(line_start, line_end, content)` line numbers refer to **original** file pre-edit, but the implementation must "compute a running line offset to translate." If two `replace` ops both target line 5 in the original, what's the semantics? Spec says "overlapping ranges → OverlappingEdit" but two ops on the *same* line aren't overlapping by interval logic — they're both [5,5]. Pre-decide whether `[5,5]` and `[5,5]` raise.

### Fragile Steps
- Step 9's overlap test uses ranges `[1,2]` and `[2,3]`. These share endpoint 2. Whether "overlap" means `start_a <= end_b AND start_b <= end_a` (inclusive) or strict overlap matters; spec says "overlapping ranges" without defining. The test will pass or fail based on the implementer's choice of inequality.
- `git status --porcelain -- <path>` on a path that doesn't exist yet (pre-create test) returns empty (not dirty), so the dirty-check code path may not run on the test. Spec says Update is for files with content — implicitly assumes file exists.
- Strip_comment on `# line 5` deletes whole physical line — line-offset bookkeeping for downstream ops becomes important; spec doesn't say whether subsequent op line numbers shift.

### Underspecified
- `insert_tag` for non-`.py` raises NotImplementedError. M3-M19 generate XML files, so this is fine, but M19's pass-4 review writes `<validation>` content — if any update path touches XML, it breaks. Verify M18/M19 don't call `update()` on .xml files.
- "pre-bracket snapshot" message format is fixed ("pidgin/update: pre-bracket snapshot of <relpath>") — relpath relative to what? project_root or cwd?
- Exception path leaves "stranded commits" — by design — but no mechanism to clean them up. Operators must know.

### Cross-Mission
- M11's `update` verb (filled in M12) calls into Transaction. M12 spec says "interactive mode without --edits-file is out of scope; raise a clear error" — verify M12 doesn't expect a method M2 doesn't expose.

---

## M3: XML prompt — converge.xml

### Blockers
- Spec Step 10 references `tools/mld/pipeline.py` and says "if it currently hardcodes generate.md, add a one-line parameter `prompt_text: str | None = None`". This is a **behavior change to v0.1 code** during Phase 1, which violates Constraint: "No behavior changes to validated v0.1 pipeline code during Phase 1-3 extraction." Either the constraint is relaxed or this approach is wrong.
- The file `local/sprints/tooling-v0.1/context/v2-mld-validation.md` is referenced as the v0.1 baseline source but its existence is not pre-verified. Step 4 SOFT-fails if missing — but the entire mission's "regression vs baseline" claim relies on it.
- Spec mentions `[CDATA-OPEN]` and `[CDATA-CLOSE]` as placeholders for `<![CDATA[ ... ]]>` — Step 7 parses with ElementTree which will choke on the literal placeholder strings or treat them as plain text. The template format is itself broken until M5's templates.py substitutes them — but M3's Step 7 happens before M5. Verify the template parses standalone.

### Fragile Steps
- Step 9's grep `'rules:'` and `'examples:'` etc. counts elements via XPath — but `findall('rules/rule')` won't find anything if the XML has the `[CDATA-OPEN]` placeholder unsubstituted (the XML may not parse).
- Step 11 expects `converged=` in the log but the script format isn't fully prescribed; "PROBES_PASSED" regex assumes exact format.
- Step 12 threshold is 8/15 (~53%) — this differs from M8's 0.6 expand_ratio rule (9/15). Inconsistency.

### Underspecified
- Where exactly is the `prompt_text` parameter wired into the v0.1 pipeline call chain? Pipeline → API call → request building. Multiple potential injection points.
- Anti-example carryover: "at least one anti-example carried from generate.md" — but if generate.md has 5 anti-examples, do all migrate or just one?
- The CACHE BOUNDARY marker is `<!-- ===== CACHE BOUNDARY ===== -->` exactly — Step 8 greps for `===== CACHE BOUNDARY =====` (no comment markers) — both work but a typo in the comment delimiters silently fails M5's split.

### Cross-Mission
- M5 splits on the literal CACHE BOUNDARY comment. If M3 or M4 author the marker even slightly differently (extra space, different = count), M5's split returns the whole string as cached_preamble.
- M14 references converge.xml; expand.xml mirrors its structure. Any structural choice here propagates.

---

## M4: XML prompt — gate.xml

### Blockers
- Step 9 "run gate via the existing v0.1 gate API path with gate.xml swapped in" — same issue as M3: requires modifying v0.1 code, violating Phase 1-3 constraint. Path of injection unspecified.
- Test cases G1-G4 require "v0.1 converged descriptions for embed_for_store, main, apply, merge". Source: "v2-mld-validation.md or M3 fallback". Step assumes M3 wrote artifacts to a known path — verify M3's probe output format matches what M4 expects to read.

### Fragile Steps
- Step 11's regex `r'G[1-4] verdict=true'` requires the script in Step 9 to print exactly that format. If the script prints `G1 verdict=True` (capital T from Python's bool), the count is 0/4. Pre-decide stringification.
- Truncated candidate "Merge delta into a copy of state," — model may judge this `valid` if asked too leniently. Hard-coding G5 to expect `false` makes M4 fail-loud on a model behavior.

### Underspecified
- The response_format json_schema for the gate — does v0.1's gate code use json_schema or json_object? If json_object, M4 needs to wire schema-strict mode into the call site.
- "Strict" attribute in `<output_schema strict="true">` — XML attribute, not OpenAI's `strict: true`. Confusing.

### Cross-Mission
- M9 batches gate calls. M4 establishes the gate's response_format. M9 must match exactly or batched gates parse differently than sync gates.

---

## M5: XML assembly

### Blockers
- Spec says ORIGAMI.md is read from `/project/ORIGAMI.md`. The file's existence is not pre-verified. v0.1 ran M14 producing ORIGAMI.md, but plan doesn't assert it's still present at `/project/ORIGAMI.md` (vs `/project/local/sprints/tooling-v0.1/...`). Step 1's `cp 2>/dev/null || echo MISSING` allows missing — then registry is empty, then full-bodies test in Step 7 silently degrades to "PRINCIPLE_WORDS selected=0 full=0 (empty registry)" — which the test treats as PASS.
- Test in Step 8 calls `assemble_xml_prompt('/project/pidgin/prompts/converge.xml', {'file': 'x'}, principles=[])` — `payload_vars` dict missing required keys (`name`, `line_start`, `function_body`) — expecting KeyError. But `principles=[]` may cause `<principles>` block replacement to be a no-op, then placeholder substitution proceeds, raises KeyError on first missing. Fine. But if implementer substitutes principles AFTER payload, KeyError may fire on the principle template before reaching payload — different failure path.

### Fragile Steps
- The `<principles>` block replacement: "find the `<principles>` block, replace its INNER content." Regex-based or DOM-based? Spec says "Read the template as TEXT (not parsed XML)." Text-based regex on `<principles>...</principles>` will fail if any `<principle>` placeholder text contains the closing tag string.
- "Find the literal `<!-- ===== CACHE BOUNDARY ===== -->` marker." If M3 wrote the marker with surrounding whitespace or different spacing, split yields wrong halves.
- Word-count proxy `len(text.split())` for token estimation — fine for sanity, but the assertion `selected_words <= 90` may fail if MLD descriptions are slightly verbose.

### Underspecified
- ORIGAMI.md format: "numbered list with each principle as header + body. Locate the MLD-compressed line (typically the first sentence)." This is a regex parsing job on a document not under spec control. What if Origami uses a different format (e.g., tables)?
- `Principle.full` storage — where does the full body come from if ORIGAMI.md is the MLD'd version? Probably None for all entries, making the comparative test in Step 7 a no-op.

### Cross-Mission
- M3 and M4 created the templates with placeholders; M5's substitution rules must match the exact placeholder syntax (`{{key}}`). If M3 used `{key}` instead, M5 silently fails to substitute.

---

## M6: Batch dispatch — generation path

### Blockers
- Spec says "system message gets cached preamble (cacheable)" but **OpenAI's prompt cache requires identical prefix in messages array AND the model supports caching**. gpt-4.1-nano caching eligibility on `/v1/chat/completions` batch endpoint is not verified in the plan. The cost projections in batch-dispatch.md depend on cache hits — if batch endpoint doesn't cache system messages identically to sync, projections are wrong.
- Step 12 live test depends on `OPENAI_API_KEY`. If unset, marked SOFT — meaning the entire batch path is verified only structurally. Real batch behavior (24h completion window, file size limits, JSONL parse quirks) goes untested.

### Fragile Steps
- `parse_batch_results` accepts FOUR response shapes. This is parser laxity that will mask drift between sync and batch behavior — both should produce identical shapes if the prompt is identical.
- Polling loop with `timeout_seconds=1800` (30 min) but `completion_window="24h"` — if a batch takes > 30 min the polling errors out while the batch keeps running, leaking work.
- Step 9's JSONL test asserts `body.messages[0].role == 'system'` — but OpenAI batch JSONL format requires the body to match the sync chat completions request exactly. If the implementer puts the preamble in `body.system` (Anthropic-style) by mistake, OpenAI rejects it.

### Underspecified
- `custom_id` format: spec example shows `"embed_for_store:call=2:draft=N/A"` but the embedding step (M7) uses `"embed_for_store:call=2:cand=1"`. Two different schemes — M7's needs to map back to M6's. Pre-decide a coherent custom_id grammar.
- Error file handling: "Errored entries appear in `error_file_id`" — file path or downloadable file_id? OpenAI returns file_id; spec is ambiguous.
- "BytesIO(jsonl)" in spec — OpenAI Files API expects bytes. JSONL string must be encoded.

### Cross-Mission
- M7 reuses run_batch_generation pattern but for embeddings. If M6 chooses a polling abstraction that's hard to reuse, M7 duplicates code.
- M9 reuses for Anthropic. Spec for M9 already says "keep two parallel implementations" — fine.
- M11's `index` verb dispatches via auto-threshold — small repos go sync, big batch. Verify M6's sync path is unchanged from v0.1.

---

## M7: Batch dispatch — embedding path

### Blockers
- Step 7 asserts `EMBEDDING_DIM == 256`. v0.1's `tools/utils/api.py` may already declare a different value. Step 3 audits ("grep -rE 'dimensions=...'") — SOFT fail. So M7 may install constants that conflict with live v0.1 calls still in `/project/tools/`. The Decision 6 audit is policy-only.
- `get_openai_client()` factory — if `tools/utils/api.py` already constructs a client at import time (not lazy), pidgin's factory and the v0.1 module both create clients with potentially different configs. State drift.
- `run_embedding_mld_pipeline_for_functions` is the load-bearing helper for M11's `index` verb. Its sync fallback path requires the v0.1 sync pipeline. If M6 didn't preserve sync (M6 spec says "synchronous path is preserved unchanged" — verify).

### Fragile Steps
- `antipode_test` default threshold 0.0 — risk register flags this. v0.1's actual threshold likely differs (0.7-0.9 range). Step 9 tests with 3D toy vectors where 0.0 works; real 256-dim embeddings will cluster differently.
- `parse_embedding_results` four-shape fallback — same masking concern as M6.
- Step 11's live test "treat live failures as architect-review, not RED" — means M7 ships unverified end-to-end.

### Underspecified
- The "extracted from probe.py" — v0.1 may keep antipode_test in `tools/utils/sections.py` per M10's inventory. Locate explicitly.
- `should_use_batch` integration in `run_embedding_mld_pipeline_for_functions` — embedding count is 15× function count; auto-threshold may flip to batch for 1 function (15 candidates) which is wasteful. Pre-decide whether threshold applies per-function or per-call-volume.

### Cross-Mission
- M8's `cluster_fn` callable signature — M7 ships `antipode_test` returning `(size, indices)`. M8's spec shows `cluster_fn` returning just `size`. Adapter required; M8's tests inline simple cluster functions, dodging the issue, but real callers need the adapter.

---

## M8: Adaptive candidates

### Blockers
- Threshold math is brittle: `expand_ratio=0.6, accept_ratio=0.8`. Initial cluster 9/15 = 0.6 exactly. Strict `>=` means 9/15 triggers expansion (correct per spec) but 12/15 = 0.8 exactly → accept. Floating-point: 9/15 in Python is 0.6 exactly (no float error), 12/15 = 0.8 exactly. Safe. But arbitrary cluster sizes may not be exact (e.g., 11/15 = 0.733...). Test scenario A relies on 9/15 == 0.6 — verify Python evaluates this as ≥ 0.6 strict.
- Test Scenario A: "9/15 = 0.6 == expand_ratio" — `0.6 >= 0.6` is True, so expand triggers. Then 21/30 = 0.7 == expanded_accept_ratio, `0.7 >= 0.7` True, converges. **But 21/30 = 0.7 in Python is 0.7 exactly?** `21/30 == 0.7` → True. OK. But the test counts cluster as 9 (initial) + 12 (expansion) = 21, on a 30-vector cluster_fn that selects v[0] > 0.5. Audit: does cluster_fn re-cluster the union or just count? Test uses union counting; cluster_fn applied to `vecs_initial + vecs_more` with the simple `v[0] > 0.5` — yes, returns 21. Fragile but works.

### Fragile Steps
- Test Scenario B's intent ("4/5 → no expansion") uses 12/15 = 0.8 = accept_ratio exactly. Whether this triggers accept or expansion depends on `>=` strict. Spec says `ratio_initial >= accept_ratio: accept`. 0.8 >= 0.8 → True → accept. OK.
- Scenario C's first attempt is wrong (the test has `pass` and re-tries with C2). Confusing test code; executor may copy the broken first version.

### Underspecified
- Configurability: spec says thresholds are configurable but exposes them only via dataclass construction. No env var, no config file. Fine for v0.2.
- audit_path default `/project/.pidgin/audit/convergence.jsonl` — directory may not exist; spec for M1 said "audit dir created on first write" but M1's audit dir was `artifact_write.jsonl` not `convergence.jsonl`. Pre-decide whether each audit module bootstraps its own subdir.

### Cross-Mission
- `evaluate_with_expansion` is called by... no one? M11's index verb calls `run_embedding_mld_pipeline_for_functions` which doesn't seem to use expansion. Verify whether M8's logic is wired into the index path or is standalone for now.

---

## M9: Anthropic batch integration

### Blockers
- Step 3 requires `anthropic` Python SDK installed. If not present, HARD fail — but no install step. Pre-flight check needed.
- Spec uses model name `"claude-haiku-4-5-20251001"` — verify this model exists at execution time. Anthropic versioning churns; the design's "ground truth" doesn't pin model versions for Anthropic.
- `client.messages.batches.create(...)` — Anthropic SDK API surface for batches has evolved. Recent SDK versions may use different method paths. Pre-flight: verify SDK version compatibility.

### Fragile Steps
- "Stream results via `client.messages.batches.results(batch_id)`" — generator vs list, SDK-version dependent.
- Cache control with ephemeral type — works on Anthropic batch endpoint? Anthropic's prompt cache documentation distinguishes batch vs non-batch. Verify.

### Underspecified
- Synchronous fallback: "callers route through existing v0.1 synchronous Anthropic path" — but does v0.1 have one? v0.1 used Anthropic for gate and selection. Locate; M10 may need to extract.
- max_tokens default 256 for gate — if model emits structured output with reason, 256 may be plenty, but if reason is empty and model emits `{"valid": true, "reason": ""}`, fine.

### Cross-Mission
- M11/M12's gate calls — do they go through M9 or stay sync? Plan doesn't wire them. Verify the gate dispatcher uses M9 for batch threshold.

---

## M10: Package extraction

### Blockers
- Step 12's sed `s/from tools\./from pidgin./g` is a flat rewrite. But the inventory shows partial extractions: `tools/utils/sections.py → pidgin/pipeline/geometry.py + audit?`. A test file importing `from tools.utils.sections import antipode_test` would rewrite to `from pidgin.utils.sections import antipode_test` which doesn't exist — geometry.py is the new location. Sed-based migration is wrong for partial moves.
- "Move tools/store/sections_chroma.py + tools/store/vectors.py → pidgin/store/nest.py (merged)" — if these files have conflicting function names, the merge silently overwrites. No conflict-detection in plan.
- v0.1 source NOT deleted — creates dual import paths. Any v0.1 code (or test) still importing from `tools.X` continues to use the old path, masking the migration. Plan acknowledges this as a v0.3 concern.

### Fragile Steps
- Step 10's provenance audit grep'ing first 600 chars for `pidgin v0.2`. If a Python file leads with a long docstring or `__future__` imports, the marker may slip past 600 chars.
- Step 12's `sed -i.bak` creates `.bak` files inside `pidgin/tests/` — may pollute test discovery (`*.py.bak` ignored by pytest, fine).
- Public API in `__init__.py`: `from .write import update` — but `update` is both a module name (`pidgin/write/update.py`) and a function (`pidgin.write.update`). Naming collision. Possibly fine if `__init__.py` re-exports cleanly, but `from pidgin.write import update` could resolve to either.

### Underspecified
- `nest.upsert_function_descriptions` — created in M10 or M11? M11 spec says "if absent, add it here." M10 may or may not include it. Pre-decide.
- Test directory existence — design says "all existing v0.1 tests pass against the new import paths." If no tests exist, success criterion #4 (M10 inventory passes tests) is vacuous. The plan acknowledges via "NO_V01_TESTS" branch but the original design's claim is then unmet.

### Cross-Mission
- M11's `index` verb imports `from pidgin.utils.parser import extract_public_functions`. M10 must move `parser.py`. If parser's function is named differently in v0.1 (`extract_functions` vs `extract_public_functions`), M11 import fails.
- M12 imports `nest_path`, `ensure_nest`, etc. — these are defined in M12, not M10. M10's nest.py must allow extension without breakage.

---

## M11: CLI — four verbs

### Blockers
- `argparse` with global flags (`--write-db`, etc.) before the subcommand: `pidgin --write-db index .` works; `pidgin index . --write-db` does not parse them as global. Spec shows the latter form in pidgin-architecture.md ("pidgin index ./src --write-db") — argparse semantics matter. Pre-decide flag placement convention.
- Step 12 runs live `pidgin index ... --write-db --sync` and SOFT fails on API failure. But the test creates `.pidgin/nest/` only if M12's `ensure_nest` exists — M11 spec says M12 does that. So Step 11 (`test -d /tmp/m11/sample/.pidgin/nest`) wouldn't pass anyway because nest creation isn't wired until M12. Actually Step 11 doesn't test that — it just runs index dry-run. OK. But Step 12's success depends on `nest.upsert_function_descriptions` existing — M11 spec says "add it if missing." Verify.

### Fragile Steps
- Step 13 expects `NotImplementedError` in stderr for `pidgin update`. But `--write-source` flag for update means CLI won't even get to verb body if permission flag enforcement runs first (M12 adds enforcement). For M11 alone, NotImplementedError surfaces.
- `python -m pidgin --help`: if `__main__.py` is `from .cli import main; sys.exit(main())`, `python -m pidgin --help` calls main() with `--help` which argparse handles by printing and exiting 0. If executor expects exit code 0, fine.

### Underspecified
- Subparser positional vs flag ordering: `pidgin --write-db index .` vs `pidgin index . --write-db`. Argparse handles only one cleanly without parents= magic.
- `--sync` and `--batch` both set: spec says "ambiguous; document or reject." Pre-decide.
- index's "dry-run" is the "no --write-db" path. If --write-db unset, does it still run the API calls (just doesn't persist)? That burns API quota silently. Pre-decide.

### Cross-Mission
- M12 fills in stubs by editing the same files. If M11's stub format differs from M12's expected interface (e.g., `run(args)` signature), M12 must rewrite.

---

## M12: Nest convention

### Blockers
- The CLAUDE.md template has `## Re-Indexing` followed by triple-backtick `pidgin index . --write-db` — embedded in a Python triple-quoted string. The triple-backticks inside the Python string need escape consideration. Spec embeds it in the Python f-string as raw markdown — Python will parse it but the resulting file content will be literal markdown which is correct. Fine, but auditor should verify the Python source compiles.
- `nest_mod.query` referenced in M13's query verb. M12 spec says "may need to be added to nest.py if absent." Add it. M13 spec says same. Race between M12 and M13 implementations of the same function.
- Step 11's test: `test -d /tmp/m12/sample/.pidgin/nest -a -f /tmp/m12/sample/.pidgin/CLAUDE.md`. If Step 10's index call SOFT-failed pre-creation (live API down), Step 11 HARD fails. Plan says "if step 10 SOFT-failed pre-creation, create the structure manually for the test then SOFT-fail this step too" — that's not what the step says ("FAIL: HARD"). Inconsistency.

### Fragile Steps
- `compress` verb writes `<input>.compressed.md` by default — collision with existing files; spec doesn't say overwrite/error/skip.
- Permission check: "exit 2 with prescribed error message" — message format matters for tests. Step 14 greps for `--write-source` substring; tolerant.

### Underspecified
- The `update` verb's `--edits-file` JSONL format for EditOps: each line has what schema? Spec says one EditOp per line. JSON-serialised dataclass? Pre-decide.
- compress reads input via what? Path argument is given; just read text. Encoding assumption (utf-8) implicit.

### Cross-Mission
- M13's query verb edits the same file. Verify M12 leaves a clean structure for M13 to extend.

---

## M13: Nested nest discovery

### Blockers
- Step 2's `touch /tmp/m13/parent/child_a/.pidgin/nest/chroma.sqlite3` creates a fake ChromaDB file. M13's discovery only checks for `.pidgin/nest/` dir existence — it doesn't actually open ChromaDB. But Step 11's `pidgin query "anything"` will try to open ChromaDB on the fake sqlite file. ChromaDB will error opening an empty/zero-byte sqlite3 file. The query will likely crash, not return "no results."
- "Searching 2" expected substring in Step 11 — if query crashes before printing this line, test fails.

### Fragile Steps
- discover_nests max_depth=4 — fe-toolkit may have deeper nesting. Configurable but default may miss real nests.
- "Skip standard noise: .git/, node_modules/, ..." — hardcoded list. Misses other directories like `target/`, `dist/`, `.tox/`.
- follow_symlinks=False default — monorepos with submodule symlinks miss children.

### Underspecified
- Namespace collision: two children both named `worker/` in different parent subtrees. Spec doesn't define resolution.
- `nest.query` signature returning `NestQueryHit` with `.similarity`, `.function_name`, `.file`, `.line_start`, `.description` — but no spec for `NestQueryHit` dataclass; it's defined wherever `nest.query` is implemented (M12 or M13). Pre-decide.

### Cross-Mission
- M12's query verb is replaced wholesale in M13's Step 5. M12's tests of query (Step 13 in M12) used local-only path; M13 changes that path. Verify M12 tests still pass after M13.

---

## M14: Bidirectional MLD — probe design

### Blockers
- Phase 5 missions M17-M19 are conditional on M16 = UNLOCK. M14-M16 are unconditional (validation phase). The plan doesn't have an explicit "if defer, halt" mechanism — sprint runner must respect M16's gate.xml or risk dispatching M17-M19 anyway.
- expand.xml is created in M14 but M14 says "NO live execution." So expand.xml is untested for actual generation behavior until M15. If expand.xml has a bug, M15 fails on bad data and M16's gate decision rests on prompt quality, not geometry.
- "Reference implementations may have been refactored since the description was generated" — huge risk. v0.1 → v0.2 extraction (M10) renames/moves files; reference implementation paths in probes.json may be stale by M14's time.

### Fragile Steps
- Step 11's "wc -l ≥ 50 lines for README" — arbitrary; readable README could be shorter.
- harness.py imports `from pidgin.prompts import assemble_xml_prompt` — but M5's assemble may not handle expand.xml's `<output_schema>` differently from converge.xml's. Pre-test.

### Underspecified
- Cost projection: 300 generation calls × $0.006 = $1.80, batched 50% = $0.90. But M15 also runs embedding calls (2-round-trip). 3000 embedding calls. embedding cost negligible. OK. But M15's actual cost depends on `n_calls` — is N=10 candidates per probe done as 10 single-candidate calls or single calls returning 10 drafts? Spec for converge.xml uses three-draft (5 calls → 15). expand.xml — same? Unclear.
- "Stability runs = 3 per (probe, budget)" — 5 × 2 × 3 = 30 runs at N=10 = 300 calls. The math assumes single-candidate-per-call. If three-draft is used, recalculate.

### Cross-Mission
- M15 runs harness.py — must run cleanly. Any pre-existing import bug in harness blocks M15 entirely.
- M16's gate uses cluster_size threshold 6/10. If M15's antipode_test default threshold (0.0 from M7) clusters wildly differently than expected, 6/10 is meaningless.

---

## M15: Bidirectional MLD — execution

### Blockers
- HARD requires `OPENAI_API_KEY`. If not set, mission halts. No fallback. Sprint stalls at M15 until operator provides key.
- Total 300 generation + 3000 embedding calls. Batch path required — under what time budget? OpenAI batches have 24h SLA but typically minutes. Sprint runner must wait.
- If antipode_test uses threshold 0.0 (M7 default), cluster_size in 256-dim code embedding space is likely always close to 10/10 (cosine sim positive in high dims). M16's gate becomes degenerate.

### Fragile Steps
- Per-run record's `syntactic_valid` requires AST parsing. Code embeddings may include surrounding text (docstrings, imports). Extraction heuristic ("look for `def <name>(`") is brittle; if model returns `def add(a: int, b: int) -> int:` and extraction grabs from `def`, fine. If it returns natural language commentary first, AST parse fails on the whole string.
- Step 6's OK_RATIO ≥ 0.8 — 24/30 records produced. If a single batch fails (unusual), 30/30 OR 0/30 depending on failure mode. 80% threshold may not be the right granularity.

### Underspecified
- Cost reporting — OpenAI batch returns cost? Not directly. `usage` field per response yes. Aggregation harness must total.
- "winning_candidate" computation — closest to centroid — must match M18's pass-3 winner selection exactly, else inconsistent.

### Cross-Mission
- M16 reads results.json. If schema drifts between M15's writer and M16's reader, gate decision fails parsing.

---

## M16: Bidirectional MLD — gate decision

### Blockers
- "Operator-style review of code; document the judgment per probe" — M16 is dispatched to an automated runner. The runner is being asked to make architect-level semantic correctness judgments. This is **judgment work that may exceed the runner's authority**. Plan calls this REASON tier but reasoning ≠ architectural authority.
- Verdict 3/5 = "AMBIGUOUS_OPERATOR_DECIDES" — sprint runner halts and waits for human. No mechanism for that wait in the plan.
- "If 4/5 probes produce stable, correct" — design Decision 1 says 4/5 unlocks, fewer than 3 defers, but is silent on exactly 3. Plan invents the AMBIGUOUS bucket. Architect should bless.

### Fragile Steps
- "string-similarity proxy: shared lines ≥ 50%" — line-by-line on Python implementations of the same function will show low overlap (variable rename, formatting). Threshold may always fail, marking probes UNSTABLE.
- Reading reference_implementation_path — if M10 moved the file (M10 between M14 and M15? No — M14 is Phase 4, M10 is Phase 3. M10 already happened. So paths in probes.json should reflect post-M10 state. But M14 may have written paths pointing at v0.1 originals in tools/.

### Underspecified
- "Strict; the gate is meant to be hard to clear" — but the bias may make the gate impossible to clear regardless of geometry.
- M16 writes verdict; Phase 5 dispatch logic unclear. Sprint runner script must read gate.xml and skip M17-M19 on DEFER. Plan doesn't specify the sprint runner's gate-respecting behavior.

### Cross-Mission
- M17 Step 1 grep'es gate.xml for `Verdict: (UNLOCK|AMBIGUOUS)`. If verdict format differs slightly (`**Verdict**: UNLOCK` vs `**Verdict:** UNLOCK`), regex fails. Pre-decide format.

---

## M17: Sprint plan XML template

### Blockers
- Conditional dispatch: M17 Step 1 grep for verdict. If M16 issued DEFER, Step 1 HARD fails (regex doesn't match) — which is the intended halt. But sprint runners typically advance on RED. Verify halt semantics.
- Template mixes `<!-- comment -->` placeholders inside `<description>`, `<compressed>`, etc. Step 4 asserts `present == required` (mission_children list). XML parsers may include comment nodes — `m` is a Element; iterating `for c in m` returns child elements only, not comments. OK.

### Fragile Steps
- Step 4's `assert present == required` — strict order. If template author re-orders for readability, breaks.

### Underspecified
- Pass-marker placement: in `<passes_completed>` block at sprint root vs per-mission. Plan says sprint-root with reference to mission n? Spec actually shows `<passes_completed>` at sprint root containing `<pass n="..."/>` — but no mission ref. So how does processor know which missions completed pass 2? Must be implicit (all of them, atomically). Pre-decide whether per-mission tracking matters.

### Cross-Mission
- M18 reads/writes this template. Any structural choice here is load-bearing.

---

## M18: Multi-pass processor

### Blockers
- "Pass 3 generates code inside an XML tag; CDATA wrapping must be handled" — risk register flags. If generated code contains `]]>`, CDATA can't naively escape. Pre-decide handling (split CDATA, escape, etc.).
- "Read `<description>` text content" — if pass-1 description contains XML-like content (e.g., describing XML processing), text content extraction may strip elements. Use `tostring` with method='text' or get all text including from sub-elements.
- "atomic XML edit" with ElementTree doesn't preserve comments or CDATA by default. lxml does. Spec says fall back to ElementTree with manual workaround — workaround is unspecified and likely buggy.

### Fragile Steps
- "winning candidate: closest to cluster centroid" — needs all candidates' vectors. Pass 3 must run embedding step too. Cost: 19 × 10 = 190 embedding calls. Plus 19 × 10 generation. ~$0.40 batched. OK.
- Idempotency check: "if `<compressed>` non-empty: skip." Whitespace-only content (e.g., the comment-with-newlines from the template) — is that "empty"? `.strip()` matters.

### Underspecified
- pass 2 internally uses what compression? `pidgin compress` is for text→text MLD. Same convergence pipeline. But for short mission descriptions (one paragraph), MLD may produce identical output. Cost of 10 candidates per mission ×19 = 190 calls.
- Document write: how is the original document preserved for diff? No backup mechanism specified.

### Cross-Mission
- M19 calls `run_pass` on real sprint plan. If M18 has bugs, M19's data is junk.

---

## M19: Integration validation

### Blockers
- Step 4 translates sprint.xml → sprint-multipass.xml. Translation rule: "Take mission's `<objective>` text content as `<description>`." But the sprint plan author (this plan) writes `<objective>` as multi-line CDATA-wrapped markdown. Extracting "text content" from CDATA-wrapped element via ElementTree returns the CDATA contents as text — fine. But preserving formatting (lists, paragraphs) into `<description>` may matter for compression quality.
- Self-referential validation: M19 runs M18 on M19's own sprint plan — but M19 IS in that sprint plan. The pass-2/pass-3 generation reads its own description and tries to compress/expand. Recursive in spirit. The sprint.xml at translation time is the static plan — the recursion is harmless but conceptually loaded.
- "pass-4 review: read each generated `<implementation>`, mark <validation> as ACCEPTED/NEEDS_REFINEMENT/REJECTED" — sprint runner makes 19 architect-level judgments. Same authority concern as M16.

### Fragile Steps
- `dispatch='batch'` for 19 missions × 10 candidates = 190 generation calls. Batch threshold (10) triggers. Two batches (gen + embed). ~minutes wait. Sprint runner must accommodate.
- "Total wall time" measured around batch — includes polling. Could be 2 min or 30 min depending on OpenAI queue.

### Underspecified
- "Disposition" thresholds: ≥15/19 ships, 10-14 not-ship-quality, <10 retract. The retract path requires editing v0.2 success criteria — sprint runner can't do this autonomously.
- M19 modifies sprint-multipass.xml, not sprint.xml. But the validation is "the sprint validates itself" — recursion only if sprint-multipass.xml IS sprint.xml. Plan separates them. Fine.

### Cross-Mission
- Final mission. If RED, sprint disposition unclear.

---

## Sprint-Level Risks

1. **v0.1 source dual-pathing creates silent regressions.** M10 doesn't delete `tools/`; any code (test, import, CLI script) still using `from tools.X` continues to work and bypasses pidgin/. Migration appears successful while real usage may still hit v0.1.
   *Mitigation:* After M10 GREEN, run `grep -r "from tools\." /project --include="*.py"` and fail loudly on any hits outside `/project/tools/` itself. Add to M10 verification.

2. **Behavior changes to v0.1 code in Phase 1 violate the constraint.** M3 and M4 require modifying `tools/mld/pipeline.py` to accept `prompt_text` parameter. The constraint says "no behavior changes." Plan acknowledges as "known intrusion, acceptable scope" — but the constraint is in the design, not just plan.
   *Mitigation:* Explicitly note in M3/M4 reports that v0.1 pipeline.py was modified, and have the architect bless before M5. Or implement the prompt swap via monkey-patching in test only.

3. **Decision 6 enforcement is policy, not mechanism.** M7 declares EMBEDDING_MODEL/DIM constants but any caller can pass overrides. Audit grep is one-time at M7. Drift risk across M11-M19.
   *Mitigation:* Add module-level assertion in `embed_for_store` rejecting non-256-dim returns. Add CI grep test that runs continuously.

4. **API key dependence creates cascading SOFT-fails.** M3, M4, M6, M7, M11, M12, M15, M18, M19 all have steps that SOFT-fail on missing API key. The sprint can technically GREEN through Phase 1-3 with API keys absent and produce a "passing" sprint that does nothing live. M15 HARD-fails on missing key — proper.
   *Mitigation:* Pre-flight check: assert OPENAI_API_KEY and ANTHROPIC_API_KEY present before dispatching any mission. Halt if missing.

5. **Phase 4/5 conditional dispatch isn't mechanized.** M16's gate.xml verdict drives M17-M19 dispatch. Sprint runner must read gate.xml and skip on DEFER. Plan describes this but doesn't specify the runner mechanism. Risk: runner advances regardless and burns API on irrelevant missions.
   *Mitigation:* Add explicit Step 0 to M17/M18/M19 that grep's gate.xml and HARD-fails on absent UNLOCK. (M17 already has this; M18/M19 should mirror.)

---

## Recommended Pre-Flight Checks

1. **Verify environment variables:** `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are set and valid. Run a 1-token test call against each. Halt if either missing or rate-limited.

2. **Verify SDKs and versions:** `python -c "import openai, anthropic, chromadb, numpy; print(openai.__version__, anthropic.__version__, chromadb.__version__, numpy.__version__)"`. Confirm SDK versions support batch APIs and structured outputs as specified.

3. **Verify v0.1 source layout:** `find /project/tools -name "*.py" | sort > /tmp/preflight-v01.txt`. Confirm `tools/store/audit.py`, `tools/store/sections_chroma.py`, `tools/store/vectors.py`, `tools/utils/api.py`, `tools/utils/parser.py`, `tools/utils/sections.py`, `tools/mld/pipeline.py`, `tools/mld/probe.py`, `tools/prompts/generate.md`, `tools/prompts/validate.md` all exist. Adjust mission paths if v0.1 structure differs.

4. **Verify ORIGAMI.md location:** `test -f /project/ORIGAMI.md && echo present || find /project -name "ORIGAMI.md" 2>/dev/null`. M5 hardcodes `/project/ORIGAMI.md`; if it lives elsewhere, M5 fails silently to empty registry.

5. **Verify v0.1 baseline file:** `test -f /project/local/sprints/tooling-v0.1/context/v2-mld-validation.md`. M3 references it. If absent, the regression-vs-baseline framing degrades to "compare against assumed 4/4" which is weak evidence.

6. **Verify git config:** `git config --global user.email && git config --global user.name`. M1 and M2 self-tests create temp repos that need git to commit successfully.

7. **Verify `/project` is a git repo:** `cd /project && git rev-parse --is-inside-work-tree`. M1's artifact_write defaults to committing in /project; if not a repo, behavior is undefined.

8. **Verify ChromaDB writeability:** `python -c "import chromadb; c = chromadb.PersistentClient('/tmp/preflight-chroma'); col = c.create_collection('test'); col.add(documents=['x'], ids=['1']); print('ok')"`. Confirm ChromaDB writes work in the executor environment.

9. **Verify prompt format placeholders in v0.1:** Read `tools/prompts/generate.md` and `tools/prompts/validate.md`. Confirm rule/example counts so M3/M4 migration counts are sane.

10. **Decide ambiguities pre-flight:**
    - artifact_write `project_root`: kwarg or auto-derive?
    - `--write-db` and `--write-source` flag placement (global vs per-subcommand)?
    - `--sync` and `--batch` both set: which wins, or error?
    - Decision 6: pre-existing dimension in `tools/utils/api.py` if not 256 — fix in M7 or M10?
    - gate.xml verdict format string exactly.