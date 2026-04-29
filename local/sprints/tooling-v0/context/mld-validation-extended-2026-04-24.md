# MLD Validation — Extended Experiment
**Date:** 2026-04-24
**Mission:** 7-E
**Total runs:** 47
**Total cost:** $0.3345 (ceiling headroom: $9.67)

---

## 1. Experiment Summary

Three generation models tested head-to-head (claude-haiku-4-5, gpt-4.1-nano,
gpt-4o-mini) across embedding dimensions [256, 512, 768] and n values [5, 10, 15].
The experiment ran four phases: smoke test, dimension sweep, n-sweep, and
non-convergence validation. All models passed Phase A. The experiment completed
without hitting the $10 ceiling.

| Parameter | Values tested |
|-----------|--------------|
| generation_model | claude-haiku-4-5, gpt-4.1-nano, gpt-4o-mini |
| embed_dim | 256, 512, 768 |
| n | 5, 10, 15 |
| functions | embed() (simple), main() (complex), apply() (ambiguous) |
| budget_range | (8, 32) — except Phase D: (8, 24) |
| budget_step | 8 |
| validation_model | claude-haiku-4-5 (fixed) |

Driver script: `/tmp/mld_extended_validate.py` (18,856 bytes)
Prompt: `/tmp/mld_extended_prompt.txt` (18,197 chars, ~4,549 tokens)

---

## 2. Phase A: Smoke Test Results

All three models produced non-empty output at dim=256, n=5 on embed().

| Model | Verdict | tok | conf | cache_hit | wall_clock | cost |
|-------|---------|-----|------|-----------|-----------|------|
| claude-haiku-4-5 | WORKING | 16 | 0.67 | 0.969 | 6.7s | $0.0163 |
| gpt-4.1-nano | WORKING | 16 | 0.67 | 0.477 | 3.9s | $0.0040 |
| gpt-4o-mini | WORKING | 16 | 0.67 | 0.413 | 4.2s | $0.0057 |

All three proceed to Phases B, C, D.

---

## 3. Phase B: Dimension Sweep

Fixed: n=5. Functions: embed, main, apply. Dims: [256, 512, 768].

### Convergence table

| model | dim | fn=embed | fn=main | fn=apply | stable_separation |
|-------|-----|----------|---------|----------|-------------------|
| claude-haiku-4-5 | 256 | ✓ @8 | ✗ | ✗ | NO |
| claude-haiku-4-5 | 512 | ✗ | ✗ | ✗ | NO |
| claude-haiku-4-5 | 768 | ✗ | ✗ | ✗ | NO |
| gpt-4.1-nano | 256 | ✓ @16 | ✓ @8 | ✓ @16 | YES* |
| gpt-4.1-nano | 512 | ✓ @16 | ✓ @8 | ✓ @16 | YES* |
| gpt-4.1-nano | 768 | ✓ @16 | ✓ @8 | ✓ @16 | YES* |
| gpt-4o-mini | 256 | ✓ @16 | ✓ @16 | ✓ @16 | NO (tie) |
| gpt-4o-mini | 512 | ✓ @16 | ✓ @8 | ✓ @16 | YES* |
| gpt-4o-mini | 768 | ✓ @16 | ✓ @8 | ✓ @16 | YES* |

*Inverted from initial expectation: main() converges at LOWER budget than embed().
See analysis below.

### Separation analysis

The initial assumption was that embed() (simpler function) would converge at a
lower token budget than main() (complex function). The data inverts this:
main() consistently converges at 8 tokens, embed() at 16 tokens.

**Root cause (judgment):** The antipode test measures embedding cloud tightness,
not semantic complexity. At 8 tokens, all descriptions of main() converge on
the same concept — "parse CLI args + embed text" — leaving little surface area
for divergence. At 8 tokens, descriptions of embed() have more surface area
("call API", "get vector", "return embedding") → looser cloud → non-convergence
at 8 tokens, convergence at 16 where the cloud tightens.

This is algorithmically correct. The MLD algorithm finds the minimum budget where
descriptions become semantically stable, not the minimum budget for the conceptually
simplest function.

### Haiku failure pattern

claude-haiku-4-5 non-converged 8 out of 9 times in Phase B, with convergence only
at dim=256 fn=embed. The same configuration (dim=768, n=5) that failed in Phase B
succeeded in Phase C (two separate runs). This is high-variance stochastic behavior,
not a systematic failure tied to dimension. haiku is not suitable as the default
generation model.

### Dimension discrimination

gpt-4.1-nano and gpt-4o-mini show identical convergence patterns across all three
dims. There is no quality difference between dim=256, 512, and 768 for these
models at n=5. Embedding dimension does not affect convergence or description
quality in this experiment. Recommend minimum viable dim=256.

---

## 4. Phase C: n-Sweep and Reject Rate

Fixed: dim=768 (chosen by driver as "best" dim from Phase B). Functions: embed, main.
n values: [5, 10, 15].

### Convergence and description quality by n

| model | n | fn=embed | fn=main | reject_rate |
|-------|---|----------|---------|-------------|
| claude-haiku-4-5 | 5 | ✓ @16 | ✓ @8 | 0.00 |
| claude-haiku-4-5 | 10 | ✗ | — | 0.00 |
| gpt-4.1-nano | 5 | ✓ @16 | ✓ @8 | 0.00 |
| gpt-4.1-nano | 10 | ✓ @16 | ✓ @8 | 0.00 |
| gpt-4.1-nano | 15 | ✓ @16 | ✓ @8 | 0.00 |
| gpt-4o-mini | 5 | ✓ @8 | ✓ @8 | 0.00 |
| gpt-4o-mini | 10 | ✓ @16 | ✓ @8 | 0.00 |
| gpt-4o-mini | 15 | ✓ @8 | ✓ @8 | 0.00 |

### Grammar filter reject rate: 0% across all runs

The grammar filter rejected zero candidates in all 47 runs. Two interpretations:

1. The 4,549-token prompt (with 20+ GOOD/BAD examples and explicit grammar rules)
   is highly effective at eliciting grammatically compliant output.
2. The grammar filter rules are insufficiently strict — accepting outputs that are
   syntactically valid but semantically incomplete (see Phase D and Section 10).

The empirical finding is that with a well-crafted coaching prompt, generation models
produce grammar-passing output nearly 100% of the time. The filter adds safety
overhead but does not reduce the candidate pool in practice.

### n-value recommendation

No quality improvement was observed when increasing n from 5 to 10 or 15 for
gpt-4.1-nano or gpt-4o-mini. Convergence patterns, description content, and
confidence scores were stable across all n values tested. The antipode test
achieves stable convergence at n=5.

**Exception:** haiku failed at n=10 (Phase C, embed). This is further evidence
of haiku's high variance rather than an n-value effect.

---

## 5. Phase D: Non-Convergence Validation

Configuration: gpt-4.1-nano, dim=768, n=10, budget_range=(8,24), budget_step=4.
Function: apply() (genuinely ambiguous — requires both merge and None-deletion
to describe losslessly).

| Run | converged | tok | confidence | description |
|-----|-----------|-----|-----------|-------------|
| 1 | True | 8 | 1.00 | "Update a copy of state with delta," |
| 2 | True | 12 | 0.75 | "Merge delta into a copy of state, delete None keys," |

**Finding: apply() converged at ≤16 tokens in both runs. Quality concern flagged.**

The 8-token description "Update a copy of state with delta," is semantically
incomplete — it drops the None-key deletion behavior and the strict-mode KeyError
raise. A lossless description of apply() requires both behaviors, which needs ≥18
tokens.

The converged=False code path in mld.py was NOT exercised empirically. The path
is correct by code inspection (mld.py:470–495) but remains unvalidated by data.

**Root cause:** The grammar filter accepts trailing commas and mid-sentence
fragments (e.g., "Merge delta into a copy of state, delete None keys," ends with
a comma but passes as grammatically valid). The convergence algorithm finds a
tight cluster around these incomplete forms and declares convergence.

This is a grammar filter gap, not an algorithm gap. The algorithm correctly reports
the minimum budget at which the description cloud stabilizes — but stability of an
incomplete description is not losslessness.

---

## 6. Cache Hit Rate Analysis

| Model | avg cache_hit_rate | min | max | runs |
|-------|-------------------|-----|-----|------|
| claude-haiku-4-5 | 0.952 | 0.900 | 0.984 | 13 |
| gpt-4.1-nano | 0.496 | 0.392 | 0.745 | 18 |
| gpt-4o-mini | 0.443 | 0.000 | 0.486 | 16 |

**Cache IS working.** Mission 7's 0% cache hit rate was caused by the prompt being
only 2,066 tokens — below Anthropic's 4,096-token minimum for Haiku prompt caching.
The 7-E prompt at 4,549 tokens (DP-4 compliant) yields 95.2% cache hit rate for
haiku across 13 runs.

**This validates DP-4:** "Pad all cached prompts to ≥4096 tokens with useful context."
The decision was correct. Mission 8 must maintain this minimum when writing
`tools/prompts/generate.md`.

**OpenAI models:** ~47% hit rate reflects OpenAI's automatic prompt caching for
repeated requests. No explicit cache_control configuration is needed; the OpenAI
API caches the system prompt automatically after the first call.

---

## 7. Wall Clock Comparison

| Model | avg (s) | min (s) | max (s) | 13+ runs |
|-------|---------|---------|---------|----------|
| claude-haiku-4-5 | 10.3 | 5.2 | 20.2 | yes |
| gpt-4.1-nano | 5.1 | 3.6 | 11.5 | yes |
| gpt-4o-mini | 4.2 | 3.2 | 7.3 | yes |

gpt-4o-mini is the fastest model (4.2s avg), gpt-4.1-nano is 1.2× slower (5.1s avg),
haiku is 2.5× slower (10.3s avg). The haiku slowness is attributed to more API
round-trips when non-convergence triggers retries and fallback behavior.

For interactive use (e.g., /technologic --fix on a single function), the 3–7 second
wall clock of gpt-4.1-nano is acceptable. For batch indexing of a large codebase,
gpt-4o-mini's marginally faster response may matter.

---

## 8. Recommendation Table

| Parameter | Recommended value | Rationale |
|-----------|-------------------|-----------|
| generation_model | `gpt-4.1-nano` | 18/18 convergences across Phases B+C. Cheapest model ($0.0043/run avg). Consistent descriptions. haiku is unreliable (high stochastic variance); gpt-4o-mini is 1.5× more expensive with no quality advantage observed. |
| embed_dim | `256` | No convergence or description quality difference between 256, 512, 768 for gpt-4.1-nano or gpt-4o-mini. Smallest dim = cheapest embedding calls. Use text-embedding-3-small with `dimensions=256`. |
| n | `5` | No improvement at n=10 or n=15 for either OpenAI model. Antipode test achieves stable convergence at n=5. Reject rate is 0% with a well-crafted prompt — more candidates do not improve filter diversity. |
| budget_step | `8` | Standard. With budget_range=(8,32), step=8 produces 4 tiers: [8,16,24,32]. Sufficient resolution. |
| budget_range | `(8, 32)` | Observed convergence range: simple functions at 8–16 tok, complex functions at 8 tok (inverted), ambiguous at 8–16 tok. The 32-token ceiling gives headroom for functions with multi-clause descriptions not tested here. |

**The mld.py defaults that must change in Mission 9:**
- `generation_model="gpt-5-nano"` → `"gpt-4.1-nano"` (gpt-5-nano is a reasoning model; emits empty strings at low max_tokens)
- `embed_dim=128` → `256` (DP-2 overridden by empirical data; 128 showed false-positive convergence in M7)
- `n=10` → `5` (no quality benefit; halves generation cost)

---

## 9. Deviations from Experiment Plan

| # | Deviation | Impact |
|---|-----------|--------|
| 1 | Phase C driver chose dim=768 as "best" dim despite gpt-4.1-nano showing identical results at all three dims. Should have been dim=256 (cheapest). | Negligible — 768 and 256 behave identically. No correctness impact. |
| 2 | Phase D used budget_step=4 (budgets [8,12,16,20,24]) rather than the spec's budget_step=8. | Minor — provided higher resolution for the non-convergence test. apply() converged at 8 and 12. Both ≤16, so quality concern is correctly flagged regardless. |
| 3 | haiku Phase C chose dim=768 (same as OpenAI models) despite Phase B showing haiku non-converged at dim=768. haiku at dim=768 n=5 converged in Phase C (different result from identical Phase B config). | Haiku is non-deterministic at this operating point. This deviation confirms the high-variance finding rather than creating a methodological error. |
| 4 | Grammar filter reject rate is 0% for all 47 runs. | The "substantially better reject rate" heuristic for n recommendation (reject_rate ≥10% at n=10 vs <5% at n=5) did not apply. n=5 recommendation relies on convergence quality stability instead. |
| 5 | converged=False empirical path not exercised. apply() converged in both Phase D runs. | The code path is verified by inspection. To empirically validate: use a function with multiple equally-plausible interpretations AND a very tight budget_range. Recommended test case for Mission 9. |

---

## 10. Open Questions for Mission 9

### Must-fix before Mission 9 ships

**Q1: Grammar filter — truncation and mid-sentence detection.**
Observed descriptions: "Call the OpenAI embeddings API with the given model and dimension, trunc" (literal truncation artifact), "Parse CLI arguments, read text input," (trailing comma), "Update a copy of state with delta," (incomplete). These pass the grammar filter. Mission 9 must add:
- Reject if last non-whitespace char is `,` `;` `:` or known dangling conjunction (`and`, `or`, `but`, `with`, `for`).
- Reject if description ends with truncation marker (`trunc` as a complete word, or mid-word cutoff).
- Optionally: reject if token count is within 2 of max_tokens (likely truncated by API).

**Q2: mld.py defaults — three values must change.**
See Section 8. Patch in Mission 9: `generation_model`, `embed_dim`, `n`.

**Q3: RATES table — add gpt-4.1-nano.**
`utils/api.py` RATES dict does not include `gpt-4.1-nano`. The driver injected it inline. Mission 9 must add it permanently so cost tracking is accurate.

**Q4: Cache hit rate investigation resolved.**
M7's 0% cache hit was a false alarm — prompt was below Haiku's 4096-token minimum.
The prompt written for 7-E (4,549 tokens) achieves 95.2% haiku cache hit rate.
Mission 8 must produce a ≥4096-token `generate.md`. This is confirmed working.

### Lower priority

**Q5: Inverted complexity assumption.**
The initial hypothesis (simple functions converge at lower budgets) is empirically
false. The convergence budget reflects description cloud tightness, not semantic
complexity. Documentation in Mission 9's SKILL.md should use "minimum stable budget"
rather than "complexity estimate."

**Q6: converged=False path — better test case.**
apply() is not ambiguous enough. A function with multiple valid interpretations at
the same abstraction level is needed. Candidate:
```python
def merge(a, b, prefer_b=True):
    return {**a, **b} if prefer_b else {**b, **a}
```
At 8 tokens: "Merge two dicts" or "Combine dicts with priority control" — both
valid, semantically different, consistently short → may force non-convergence.

**Q7: gpt-4o-mini as a quality/speed upgrade path.**
gpt-4o-mini was marginally faster (4.2s vs 5.1s) and produced good descriptions
but costs 1.5× more than gpt-4.1-nano. For operators who want faster /technologic
runs, expose `generation_model` as a CLI flag. Default to gpt-4.1-nano; document
gpt-4o-mini as a known working alternative.
