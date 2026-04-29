# Adaptive Candidate Counts

V2 runs a fixed number of candidates per convergence test: 5 calls × 3 drafts = 15 candidates. This is sufficient when convergence is clear (4/5 or 5/5 agreement) but leaves uncertainty unresolved when convergence is marginal (3/5).

## The Problem

A 3/5 convergence means 3 candidates agreed and 2 didn't. Is that genuine consensus with noise, or a borderline case where the description is nearly but not quite lossless? With only 5 data points, the algorithm can't distinguish between these. The current pipeline returns converged=True (majority wins) but the confidence score is lower. The operator sees a lower confidence and doesn't know whether 5 more candidates would resolve to 5/5 or collapse to 2/5.

## The Proposal

Adaptive candidate generation based on initial convergence ratio:

- **5/5 or 4/5 agreement:** Accept. Convergence is clear. No additional candidates needed.
- **3/5 agreement:** Run 5 more calls (15 more candidates via three-draft). Retest convergence against the full set of 30 candidates. If the expanded set shows clear convergence (e.g., 8/10 data points in the dominant cluster), accept. If the expanded set remains split, flag as non-convergent.
- **Below 3/5:** Flag as non-convergent immediately. The description is too ambiguous or the function is too complex for the current budget tier. Escalate to a higher budget or flag for human review.

## Cost Analysis

5 additional GPT-4.1 nano calls at ~$0.006 each = $0.03. One additional embedding batch for 15 candidates = negligible. This triggers only on 3/5 convergence, which in V2 empirical data occurred on 0/4 probes (all were 5/5). In V1 data across 54 runs, the frequency of marginal convergence was not tracked at this granularity — the algorithm reported converged/not-converged without the ratio. The v0.2 pipeline should track the ratio to build empirical data on how often adaptive expansion triggers.

## Implementation Notes

The adaptive expansion is a loop around the existing convergence test, not a new code path. Pseudocode:

```
candidates = generate(n_calls=5)  # 15 candidates via three-draft
ratio = convergence_test(candidates)

if ratio >= 4/5:
    return converged, candidates
elif ratio >= 3/5:
    more = generate(n_calls=5)  # 15 more
    all_candidates = candidates + more
    ratio = convergence_test(all_candidates)
    if ratio >= 7/10:
        return converged, all_candidates
    else:
        return non_convergent, all_candidates
else:
    return non_convergent, candidates
```

The thresholds (4/5, 3/5, 7/10) are design-time defaults. They should be configurable and empirically validated. The 7/10 threshold for the expanded set is more lenient than 4/5 because 30 candidates have more natural variation than 15 — a stricter threshold on a larger set may reject descriptions that are genuinely convergent with normal sampling noise.

## Relationship to Batch Dispatch

Adaptive expansion interacts well with batch dispatch. The initial 5 calls are part of the bulk batch. If any functions come back at 3/5, their expansion calls are collected into a second batch. Two batch round trips instead of one, triggered only when needed.
