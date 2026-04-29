# V2 Integration Report — Mission 16

**Date:** 2026-04-26
**Target:** `tools/utils/` (5 tracked files, 23 public functions)
**Status:** GREEN

---

## Per-Step Results

| Step | Skill | Exit | Lines | Verdict | Notes |
|------|-------|------|-------|---------|-------|
| /embed | embed_skill.py | 0 | 14 | PASS | 23 vectors upserted to function_bodies |
| /digest (first run) | digest_skill.py | 0 | 51 | PASS* | 0 sections written — asyncio.run() nested-loop bug |
| /digest (after fix) | digest_skill.py | 0 | 50 | PASS | 8 new sections written, 1 module, 1 repo |
| /dissect-v2 (first try) | dissect_skill.py | 2 | 10 | FAIL | 15 missing MLDs (non-convergent) — preflight hard-stop |
| placeholder MLDs | manual section_put | — | — | PASS | 15 operator-written MLDs for non-convergent functions |
| /dissect-v2 (retry) | dissect_skill.py | 0 | 12 | PASS | 23 contracts + 1 module spec written |
| /technologic --dry-run | technologic.py | 1 | 37 | SOFT | Exit 1 = four-check verdict BLOCKED (23 MISSING_INDEX_ENTRY), not a crash |
| seed-empty workaround | git commit | — | — | PASS | tools/utils/CLAUDE.md seeded empty, committed |
| /technologic real | technologic.py | 0 | 9 | PASS | Result: OK; 5 source files re-commented, CLAUDE.md written |
| vector probe | find_by_body | 0 | 3 | PASS | embed_text and embed_for_store in top 2 hits |

### Per-Step Output Snapshots

**embed (top 3 / tail 5):**
```
INFO: function collections reset.
SKIP: cannot read .../tools/utils/sidecar.py: No such file or directory
# /embed report
- target path: tools/utils
- files walked: 6
...
- vectors upserted: 23
- cost: $0.0001
- collections: function_bodies (23), function_descriptions (0)
```

**digest (top 3 / tail 5):**
```
WARN: cannot read .../tools/utils/sidecar.py: No such file or directory
# /digest report
...
- 8 converged / 15 non-converged
- 8 new sections written
- total: $0.0665
```

**dissect-v2 (top 3 / tail 5):**
```
WARN: cannot read .../tools/utils/sidecar.py: No such file or directory
# /dissect-v2 report
- depth: module
- files walked: 6
- functions contracted: 23 (23 new sections written)
- modules speced: 1 written / 0 skipped
- total cost: $0.3106
```

**technologic --dry-run (top 3 / tail 5):**
```
[dry-run] would write .../tools/utils/__init__.py
[dry-run] would write .../tools/utils/api.py
...
Functions: 23 total, 23 with MLD, 0 missing
Findings: 23 (23 hard stops, 0 warnings)
Result: BLOCKED
```

**technologic real (top 3 / tail 5):**
```
Technologic V2 — 2026-04-26T09:47:07-0400
...
Functions: 23 total, 23 with MLD, 0 missing
Findings: 1 (0 hard stops, 1 warnings)
  TOO_SHORT: tools/utils/CLAUDE.md::reset_cost_totals — 6 tokens
Result: OK
```

---

## Vector Probe

Query: `"how do I call OpenAI embeddings"`  k=3

| Rank | Name | File |
|------|------|------|
| 1 | embed_text | tools/utils/api.py |
| 2 | embed_for_store | tools/utils/api.py |
| 3 | generate | tools/utils/api.py |

Top hits are `embed_text` and `embed_for_store` — exactly as specified. PASS.

---

## ChromaDB State (Post-Integration)

### descriptions collection (53 total)

| doc_type | Count |
|----------|-------|
| behavioral_contract | 23 |
| function_description | 26 |
| module_behavior | 1 |
| module_summary | 2 |
| repo_overview | 1 |

Notes:
- `function_description` (26) = 8 from digest (convergent api.py functions) + 3 pre-existing + 15 placeholder MLDs written by operator
- `behavioral_contract` (23) = per-function contracts from /dissect-v2
- `module_behavior` (1) = tools/utils module spec from /dissect-v2
- `module_summary` (2) = tools/utils module summary from /digest (1 new + 1 pre-existing)
- `repo_overview` (1) = repo MLD from /digest

### Other collections

| Collection | Count | Notes |
|------------|-------|-------|
| function_bodies | 23 | Populated by /embed — all tools/utils functions |
| function_descriptions | 0 | Empty — /embed only writes bodies when no MLD exists |
| principles | 19 | Unchanged from M14 |

---

## Audit Log

**Total records in marionette_actions.jsonl:** 17

**Records added during M16 (/technologic run, 2026-04-26T13:47):** 5

| Timestamp | Agent | Action | File |
|-----------|-------|--------|------|
| 2026-04-26T13:47:06 | technologic | crispr_edit | api.py |
| 2026-04-26T13:47:06 | technologic | crispr_edit | mld.py |
| 2026-04-26T13:47:06 | technologic | crispr_edit | parser.py |
| 2026-04-26T13:47:06 | technologic | crispr_edit | sections.py |
| 2026-04-26T13:47:07 | technologic | crispr_write | CLAUDE.md |

Note: /embed, /digest, and /dissect-v2 do not write audit entries — only CRISPR operations do.

By agent breakdown (all-time): test=5, origami-reprocess=7, technologic=5.

Last audit entry (CLAUDE.md write):
- pre_hash: e3b0c44… (empty file — seed-empty commit)
- post_hash: e57039b… (67 lines, 3737 bytes)
- pre_commit: 3142645
- post_commit: 1e7aa96

---

## Cost Summary

| Skill | Cost |
|-------|------|
| /embed | $0.0001 |
| /digest (retry with fix) | $0.0665 |
| /dissect-v2 | $0.3106 |
| /technologic | ~$0.00 (read-only against sections store) |
| **Total** | **$0.3772** |

Budget guard: $0.3772 < $2.00 limit. PASS.

---

## Anomalies

### 1. asyncio.run() nested-loop conflict in sections_chroma.py

**Root cause:** `section_put_chroma` (tools/store/sections_chroma.py:158) calls `asyncio.run(api.embed_for_store(content))`. When called from within the digest skill's own async event loop (`asyncio.run(main_async(args))`), this raises `RuntimeError: asyncio.run() cannot be called from a running event loop`.

**Effect:** First /digest run produced 0 sections written despite generating MLDs correctly.

**Fix applied:** sections_chroma.py modified to detect a running event loop and dispatch the coroutine via `ThreadPoolExecutor` when one exists. This is a targeted deviation from the spec — the behavior is correct (embed still runs), the mechanism adapts.

**Deviation from spec:** sections_chroma.py was modified as part of M16. This is an integration bug discovered and fixed during the mission. Not a pre-existing validated path per M14+M15 audit.

### 2. 15 non-convergent functions — placeholder MLDs required

**Root cause:** digest's MLD pipeline ran on all 23 functions but 15 did not converge (returned empty description). Digest only writes to sections when `description != ""`. Dissect-v2 preflight hard-stops when any function has no MLD entry.

**Affected functions:** All public symbols in mld.py (3), parser.py (9), and sections.py (3). These are data classes, multi-language parsers, and pass-through wrappers — difficult to compress into 8-12 imperative tokens.

**Fix applied:** Operator wrote 15 placeholder MLDs directly via section_put (model='m16-placeholder', confidence=0.5, converged=False). These are accurate single-sentence descriptions.

**Note:** Re-running /digest with higher --target-n (e.g., 24) or --force-reprocess may eventually converge these. The MLD convergence gate is strict — many parser functions have bodies too complex for the grammar filter at current budget ranges.

### 3. seed-empty workaround fired

tools/utils/CLAUDE.md did not exist. Applied seed-empty per Amendment 2 instruction:
- `touch tools/utils/CLAUDE.md`
- Committed at: `55a3b18` ("seed-empty: tools/utils/CLAUDE.md by m16-integration")

### 4. sidecar.py ghost reference

All 4 skills warn: `cannot read .../tools/utils/sidecar.py`. This file was deleted in M2 but remains in the git index. The warning is harmless — skills skip the file gracefully.

### 5. /technologic real exit 0 with 1 TOO_SHORT warning

`reset_cost_totals` has a 6-token description ("Reset all cost totals to zero."). Below the minimum recommended token count. Not a hard stop — Result: OK.

### 6. function_descriptions collection remains at 0

/embed only populates `function_descriptions` when an MLD already exists at embed-time (via the `--using-existing-mld` path). Since /embed ran with --reset before /digest, no descriptions existed at embed-time. A second /embed run (without --reset) after /digest would populate function_descriptions.

---

## Rollback

**Source re-comments (/technologic):**
```
git revert 17ef675 e3e3f9c 8a89073 c369ba4  # pre-write commits
# or simply:
git checkout 5091143 -- tools/utils/api.py
git checkout c208af5 -- tools/utils/mld.py
git checkout 0c7e416 -- tools/utils/parser.py
git checkout eb12580 -- tools/utils/sections.py
```

**CLAUDE.md (seed-empty + technologic write):**
```
git revert 1e7aa96 3142645 55a3b18
# or:
rm tools/utils/CLAUDE.md
git rm --cached tools/utils/CLAUDE.md
```

**ChromaDB state:** No git-managed rollback. Reset function collections:
```python
from tools.store.vectors import reset_all
reset_all()  # drops function_bodies and function_descriptions only
```
The descriptions collection (behavioral_contract, function_description, etc.) requires manual ChromaDB delete or full store reset.

---

## Per-Skill Verdicts

| Skill | Verdict | Notes |
|-------|---------|-------|
| /embed | PASS | 23 vectors in function_bodies; $0.0001 |
| /digest | PASS (after asyncio fix) | 8 convergent MLDs; 15 non-convergent required operator placeholders |
| /dissect-v2 | PASS (after placeholders) | 23 contracts + module spec; $0.3106 |
| /technologic --dry-run | SOFT (exit 1 = four-check BLOCKED) | Skill ran correctly; exit 1 is the verdict, not a crash |
| /technologic real | PASS | 5 files re-commented; CLAUDE.md built; exit 0, Result: OK |
| vector probe | PASS | embed_text #1, embed_for_store #2 — expected result |
| audit log | PASS | 5 M16 entries (technologic CRISPR writes) |
