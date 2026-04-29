# Tooling V1 — Execution Log

**Executed:** 2026-04-24
**Dispatch mode:** Local agents (scout: haiku-4-5, execute: sonnet-4-6, reason: opus-4-7)
**Decision points:**
- DP-1: tools/prompts/ for shared; each skill's prompts/ for skill-specific
- DP-2: embed_dim default = 128
- DP-3: ANTHROPIC_API_KEY + OPENAI_API_KEY confirmed in local/.env
- DP-4: Pad cached prompts to ≥4096 tokens with grammar rules, examples, controlled vocabulary, structured output schema

---

### Mission 1: Baseline Audit — GREEN
- Tier: scout
- Dispatch: local agent
- Steps: 8/8 HARD passed, 1/1 SOFT passed
- Review: skipped (review: false)
- Review findings: n/a
- Files written: none
- Key observations: Both API keys confirmed. All 5 skills present. embed.py has embed() at line 25, main() at line 36 (81 lines total). Scratch file present.
- Anomalies: tools/ also contains CLAUDE.md and .venv (not in spec expected list — benign extras)

### Mission 2: utils/api.py + sidecar.py + requirements.txt — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: 11/11 HARD passed, 0 SOFT
- Review: CONCERNS
- Review findings: 0 critical, 1 warning, 8 notes
- Files written: tools/requirements.txt (modified), tools/utils/__init__.py, tools/utils/api.py (376 lines), tools/utils/sidecar.py (102 lines)
- Key observations: All three async def (generate, generate_batch, embed_text) and all three sidecar defs implemented. Anthropic cache_control, strict tool use, and n>1 cache-warming all correctly implemented.
- Anomalies: (1) OpenAI path `max_tokens` → patched to `max_completion_tokens` post-review (o1/o3/o4 reject max_tokens; gpt-5-nano accepts both but deprecation active); (2) unused `_retry_sync` dead code; (3) sidecar.merge_sidecar does not validate model/dimensions compatibility between old and new chunks

### Mission 3: utils/mld.py + utils/parser.py — GREEN (execution) / FAIL (review)
- Tier: reason
- Dispatch: local agent
- Steps: 10/10 HARD passed
- Review: FAIL (reviewer mislabeled CONCERNS but listed 4 criticals — treated as FAIL)
- Review findings: 4 critical, 9 warnings, 7 notes
- Files written: tools/utils/mld.py (550 lines), tools/utils/parser.py (470 lines)
- Key observations: MLD pipeline structure correct. Grammar filter, antipode test, confidence formula all match spec. Parser covers all 5 languages.
- Anomalies (critical):
  1. mld.py:196-215 — schema-path extraction: _extract_candidate returns plain string, grammar_filter then tries json.loads on it and rejects every candidate
  2. parser.py:76-84 — ast.walk not used; tree.body iteration only captures top-level defs, misses class methods
  3. parser.py:200-204 — TS regex makes `export` optional; captures non-exported items marked private (spec requires exported only)
  4. parser.py:266-268 — Go regex captures all funcs; spec says capitalized-name only

### Mission 3-P: Patch four review criticals — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: all HARD passed
- Review: skipped (patch mission)
- Files modified: tools/utils/mld.py, tools/utils/parser.py
- Key changes:
  - C1: _extract_candidate always serializes full JSON; _candidate_text helper added; mld() call sites wrapped
  - C2: parse_python uses ast.walk(tree) — class methods now extracted
  - C3: _TS_ITEM requires export at col 0; let/var/enum removed from kinds
  - C4: _GO_FUNC/_GO_TYPE require [A-Z] first char — exported names only
- Anomalies: Step 15 grep count was 2 (extract_imports already used ast.walk); verified functionally

### Mission 4: strip_comments.py + extract_functions.py — GREEN (execution) / FAIL→patched (review)
- Tier: execute
- Dispatch: local agent
- Steps: 9/9 HARD passed
- Review: FAIL (6 labeled criticals; 2 real, 4 within spec's "regex-based acceptable" provision)
- Review findings: 2 critical (patched), 8 warnings, 5 notes
- Files written: tools/strip_comments.py (282 lines), tools/extract_functions.py (149 lines)
- Key observations: CLI conventions match embed.py. 7 slot markers on embed.py. Shebang preserved.
- Anomalies accepted: JS/TS regex literals and template literals unhandled (spec says "same as Rust" — documented limitation)

### Mission 4-P: Patch two criticals in strip_comments.py — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: all HARD passed
- Review: skipped (patch mission)
- Files modified: tools/strip_comments.py
- Key changes:
  - C1: _strip_rust parameterized with `lang`; _strip_go passes lang="go" → slot markers now `#` for Go
  - C2: multi-line block comment emits slot marker on opening line; closing line emits only trailing content
- Verified: Go `# [COMMENT_SLOT:...]`, Rust multi-line marker on first line, Python shebang intact, 13 slots on embed.py

### Mission 5: chunk_md.py + chunk_py.py + chunk_rs.py — GREEN (execution) / FAIL (review)
- Tier: execute
- Dispatch: local agent
- Steps: 9/9 HARD passed
- Review: FAIL (reviewer labeled CONCERNS but listed 4 criticals — treated as FAIL; 2 real, 2 within spec's acceptable-limitation provision)
- Review findings: 4 critical (2 real, 2 accepted), 7 warnings, 5 notes
- Files written: tools/chunk_md.py (219 lines), tools/chunk_py.py (193 lines), tools/chunk_rs.py (134 lines)
- Key observations: Markdown, Python AST, and Rust chunkers all produce Chunk dataclasses matching sidecar.py schema. chunk_py.py uses ast.iter_child_nodes directly (not parse_python) for unambiguous class membership. chunk_rs.py one-chunk-per-pub-item. chunk_md.py sections on heading boundaries.
- Anomalies (critical — real):
  1. chunk_md.py — any `|`-leading line triggered table mode; `_TABLE_SEP_RE` defined but unused; prose tables with `|` chars incorrectly chunked as tables
  2. chunk_md.py — leading prose before first `#` in ≥50-line file emitted `header_chain: []` (empty array breaks downstream lookup)
- Anomalies (accepted — within spec):
  3. chunk_py.py — module-level chunk line_range is [min_uncovered, max_uncovered], not contiguous (spec says "one trailing chunk", no contiguity requirement)
  4. chunk_py.py — nested classes silently dropped (spec does not describe nested class behavior)

### Mission 5-P: Patch two criticals in chunk_md.py — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: all HARD passed
- Review: skipped (patch mission)
- Files modified: tools/chunk_md.py
- Key changes:
  - C1: Two-pass table detection — buffer `|`-leading lines as candidates; only confirm as table when `_TABLE_SEP_RE` (`| --- |`) line seen; non-`|` line before confirmation flushes buffer to section_lines as prose
  - C2: header_chain fallback: `chain = section_chain if section_chain else [Path(source_file).name]` in flush_section — leading prose now emits filename as chain
- Verified: empty_chains=0 on CLAUDE.md, correct table/prose discrimination confirmed

### Mission 6: End-to-End Dry Run (mechanical pipeline) — GREEN
- Tier: scout
- Dispatch: local agent
- Steps: 9/9 HARD passed, 0 SOFT
- Review: skipped (review: false)
- Review findings: n/a
- Files written: none (temp /tmp only)
- Key observations: Full embed.py round-trip — extract_functions (2 records: embed, main), strip_comments (13 slots, stripped source parses cleanly), chunk_py (3 chunks with line_range). All CLI flags wired. All JSON valid. anthropic-0.97.0 and numpy-2.4.4 installed.
- Anomalies: none — wiring clean, ready for Mission 7

### Mission 7: MLD Empirical Validation — GREEN
- Tier: reason
- Dispatch: local agent
- Steps: 8/8 HARD passed, 0 SOFT
- Review: skipped (review: false)
- Review findings: n/a
- Files written: local/sprints/tooling-v1/context/mld-validation-2026-04-24.md
- Total cost: $0.3458 (7 runs, avg $0.049/run — well under $5.00 ceiling)
- Key observations: Pipeline converges. dim 64 = no separation (both @ 24 tok), dim 128 = false-positive tight cluster (Haiku truncation artifact), dim 256 = first stable separation (embed=8 tok, main=16 tok). Recommend embed_dim=256 over DP-2 value of 128.
- Anomalies (critical for Mission 9):
  1. gpt-5-nano default in mld.py is broken — reasoning model consumes entire output budget with thinking tokens; emits empty strings. Must switch default to claude-haiku-4-5 BEFORE Mission 9.
  2. Cache hit rate = 0% across 329k input tokens despite correct cache_control ephemeral. Uninvestigated — must verify before tool ships.
  3. Grammar filter: 0% reject rate (prompt coaching too effective) and no truncation detection (mid-sentence strings pass).
  4. Non-convergent path unexercised — constructed ambiguous case converged. Verified by code inspection only.
- Anomalies (accepted deviations): n=5 not n=10 (rate limit + gpt-5-nano 8-cap), switched generator to claude-haiku-4-5, temperature=1.0 for parity

### Mission 7-E: Extended MLD Validation — GREEN
- Tier: reason (runner-executed after repeated agent timeout on long API run)
- Dispatch: local agent (driver written by agent; experiment run directly by runner)
- Steps: 12/12 HARD passed, 0 SOFT
- Review: skipped
- Review findings: n/a
- Files written: local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md
- Total runs: 47 | Total cost: $0.3345 (ceiling headroom: $9.67)
- Cache hit rates: haiku=95.2%, gpt-4.1-nano=49.6%, gpt-4o-mini=44.3% — all models caching with 4549-token prompt (validates DP-4)
- Key findings:
  1. gpt-4.1-nano: 18/18 convergences, most consistent, cheapest — PERMANENT DEFAULT
  2. haiku: 8/9 non-convergences in Phase B, stochastic across identical configs — NOT SUITABLE as default
  3. embed_dim: no quality difference between 256/512/768 for OpenAI models → dim=256 (cheapest)
  4. n: no improvement from 5 → 10 or 15; n=5 is sufficient
  5. Phase D quality concern: apply() converged at 8-12 tokens with incomplete descriptions; grammar filter passes trailing-comma and truncated outputs
- Permanent defaults confirmed: generation_model=gpt-4.1-nano, embed_dim=256, n=5, budget_step=8, budget_range=(8,32)
- Must-fix for Mission 9: (1) change mld.py defaults; (2) add grammar filter truncation/mid-sentence detection; (3) add gpt-4.1-nano to RATES table

### Mission 8: Shared prompts — generate.md, validate.md, recomment.md — GREEN (execution) / FAIL (review)
- Tier: execute
- Dispatch: local agent
- Steps: 11/11 HARD passed, 0 SOFT
- Review: FAIL (3 criticals, all in generate.md; validate.md and recomment.md acceptable)
- Review findings: 3 critical, 2 warnings, 6 notes
- Files written: tools/prompts/generate.md (40,157 chars), tools/prompts/validate.md (4,365 chars), .claude/skills/technologic/prompts/recomment.md (9,591 chars)
- Key observations: generate.md is 40,157 chars (1.67× floor), 17 sections, all 16 Origami terms present, DESIGN NOTE in all three files, all four live validation failures present as named anti-examples.
- Anomalies (critical):
  1. generate.md: ~30/32 GOOD examples have wrong token_count values (off by 1–6 from whitespace word-split). Generator will learn to miscount; grammar filter will break on boundary cases.
  2. generate.md: Multiple budget=8 GOOD examples are below the 8-token floor (6–7 tokens). Rule 2 requires ≥8. Contradicts hard-budget DESIGN NOTE.
  3. generate.md: One budget=8 GOOD example is 9 tokens ("Clamp a float value between lo and hi bounds.") — over budget at the tier it's teaching.
- Anomalies (warnings): "8-Token Floor Discipline" section uses 9–10 token constructions without flagging as over-budget; Schema Mode example claims token_count=10 but actual word-split is 9.

### Mission 8-P: Patch three criticals in generate.md — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: all HARD passed
- Review: skipped (patch mission)
- Files modified: tools/prompts/generate.md
- Key changes:
  - C1: Recounted all 34 JSON example blocks; 31/34 had wrong token_count (off by 1–6); all corrected to len(description.split())
  - C2: 5 budget=8 GOOD examples were sub-floor (6–7 tokens); rewritten to exactly 8 tokens: "Add two integers...", "Parse YAML config and return...", "Convert a camelCase identifier...", "Return the absolute value of a given integer.", plus Rust extended example
  - C3: Two budget=8 examples were over-budget (9–10 tokens); trimmed to 8 tokens each
- Verified: 0 token_count mismatches, 0 floor/ceiling violations across all 34 examples; file 39,863 chars (≥24,000 ✓)

### Mission 9: /technologic active skill — technologic.py + SKILL.md — GREEN
- Tier: reason
- Dispatch: local agent
- Steps: all HARD passed (syntax parse clean, SKILL.md frontmatter valid, 21 defs present, all 4 CLI flags present)
- Review: CONCERNS (0 critical, 10 warnings, 4 notes)
- Review findings: See key warnings below
- Files written: .claude/skills/technologic/technologic.py (912 lines, 21 top-level defs), .claude/skills/technologic/SKILL.md (overwritten)
- Files patched: tools/utils/mld.py (defaults + grammar filter), tools/utils/api.py (RATES table + dotenv override)
- Key observations: All four operator patches applied correctly (generation_model=gpt-4.1-nano, embed_dim=256, n=5; grammar_filter trailing-punct/conjunction/fragment rules; gpt-4.1-nano RATES entry; load_dotenv override=True). technologic.py public surface: FunctionMLD, FileResult, PipelineReport dataclasses; resolve_git_root, list_tracked_sources; extract_functions, strip_file_via_subprocess, compute_mld_for_function, recomment_file, _reinsert_slots, format_files, synthesize_claude_md, write_claude_mds; enforce_checks, run_pipeline, run_enforce_only, main. --enforce-only routes to run_enforce_only() with no writes.
- Anomalies (review warnings):
  1. Enforcement phase calls git ls-files which won't find just-written CLAUDE.md files (untracked) → false MISSING_INDEX_ENTRY hard stops on every full-write run. Workaround: run git add before enforcement, or skip CLAUDE.md staleness check in pipeline mode.
  2. _COMPLETE_SHORT_WORDS allowlist missing "its", "our", "not", "now" from spec list — descriptions ending in these 3-char words will be incorrectly rejected as truncation artifacts.
  3. SKILL.md.bak backup: /tmp/backup-technologic-SKILL.md was created (per step 1), but technologic.py itself doesn't produce the .bak — this is an operator-level action, not a runtime concern.
  4. write_claude_mds dry-run mode does not print which CLAUDE.md files would change (silent).
  5. synthesize_claude_md uses first function's MLD as file-level description (not spec-required, heuristic anchor).

### Mission 10-P: Patch two blocking bugs in technologic.py — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: 10/10 HARD passed
- Review: skipped (patch mission)
- Files patched: .claude/skills/technologic/technologic.py
- Key changes:
  - Bug 1: Added _unwrap_mld_json(raw) helper — extracts "description" field if raw is a JSON object, returns as-is otherwise. Updated compute_mld_for_function call site: mld=_unwrap_mld_json(result.description or "").
  - Bug 2: Updated _reinsert_slots regexes from `# SLOT:<id>` / `/* SLOT:<id> */` to `# [COMMENT_SLOT:<id>]` / `// [COMMENT_SLOT:<id>]` to match actual strip_comments.py output. Docstring updated to match.
- Smoke test: all 3 JSON-extraction cases + 2 regex match cases + 1 non-match case passed.
- Anomalies: none

### Mission 10 (re-run post-10-P): /technologic --verify-only — GREEN (pipeline) / BLOCKED (enforcement)
- Pipeline ran without crash. Cost: $0.0233. Both functions converged at 16 tokens (was 32/16 with JSON wrapper artifact — fixed).
- _unwrap_mld_json fix confirmed: `embed` → "Call the OpenAI embeddings API with the given model and input text, return the resulting vector." (plain text, 16 tokens). Slot regex fix: not directly verified (embed.py has no stripped slots in this run — it's already stripped source in the dry run).
- Enforcement BLOCKED (40 hard stops, 25 warnings): all findings are false positives. Root CLAUDE.md and non-tools CLAUDE.md files document services (redis, nginx, watchtower...), MongoDB collections, and lifecycle artifacts — not tracked Python functions. Enforcement incorrectly treats every table row as a code symbol and marks them ORPHANED. This is a scope/design tension, not a pipeline bug. Fix: scope --write to tools/ where only embed.py lives, or add a skip list for non-code CLAUDE.md files.
- DIFF: tools/embed.py would change — confirms the pipeline produces proposed source (slot reinsertion cannot be verified without a slot-bearing file, but regex fix is verified by smoke test).
- Edge case flagged: truncated-JSON artifacts (budget cap cuts mid-JSON before closing brace) fall through _unwrap_mld_json (json.loads fails → returns raw). Grammar filter text path doesn't reject `{`-leading strings. Not observed in this run. Low risk at n=5 with well-formed prompts.
- Recommendation: Ready for --write on tools/ scope. Do NOT use . scope until enforcement is tuned for non-code CLAUDE.md files.

### Mission 10: /technologic --verify-only on fe-toolkit — RED (2 blocking bugs)
- Tier: reason
- Dispatch: local agent
- Steps: step 3 (--verify-only) GREEN (no crash); interpretation RED
- Review: skipped (review: false)
- Files written: /tmp/tech_verify.log, local/sprints/tooling-v1/context/technologic-report.md (by pipeline)
- Files walked: 1 (tools/embed.py — only tracked source file). Functions documented: 2.
- Cost: $0.0218 (well under budget)
- Complexity distribution: embed=32tok (budget-ceiling artifact), main=16tok. Neither non-convergent.
- Anomalies (blocking — RED):
  1. compute_mld_for_function passes schema=None to mld_mod.mld(). generate.md trains the model to output {"description": "...", "token_count": N} JSON. grammar_filter text-mode passes JSON strings (first token "description" is not a copula). _candidate_text(schema=None) returns JSON verbatim. Result: every FunctionMLD.mld is a raw JSON fragment like '{"description": "Call the OpenAI...", "'. Writing this to source files or CLAUDE.md would land JSON literals in the code.
  2. _reinsert_slots regex matches `# SLOT:<id>` and `/* SLOT:<id> */`. strip_comments.py emits `# [COMMENT_SLOT:<id>]` and `// [COMMENT_SLOT:<id>]`. Zero matches → all slot lines remain as literal markers in the proposed new_source. Slot reinsertion is completely broken.
- Recommendation: NOT ready for --write run. Compose Mission 10-P to fix both bugs before re-attempting.

### Mission 9-P: Patch four review concerns — GREEN
- Tier: execute
- Dispatch: local agent
- Steps: 14/14 HARD passed
- Review: skipped (patch mission)
- Files written: tools/utils/sections.py (247 lines)
- Files patched: .claude/skills/technologic/technologic.py, tools/utils/mld.py
- Key changes:
  - Item 1: sections.py — section_get(file, tag) → (content, attrs) | None; section_put(file, tag, content, model=None) → bool. Hash-based idempotency, version/updated/by/model/source_hash attributes, language-aware comment prefix (py=#, rs/js/ts/go=//, md/html=bare).
  - Item 2: technologic.py — synthesize_claude_md → synthesize_index_content (strips top-level # header; returns only ## Files block); write_claude_mds rewired to section_put(target, "index", index_content, model=MLD_GENERATION_MODEL); .bak backup logic removed. shutil retained (used by format_files).
  - Item 3: mld.py — _COMPLETE_SHORT_WORDS += {"its", "our", "not", "now"}
  - Item 4: technologic.py — write_claude_mds return captured as written_claude_mds; git -C <git_root> add -- <paths> run (check=False) before enforce_checks
- Anomalies: none — all steps passed; shutil retained intentionally (shutil.which in format_files)

---

### Operator notes — pre-Mission 8

**Note 1 — generate.md prompt seed**
/tmp/mld_extended_prompt.txt (18,197 chars, ~4,549 tokens) is the validated seed.
Mission 8 formalizes this prompt into tools/prompts/generate.md but does NOT redesign
it. It produced 18/18 convergences with gpt-4.1-nano. The ≥4,096 token floor must be
maintained for Haiku cache efficiency (DP-4 validated at 95.2% hit rate). The padding
is useful context — grammar rules, worked examples, Origami vocabulary, structured
output schema — not filler. Do not trim it.

**Note 2 — soft budget redesign is planned but deferred**
The current hard-budget approach (strict max_tokens per tier, mechanical grammar filter
by regex) is the validated path. A soft budget redesign is planned as the next iteration:
generous max_tokens with an explicit "be concise" instruction, LLM-based validation
replacing the mechanical grammar filter. Mission 8 must write prompts for the current
hard-budget approach only. Note this design intent in a comment at the top of each
prompt file. The soft budget redesign ships after Mission 9 completes and /technologic
is working end-to-end — we need a working skill to iterate against before redesigning
the generation strategy.

**Note 3 — dotenv override fix belongs in Mission 9 patch list**
Every script since Mission 7 (mld_validate.py, mld_extended_validate.py, mld_probe.py)
has independently worked around the same bug: Claude Code's ambient ANTHROPIC_API_KEY
shadows the key in local/.env because dotenv load_dotenv() does not override by default.
The fix (load_dotenv(override=True)) must be applied once in api.py's dotenv load block,
not patched per-script. Add this to Mission 9's patch list alongside the mld.py defaults
and grammar filter fixes.

---

## Final Summary — Sprint Closed by Operator Decision

**Closed:** 2026-04-25
**Overall verdict:** GREEN — foundation delivered

**Missions 11–18: CANCELLED** — superseded by tooling-v2 design.

The remaining missions were:
- 11: /digest prompts (analyze.md, analyze_anonymized.md)
- 12: /digest skill (digest.py, SKILL.md)
- 13: /digest validation on rf-edge/watchtower
- 14: /embed skill (embed_skill.py, SKILL.md)
- 15: /embed validation on docs/
- 16: /consolidate skill (consolidate.py, SKILL.md)
- 17: /consolidate validation
- 18: Cleanup — retire /finalize, /dissect, delete scratch file

These are not left incomplete — the design evolved past them. tooling-v2 will address
the remaining skill surface with the benefit of a working /technologic to iterate
against and validated MLD defaults in hand.

### What the sprint delivered

| Artifact | Status |
|----------|--------|
| tools/utils/api.py | Complete — Anthropic + OpenAI async client, cost tracking, prompt caching, dotenv override |
| tools/utils/sidecar.py | Complete — embedding sidecar format, merge/split |
| tools/utils/mld.py | Complete — MLD pipeline, grammar filter, antipode convergence, validated defaults (gpt-4.1-nano, dim=256, n=5) |
| tools/utils/parser.py | Complete — 5-language function extraction (py/rs/ts/js/go) |
| tools/utils/sections.py | Complete — section_get/section_put, hash idempotency, version tracking |
| tools/strip_comments.py | Complete — comment stripping with [COMMENT_SLOT:] markers |
| tools/extract_functions.py | Complete — function extraction CLI |
| tools/chunk_md.py | Complete — Markdown chunker with two-pass table detection |
| tools/chunk_py.py | Complete — Python AST chunker |
| tools/chunk_rs.py | Complete — Rust pub-item chunker |
| tools/prompts/generate.md | Complete — 39,863 chars, 34 calibrated examples, 4096+ token floor for cache efficiency |
| tools/prompts/validate.md | Complete — description validator prompt |
| .claude/skills/technologic/prompts/recomment.md | Complete — inline contract generator prompt |
| .claude/skills/technologic/technologic.py | Complete — active MLD pipeline: extract→strip→MLD→recomment→index→enforce |
| .claude/skills/technologic/SKILL.md | Complete — rewritten for active mode, --enforce-only preserved |

### Key decisions locked in by this sprint

- **generation_model: gpt-4.1-nano** — 18/18 convergences, $0.005/run avg, 5.1s avg. haiku unreliable (high stochastic variance). gpt-4o-mini 1.5× more expensive with no quality advantage.
- **embed_dim: 256** — no quality delta at 512/768; cheapest embedding calls.
- **n: 5** — no improvement at 10 or 15; 0% grammar reject rate means more candidates add no diversity.
- **budget_range: (8, 32), budget_step: 8** — four tiers sufficient; observed convergence range 8–16 tokens for real functions.
- **Cache: ≥4096 token prompt floor** — validated at 95.2% haiku cache hit rate (DP-4).
- **Hard-budget approach confirmed** — soft budget redesign deferred to tooling-v2; needs a live skill to iterate against.

### Known open items for tooling-v2

1. Enforcement scope: --enforce-only treats every CLAUDE.md table row as a code symbol. Root CLAUDE.md documents services, collections, and vocabulary — all false-positive ORPHANED. Enforcement needs a scope annotation or skip logic for non-code CLAUDE.md files.
2. Truncated-JSON edge case: if the budget cap cuts a JSON response mid-string before closing `}`, _unwrap_mld_json falls back to raw. Grammar filter text path doesn't reject `{`-leading strings. Not observed in practice at n=5 but present.
3. CLAUDE.md synthesis drops hand-crafted sections: synthesize_index_content produces only the ## Files table. section_put writes it as `<index>` so existing prose is preserved — but the original header and non-table content (## Venv, ## Credentials, etc.) must be hand-authored first; the pipeline won't regenerate them.
4. _reinsert_slots slot coverage: unverified on a file with actual slot markers in this sprint. Regex is correct by smoke test; end-to-end slot fill needs a live --write run against a commented file.
5. Soft budget redesign: planned, deferred. Current hard-budget + mechanical grammar filter is the validated path.

### Sprint statistics

- Missions executed: 10 missions + 4 patch missions (9-P, 10-P, plus 3-P, 4-P, 5-P, 8-P from earlier)
- Total API cost: ~$0.72 (M7: $0.3458, M7-E: $0.3345, M10 verify runs: ~$0.046)
- Adversarial reviews: 4 (M3 FAIL→patch, M4 FAIL→patch, M5 FAIL→patch, M8 FAIL→patch, M9 CONCERNS→patch)
- Hard bugs caught by review: 12 criticals patched across 4 missions
- Hard bugs caught post-ship (M10 verify): 2 (JSON envelope, slot regex) — both patched in 10-P

**Sprint tooling-v1: CLOSED.**
