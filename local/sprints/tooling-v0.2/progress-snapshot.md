# tooling-v0.2 Sprint Progress Snapshot
**Written:** 2026-04-27 (mid-run)
**Sprint runner session start:** ~45 minutes ago

---

## Overall Status

- **Phase 1 (M1-M5): COMPLETE — all GREEN**
- **Phase 2 (M6-M9): IN PROGRESS**
  - M6: GREEN ✓
  - M7: DISPATCHING NOW (interrupted)
  - M8, M9: pending

---

## Mission-by-Mission Results

### M1: Write model — artifact_write ✅ GREEN
**What it built:** The `pidgin/` package foundation + Modes 3/4 write semantics.
- `pidgin/__init__.py` — MIT header, version 0.2.0
- `pidgin/utils/__init__.py`, `pidgin/utils/git.py` — git bracket helpers
- `pidgin/write/__init__.py`, `pidgin/write/new.py` (artifact_write), `pidgin/write/compress.py` (compress_write)
- `pidgin/write/CLAUDE.md` — discovery index

**Key facts:**
- PD1 implemented: `_find_project_root` walks up to nearest `.git` — self-test in temp repo works correctly
- sha256 hashing (PD5), atomic write via os.replace, one commit + one JSONL audit per batch
- Review: PASS (3 minor non-blocking notes)

---

### M2: Write model — transaction context manager ✅ GREEN
**What it built:** Mode 2 (Update) — the transaction-based file edit system.
- `pidgin/write/update.py` (376 lines) — Transaction context manager

**Key facts:**
- `OverlappingEdit` exception raised when ops have overlapping original line ranges (inclusive interval check)
- Running delta offset: ops target original line numbers, delta applied as ops execute
- Pre-bracket snapshot commit for dirty files; post-commit after atomic write; single JSONL audit entry
- `insert_tag` raises NotImplementedError for non-.py; `strip_comment` records noop metadata
- Review: PASS (3 minor non-blocking notes)

---

### M3: XML prompt — converge.xml ✅ GREEN
**What it built:** The generation prompt in XML format (replacing generate.md).
- `pidgin/prompts/converge.xml` (30,480 bytes) — 8 rules, 33 positive examples, 17 anti-examples
- `pidgin/prompts/__init__.py` — marker
- `pidgin/prompts/CLAUDE.md` — discovery index
- **Modified:** `tools/mld/pipeline.py` — KE1: additive `prompt_text: str | None = None` parameter

**Key facts:**
- 4/4 reference probes at 15/15 convergence — zero regression vs v0.1 baseline
- CACHE BOUNDARY comment at line 540; [CDATA-OPEN]/[CDATA-CLOSE] as literal placeholders
- P3/P4 sourced from tools/mld/probe.py (not sections.py — justified as canonical source)
- Cached preamble ~7,482 tokens (larger than generate.md, cache hit amortizes cost)
- Review: PASS

---

### M4: XML prompt — gate.xml ✅ GREEN
**What it built:** The validation gate prompt in XML format (replacing validate.md).
- `pidgin/prompts/gate.xml` (5,264 bytes) — 11 criteria, 6 examples

**Key facts:**
- G1-G4 (valid descriptions): all valid=true ✓
- G5 (truncated "Merge delta into a copy of state,"): valid=false ✓
- **IMPORTANT FINDING:** `gpt-4.1-nano` hallucinated on valid descriptions (claimed trailing commas, called "Parse" non-imperative). Had to switch to `claude-haiku-4-5` for gate calls. Future pipeline wiring must use haiku-4-5 minimum.
- validate.md was a candidate SELECTOR (not a binary gate) — gate.xml is a design evolution
- pipeline.py NOT modified (gate not yet wired in — acceptable per KE1)
- Review: PASS (model switch noted as CONCERN, non-blocking)

---

### M5: XML assembly — templates.py ✅ GREEN
**What it built:** The prompt assembler — principle injection, placeholder substitution, cache boundary split.
- `pidgin/prompts/templates.py` (4.9KB)

**Key facts:**
- 19 principles parsed from ORIGAMI.md
- Selective injection: selected_words=48 (ids 1,3,7) vs full_words=613 — 13x compression confirmed
- KeyError raised on missing payload key (name, line_start, etc.)
- CACHE BOUNDARY split: substring match on any line containing `===== CACHE BOUNDARY =====`
- Review: PASS (1 minor note: tuple vs list type annotation)

---

### M6: Batch dispatch — generation path ✅ GREEN
**What it built:** OpenAI Batch API integration for generation calls.
- `pidgin/pipeline/__init__.py` — marker
- `pidgin/pipeline/batch.py` (11KB) — GenerationRequest/Result, build_jsonl, should_use_batch, run_batch_generation, parse_batch_results
- `pidgin/pipeline/mld.py` (29KB) — copy of tools/mld/pipeline.py with additive `dispatch` parameter
- `pidgin/pipeline/CLAUDE.md` — discovery index

**Key facts:**
- Live batch test: 20/20 results, 0 errors, 166.3 seconds wall time
- DP4 threshold confirmed: n_tasks >= 10 → batch; < 10 → sync
- Response shape: dict-with-keys (`{"draft_1":..,"draft_2":..,"draft_3":..}`) with json_schema response_format
- JSONL: system=cached_preamble (cacheable), user=payload — correct structure
- parse_batch_results: 8 test cases covering all 4 shapes + missing + error paths
- Review: PASS (1 minor: error message string "missing from batch output" vs "missing_from_batch_output")

---

### M7: Batch dispatch — embedding path — DISPATCHING NOW (interrupted)
Not yet complete. Will add:
- `pidgin/utils/api.py` — EMBEDDING_MODEL, EMBEDDING_DIM constants, get_openai_client factory
- `pidgin/pipeline/geometry.py` — cosine_similarity, centroid, antipode_test
- Extension to `pidgin/pipeline/batch.py` — EmbeddingRequest/Result, run_batch_embedding, run_embedding_mld_pipeline_for_functions

---

## Remaining Missions

| Mission | Phase | Description | Status |
|---------|-------|-------------|--------|
| M7 | 2 | Batch embedding + geometry | In dispatch |
| M8 | 2 | Adaptive candidates | Pending |
| M9 | 2 | Anthropic batch (gate calls) | Pending |
| M10 | 3 | Package extraction + import reconciliation | Pending |
| M11 | 3 | CLI — four verbs | Pending |
| M12 | 3 | Nest convention | Pending |
| M13 | 3 | Nested nest discovery | Pending |
| M14 | 4 | Bidirectional MLD — probe design | Pending |
| M15 | 4 | Bidirectional MLD — execution | Pending (live API, ~$0.90) |
| M16 | 4 | Bidirectional MLD — gate decision | Pending (HARD STOP after this) |
| M17-M19 | 5 | Sprint-plan-as-artifact | Conditional on M16 gate |

---

## API Spend Tracker (cumulative estimate)

| Mission | Spend |
|---------|-------|
| M3 | ~$0.05 (60 gen + embed calls) |
| M4 | ~$0.02 (10 gate calls) |
| M6 | ~$0.002 (20 gen calls via batch) |
| M7 | TBD (live pipeline test pending) |
| **Total so far** | **~$0.07** |
| **Budget remaining** | **~$1.93** (target <$2.00 total) |

---

## Key Risks Surfaced

1. **gpt-4.1-nano unreliable for gate calls** — switches to claude-haiku-4-5 required (M4)
2. **Cached preamble is large** (~7.5K tokens) — cache-hit amortization needed
3. **gate.xml not yet wired into pipeline.py** — deferred to later mission (KE1)
4. **Batch poll timeout** (30 min default) vs OpenAI's 24h completion window

---

## Files Created (net new under pidgin/)

```
pidgin/
├── __init__.py
├── pipeline/
│   ├── __init__.py
│   ├── batch.py
│   ├── CLAUDE.md
│   ├── geometry.py       (M7 — in progress)
│   └── mld.py
├── prompts/
│   ├── __init__.py
│   ├── CLAUDE.md
│   ├── converge.xml
│   ├── gate.xml
│   └── templates.py
├── utils/
│   ├── __init__.py
│   ├── api.py            (M7 — in progress)
│   └── git.py
└── write/
    ├── __init__.py
    ├── CLAUDE.md
    ├── compress.py
    ├── new.py
    └── update.py
```
