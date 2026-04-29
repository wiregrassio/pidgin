# Calibration Findings

Source: calibration-data.json + calibration-vectors.npz + analysis-results.txt
Experiment: 126 functions × 25 calls × 4 temperatures × 3 drafts = 12,600 API calls
Vectors: 37,638 embeddings (text-embedding-3-small, 256-dim)

## Finding 1: Draft Hypothesis is Dead

Draft 3 has HIGHER variance than draft 1 at every temperature.

| Temp | Draft 1 mean sv | Draft 3 mean sv | Delta |
|------|----------------|----------------|-------|
| 0.3  | 0.0626         | 0.0941         | +50%  |
| 0.7  | 0.0964         | 0.1225         | +27%  |
| 1.0  | 0.1179         | 0.1392         | +18%  |
| 1.5  | 0.1690         | 0.1879         | +11%  |

The shorter token budget on draft 3 forces each call to make different
choices about what to include, which INCREASES diversity. Draft 1 (120
tokens, verbose) is the most convergent because there's room to say
everything.

**Action: Generate 1 draft per call. Drop drafts 2 and 3. This kills
2/3 of generation token spend.**

## Finding 2: Temperature 0.3 Wins

2.7x tighter clusters than t=1.5. Mixing temperatures hurts (sv goes
from 0.0626 to 0.1210 when pooling all temps).

**Action: Lock temperature at 0.3. Do not mix temperatures.**

## Finding 3: Pooling Drafts Hurts

Mean sv pooled (all 3 drafts): 0.1075
Mean sv draft_1 only: 0.0626

Every single function gets worse when you include drafts 2 and 3.

**Action: Use draft_1 vectors only for convergence testing and centroid
selection.**

## Finding 4: Threshold Calibration

At t=0.3, draft_1, N=25:

| Threshold | Converged | Rate |
|-----------|-----------|------|
| sv < 0.02 | 18/126   | 14%  |
| sv < 0.05 | 60/126   | 48%  |
| sv < 0.08 | 90/126   | 71%  |
| sv < 0.10 | 102/126  | 81%  |
| sv < 0.12 | 116/126  | 92%  |
| sv < 0.15 | 121/126  | 96%  |

Functions above sv=0.15 are all complex multi-purpose constructs:
MLDResult (0.28), generate (0.19), classify_batch_results (0.19),
EditOp (0.18), AssembledPrompt (0.15).

**Action: Threshold at sv < 0.10. Functions above 0.15 are flagged
for review — the function itself is likely the problem, not the pipeline.**

## Finding 5: Sample Size

Mean absolute deviation from N=25 reference:

| N  | Mean dev | Max dev |
|----|----------|---------|
| 3  | 0.0248   | 0.2614  |
| 5  | 0.0169   | 0.2358  |
| 7  | 0.0127   | 0.1582  |
| 10 | 0.0095   | 0.1324  |
| 15 | 0.0063   | 0.0667  |
| 20 | 0.0038   | 0.0521  |

At N=10, mean deviation is 0.0095 — an order of magnitude smaller than
the 0.10 threshold. Max deviation 0.1324 means rare worst cases could
flip a borderline function, but the threshold has enough margin.

**Action: Default to 10 calls per function. This produces 10 vectors
(1 draft each), sufficient for reliable sv computation.**

## Finding 6: Body Length Doesn't Predict Convergence

Correlation sv vs body_length: 0.169 (weak).

run_incremental_mld_pipeline (4808 chars) has sv=0.0200.
MLDResult (913 chars) has sv=0.2801.

Semantic clarity matters. Size doesn't.

## Implementation Summary

The convergence test becomes one line:

```python
converged = spherical_variance(draft_1_vectors) < 0.10
```

No draft comparison. No monotonicity test. No temperature mixing.
No threshold-free verdict. One number, one comparison, empirically
calibrated on 37,638 data points.

Pipeline changes:
- Generate 1 draft per call (not 3) → changes converge.xml response schema
- Temperature 0.3 (hardcoded) → changes generation call
- 10 calls default (not 5) → changes ADAPTIVE_MAX_BATCHES
- convergence_verdict() replaced with sv < 0.10 → changes geometry.py, batch.py
- _stratify() data collection can stay for telemetry but doesn't drive decisions
