---BEGIN MISSION 7-E---
tier: reason
review: false

<context>
Mission 7 established a baseline using claude-haiku-4-5 at n=5, dims 64/128/256.
Key findings that motivated this experiment:
- gpt-5-nano (the mld.py default) emits empty strings — reasoning model consumes
  budget with thinking tokens before emitting content. Default must change.
- dim 128 (DP-2) showed false-positive convergence via Haiku output truncation.
- dim 256 was the first stable separation point, but 512/768 were not tested.
- n=10 and n=15 were not tested on non-reasoning OpenAI models.
- Cache hit rate was 0% — needs investigation under load.

This mission sets the PERMANENT defaults for the MLD pipeline. Every parameter
recommended here is written into mld.py in Mission 9 and stays there.

Budget ceiling: $10 hard abort. Estimated cost: $3–6.

Test subject functions:
- tools/embed.py::embed   — known simple (baseline: converges at 8–16 tok)
- tools/embed.py::main    — known complex (baseline: converges at 16–32 tok)
- apply() (inline)        — genuinely ambiguous; multiple valid descriptions
  at different abstraction levels. Expected to non-converge or converge late.
</context>

<objective>
1. Verify gpt-4.1-nano and gpt-4o-mini work at low token budgets (non-reasoning).
2. Sweep embed dims [256, 512, 768] — identify minimum stable-separation dim.
3. Sweep n values [5, 10, 15] on OpenAI models — measure antipode robustness
   and grammar filter reject rate as n grows.
4. Validate the non-convergence path empirically with a genuinely ambiguous function.
5. Track per run: convergence token count, candidates passing grammar filter,
   grammar filter reject rate, cache hit rate, wall clock seconds, cost dollars.
6. Recommend permanent defaults: (generation_model, embed_dim, n, budget_step).
7. Write findings to /project/local/sprints/tooling-v1/context/
   mld-validation-extended-2026-04-24.md.
</objective>

<specification>

### Genuinely ambiguous test function

```python
AMBIGUOUS_SRC = '''def apply(state, delta, strict=False):
    out = dict(state)
    for key, value in delta.items():
        if strict and key not in out:
            raise KeyError(key)
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out'''
```

This function has multiple valid descriptions at different abstraction levels:
- "Merge delta into a copy of state, deleting None-valued keys" (18 tok)
- "Apply a patch dict to state with optional strict-key validation" (20 tok)
- "Update a state copy from delta, removing keys where value is None" (22 tok)

The antipode test should struggle to converge below 16 tokens because the
correct minimum description requires naming both the merge and the None-delete
behavior. If the pipeline converges at 8 tokens, flag as a quality concern.

### Rates for new models (inject into api.RATES at driver startup)

```python
# gpt-4.1-nano: April 2025 pricing, non-reasoning
"gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cache_read": 0.025, "cache_write": 0.0}

# gpt-4o-mini: current pricing, non-reasoning
"gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075, "cache_write": 0.0}
```

### Experiment matrix and phasing

Run in four phases to maximize information per dollar. Abort if cumulative cost
exceeds $10 at any phase boundary.

**Phase A — Smoke test (3 runs, ~$0.15)**
Verify all 3 generation models produce non-empty output.
- models: [claude-haiku-4-5, gpt-4.1-nano, gpt-4o-mini]
- dim=256, n=5, function=embed only
- If a model emits empty descriptions or raises, mark it BROKEN and exclude
  from Phases B/C. Do not abort the mission.

**Phase B — Dimension sweep (up to 27 runs, ~$1.50)**
Identify minimum stable-separation embedding dimension.
- All non-BROKEN models from Phase A
- dims: [256, 512, 768]
- n=5 (fixed)
- functions: [embed, main, apply]
- "Stable separation" = embed converges at strictly lower budget than main
  in at least 2 of 3 dim values for that model. If already shown at 256,
  do not skip 512/768 — need the full curve for the recommendation.

**Phase C — n sweep (up to 18 runs, ~$2.00)**
Measure antipode robustness and reject rate as n grows.
- All non-BROKEN models from Phase A
- dim = minimum stable-separation dim identified in Phase B
- n: [5, 10, 15]
- functions: [embed, main] only (drop apply — save budget)
- If OpenAI rate limit fires on n=15: drop to n=12, then n=10, document
  the ceiling. Do not abort the phase.

**Phase D — Non-convergence validation (3–5 runs, ~$0.15)**
Empirically exercise the converged=False code path.
- Best (model, dim, n) from Phase C
- function: apply only
- budget_range=(8, 24), budget_step=8  ← tighter range forces ambiguity
- Expected: converged=False OR convergence at exactly 24 tokens (max budget)
- If converged=True at any budget ≤ 16: flag as quality concern in report.
  The 8-token description of apply() cannot be lossless.

### Per-run metrics to collect

```python
{
    "phase": "A|B|C|D",
    "generation_model": str,
    "embed_dim": int,
    "n": int,
    "function": str,
    "converged": bool,
    "token_count": int,
    "description": str,
    "confidence": float,
    "candidates_generated": int,
    "candidates_passing": int,       # candidates_generated - candidates_filtered
    "grammar_reject_rate": float,    # candidates_filtered / candidates_generated
    "budget_tried": list[int],
    "cache_hit_rate": float,         # cache_read_tokens / total_prompt_tokens
    "wall_clock_s": float,
    "cost_dollars": float,
}
```

### Driver script location

/tmp/mld_extended_validate.py

The driver must:
1. Inject new model rates into api.RATES before any calls.
2. Call api.reset_cost_totals() before each mld() call.
3. Capture time.monotonic() before/after each mld() call for wall_clock_s.
4. Compute cache_hit_rate from cost_totals() after each call:
   cache_hit_rate = cache_read_tokens / (input_tokens + cache_read_tokens + cache_creation_tokens)
   where the denominator is 0 → rate = 0.0 to avoid divide-by-zero.
5. Enforce $10 ceiling: check cumulative_cost before each phase and abort
   with a status line if exceeded.
6. Write all results to /tmp/mld_extended_findings.json (append-mode list).
7. Print each result as JSON to stdout for live monitoring.

### The generation prompt

Hand-craft a ≥4,096-token generation prompt for the driver. Requirements:
- Opens with: "You produce single-sentence descriptions of code."
- Encodes Daft Punk grammar: single imperative verb, 8–32 tokens, no hedging.
- Includes 20+ worked examples spanning budgets 8, 16, 24, 32 with explicit
  GOOD/BAD labels and the rule violated.
- Includes Origami vocabulary (the terms in CLAUDE.md vocabulary table)
  so the model uses domain-correct language for RF-edge code.
- Includes the structured output schema for when schema is passed.
- Pad to ≥4,096 tokens with controlled vocabulary lists and principles.
This prompt is the same prompt that will ship in tools/prompts/generate.md
(Mission 8). Write it to /tmp/mld_extended_prompt.txt as a side artifact.

### Report destination

/project/local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md

Required sections:
1. Experiment summary (models tested, dims, n values, total runs, total cost)
2. Phase A: Smoke test results (per model: WORKING / BROKEN)
3. Phase B: Dimension sweep table and separation analysis
4. Phase C: n-sweep table and reject rate analysis
5. Phase D: Non-convergence validation results
6. Cache hit rate analysis (did it ever fire? any model/dim combination?)
7. Wall clock comparison (which model is fastest end-to-end?)
8. **Recommendation table** — the permanent defaults:
   | Parameter | Recommended value | Rationale |
   |-----------|-------------------|-----------|
   | generation_model | ... | ... |
   | embed_dim | ... | ... |
   | n | ... | ... |
   | budget_step | ... | ... |
   | budget_range | ... | ... |
9. Deviations from experiment plan (rate limits hit, models broken, etc.)
10. Open questions for Mission 9

### Judgment calls you own

- If all three models produce similar quality at Phase B, prefer the cheapest.
- If gpt-4o-mini separation is better than gpt-4.1-nano by >1 budget tier,
  recommend gpt-4o-mini despite higher cost.
- If dim 256 already shows stable separation across all models, you may
  recommend 256 even if 512/768 shows marginal improvement (cost/quality tradeoff).
- If n=10 shows substantially better reject-rate diversity than n=5 without
  meaningful cost increase (< 2× cost), recommend n=10.
- "Substantially better" = reject rate ≥10% at n=10 vs <5% at n=5.
- The non-convergence path (Phase D): if apply() converges at ≤16 tokens,
  note this is a quality concern and recommend tightening the grammar filter
  to require both a verb AND a complement clause.

</specification>

<steps>
Phase 0 — Baseline

Step 1:
RUN: test -f /project/local/.env && grep -q '^OPENAI_API_KEY=' /project/local/.env && grep -q '^ANTHROPIC_API_KEY=' /project/local/.env && echo ok
EXPECT CONTAINS: ok
FAIL: HARD

Step 2:
RUN: /project/tools/.venv/bin/python3 -c "import anthropic, openai, numpy; print('ok')"
EXPECT CONTAINS: ok
FAIL: HARD

Step 3:
Write /tmp/mld_extended_validate.py per the specification. Hand-craft
the ≥4,096-token generation prompt inline. Inject model rates. Implement
all four experiment phases with per-run metric collection.
FAIL: HARD

Phase 1 — Setup

Step 4:
RUN: mkdir -p /project/local/sprints/tooling-v1/context
FAIL: HARD

Step 5:
RUN: wc -c /tmp/mld_extended_validate.py
EXPECT MATCHES: ^[0-9]+
FAIL: SOFT

Phase 2 — Execute

Step 6:
RUN: cd /project && /project/tools/.venv/bin/python3 /tmp/mld_extended_validate.py 2>&1 | tee /tmp/mld_extended_run.log
EXPECT CONTAINS: Phase A
EXPECT CONTAINS: Phase D
FAIL: RETRY

Step 7:
RUN: test -f /tmp/mld_extended_findings.json && /project/tools/.venv/bin/python3 -c "import json; d=json.load(open('/tmp/mld_extended_findings.json')); print('runs=' + str(len(d))); print('phases=' + str(sorted(set(r['phase'] for r in d))))"
EXPECT CONTAINS: Phase D
FAIL: HARD

Step 8:
RUN: /project/tools/.venv/bin/python3 -c "
import json
d = json.load(open('/tmp/mld_extended_findings.json'))
total_cost = sum(r['cost_dollars'] for r in d)
print(f'total_cost={total_cost:.4f}')
print('ceiling_ok=' + str(total_cost < 10.0))
"
EXPECT CONTAINS: ceiling_ok=True
FAIL: HARD

Phase 3 — Documentation

Step 9:
Read /tmp/mld_extended_findings.json and /tmp/mld_extended_run.log.
Analyze all four phases. Produce the recommendation table.
FAIL: HARD (analysis must complete before writing)

Step 10:
Write /project/local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md
with all 10 required sections per spec. Include the raw findings table
for all runs and the recommendation table.
FAIL: HARD

Phase 4 — Verify

Step 11:
RUN: grep -c '^## ' /project/local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md
EXPECT MATCHES: ^[8-9]$|^[1-9][0-9]+$
FAIL: SOFT

Step 12:
RUN: grep -q 'Recommended value' /project/local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md && echo found
EXPECT CONTAINS: found
FAIL: HARD

Phase 5 — Report
</steps>

<report>
Status: GREEN if all HARD steps pass and the recommendation table is present.
RED if cost exceeded $10 or the pipeline crashed for all three models.

Files written:
- /project/local/sprints/tooling-v1/context/mld-validation-extended-2026-04-24.md
- /tmp/mld_extended_validate.py (driver, not tracked)
- /tmp/mld_extended_findings.json (raw data, not tracked)
- /tmp/mld_extended_prompt.txt (prompt text, not tracked)

Include in the mission report:
- Phase A smoke test verdicts (WORKING / BROKEN per model).
- Phase B separation table — which dim first shows stable separation.
- Phase C reject-rate table — how reject rate and convergence quality
  change with n.
- Phase D non-convergence verdict — did apply() force converged=False?
- Total cost and ceiling headroom.
- The recommendation table (all five parameters with rationale).
- Any open questions for Mission 9.

No rollback needed — no source files modified.
</report>
---END MISSION 7-E---
