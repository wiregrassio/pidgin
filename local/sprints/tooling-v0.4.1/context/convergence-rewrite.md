# Convergence Rewrite

## Current State (Broken)

The pipeline currently has `convergence_verdict()` in geometry.py which
checks whether sv1 > sv2 > sv3 (variance decreasing across draft tiers).
The calibration data proved this is backwards — draft 3 always has higher
variance. Result: near-0% convergence on real code.

The descriptions are still good (queries return correct results at 0.75+
similarity). The convergence FLAG is wrong, not the description selection.

## Target State

### geometry.py

Replace `convergence_verdict()` with:

```python
CONVERGENCE_THRESHOLD = 0.10

def is_converged(vectors: list[list[float]], threshold: float = CONVERGENCE_THRESHOLD) -> tuple[bool, float]:
    """Single-number convergence test.
    Returns (converged, sv) where converged = sv < threshold."""
    sv = spherical_variance(vectors)
    return sv < threshold, sv
```

Delete `convergence_verdict()`. Keep `spherical_variance()` and `centroid()`.

### converge.xml / response schema

Current schema requires draft_1, draft_2, draft_3. Change to single draft:

```json
{
  "type": "object",
  "properties": {
    "description": {"type": "string"}
  },
  "required": ["description"],
  "additionalProperties": false
}
```

Update converge.xml role section: remove "produce three drafts at
increasing refinement." Replace with "produce one concise description."

### batch.py

- Change generation: 1 draft per call, not 3
- Set temperature=0.3 on all generation calls
- Change ADAPTIVE_MAX_BATCHES from 5 to 10 (10 calls × 1 draft = 10 candidates)
- Replace convergence check: `is_converged(vectors)` instead of `convergence_verdict(d1, d2, d3)`
- Remove or simplify `_stratify()` — it can stay for telemetry but
  doesn't drive convergence decisions
- FunctionMldResult: remove sv1/sv2/sv3 fields, add single `sv: float`
  and `converged: bool` driven by the threshold

### mld.py

Same change as batch.py: single-draft generation, is_converged() check.

### _extract_drafts()

Simplify four-shape fallback. With a single "description" field, shape 1
becomes `{"description": "..."}`. Keep fallback for robustness but the
primary shape is trivial.

## What NOT to Change

- centroid() — still used to pick the winner (nearest to centroid)
- embed_text / embed_for_store — unchanged
- Nest storage format — unchanged
- Query logic — unchanged
- Batch chunking, incremental writes, graceful shutdown — unchanged (M1-M3 from v0.4)

## Testing

After the rewrite:
1. `pidgin index . --sync --verbose` on the pidgin repo
2. Compare convergence rates to the calibration loading (should be ~81%)
3. `pidgin query "compute spherical variance"` should return 0.83+ (matches calibration)
4. The 5 divergent functions should still be divergent (same sv values)
