# M16 Bidirectional MLD Gate Decision

**Verdict:** DEFER
**Stable+Correct probes:** 1/5
**Date:** 2026-04-27
**Decision authority:** sprint architect (per design Decision 1)

## Per-Probe Judgment

### P1 — embed_for_store (pidgin/utils/api.py)

**Mechanical stability**

- converged: 3/6
- cluster sizes (converged): [6, 7, 6] — range 6-7 (delta=1)

**Stable verdict:** NOT STABLE — converged_count (3) is below the threshold of 4.

Skipped semantic judgment per gate procedure. Notes: of the 3 converged runs, every one
produced a different winning candidate; one of them is a truncated/malformed JSON string
that ends mid-sentence (`...embed_text(store_model,`). The cluster geometry is tight when
convergence does happen, but the description ("Call embed_text with store model, dimension,
and input text...") is too generic for the model to land on a single body.

### P2 — main (tools/mld/probe.py:MAIN_SRC, lines 27-33)

**Mechanical stability**

- converged: 5/6
- cluster sizes (converged): [6, 7, 7, 6, 6] — range 6-7 (delta=1)

**Stable verdict:** STABLE.

**Semantic correctness:** INCORRECT.

The reference body (the toy `MAIN_SRC` literal) is:

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text')
    args = parser.parse_args()
    print(args.text)
```

The 5 converged winning candidates are 5 *distinct* implementations. Three are truncated
JSON strings that never close (e.g. variant 1 ends after `text = args.text\n\n`). The two
runnable variants (variants 4 and 5) reach far past the toy and implement a pseudo-embed
pipeline:

```python
# variant 4 (runnable, but wrong)
def main():
    import argparse, json
    parser = argparse.ArgumentParser(); parser.add_argument('text')
    args = parser.parse_args(); text = args.text
    def embed(text): return [ord(c)/1000 for c in text]
    vector = embed(text)
    with open('vector.json', 'w') as f:
        json.dump({'vector': vector}, f)
```

Different signature side effects (file write vs stdout), different observable behaviour
(no embedding, no vector in the toy). The description ("Parse CLI args, read text, embed
it, write JSON vector.") drove the model toward the *production* tools/embed.py:main
behaviour rather than the toy probe body — a faithful reflection of the description, but
not equivalent to the reference. Probe-source mismatch acknowledged in probes.json.

### P3 — apply (tools/mld/probe.py)

**Mechanical stability**

- converged: 6/6
- cluster sizes (converged): [8, 10, 10, 9, 9, 8] — range 8-10 (delta=2)

**Stable verdict:** STABLE (delta=2 is exactly at the limit).

**Semantic correctness:** INCORRECT (AMBIGUOUS counts as INCORRECT).

The reference body:

```python
def apply(state, delta, strict=False):
    out = dict(state)
    for key, value in delta.items():
        if strict and key not in out:
            raise KeyError(key)
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out
```

Two winning variants tied at n=3 each:

- Variant 1 (n=3) is a truncated JSON string ending after `raise KeyError(key)\n` — not
  runnable Python.
- Variant 2 (n=3) is a verbatim match to the reference (same signature, same strict
  semantics, same None→delete, same return).

Half of the converged runs landed on the complete reference equivalent; the other half
landed on a truncated cousin that describes the same algorithm but is not executable.
The modal winning candidate is not unambiguous: this is exactly the AMBIGUOUS case the
gate criterion specifies as INCORRECT.

The b=50 budget is responsible for the truncations (`syn_valid=0` at b=50 for this
probe; `syn_valid=10` at b=200). At b=200 all three runs land on the complete reference
match — which is the better signal but not what the strict gate criterion captures here.

### P4 — merge (tools/mld/probe.py)

**Mechanical stability**

- converged: 5/6
- cluster sizes (converged): [8, 8, 8, 7, 7] — range 7-8 (delta=1)

**Stable verdict:** STABLE.

**Semantic correctness:** CORRECT.

The reference body:

```python
def merge(a, b, prefer_b=True):
    return {**a, **b} if prefer_b else {**b, **a}
```

All 5 converged runs picked the identical winning candidate, byte-equal to the reference.
`syn_valid=10/10` in every record. Same signature, same return type, same precedence
semantics on `prefer_b`, no side effects, no error semantics to mismatch. Trivially
correct.

### P5 — antipode_test (pidgin/pipeline/geometry.py)

**Mechanical stability**

- converged: 5/6
- cluster sizes (converged): [6, 6, 7, 6, 6] — range 6-7 (delta=1)

**Stable verdict:** STABLE.

**Semantic correctness:** INCORRECT.

`syntactically_valid_count` is 0 across **all 30 records** (every budget, every run).
Every one of the 5 distinct winning candidates is a truncated JSON string that does not
parse as Python — they all stop mid-implementation (mid-`centroid = [...]`, mid-`for vec
in vectors`, mid-`def dot(a, b):\n        return`).

The reference (geometry.py:antipode_test, lines 31-69) computes a centroid via a helper,
computes cosine similarity per vector via a helper, derives an adaptive threshold from
the mean similarity when `threshold == 0.0`, and returns `(len(kept), kept)`. Several
candidates would *eventually* compute this — but none of them get there before the
budget cutoff. **None are runnable, so none can be observably equivalent to the reference.**

This probe sat at b=50/200; the function is too complex to fit in either window. Higher
budgets (≥800) would likely change the answer.

## Rationale

The cluster geometry signal is *clean*. Every probe (including P1 in the runs that did
converge) produces tight clusters, with cluster_size deltas of 1 across the converged
runs. This is the strongest data point in the experiment: **the antipode geometry is
well-behaved when applied to candidate code bodies.** Convergence detection in code
embedding space matches the convergence detection on description embeddings that V2
already established.

The semantic-correctness signal is dominated by **token-budget truncation**, not by code
embedding geometry. Three of the four STABLE probes (P2, P3, P5) are bottlenecked on
budget-induced truncation. P3 in particular shows what success could look like: at
b=200, all three runs land on a verbatim match to the reference. At b=50, the same
algorithm is correct but the JSON envelope clips the closing brace and the body becomes
unparseable. The "winning candidate" at b=50 is the cluster centroid of three
*truncated* strings that all start the same way — geometrically valid, semantically
broken.

What surprised us: P4 succeeded in 5/5 runs because the function is small enough to fit
in any budget. P3 split exactly down the middle (3 truncated, 3 complete) because the
function is right at the b=50 boundary. P5 failed everywhere because it never fits in
b=200. The pattern is **complexity vs budget**, not "code embeddings don't cluster."

What the code-embedding space implies: when candidates are runnable code, they cluster
tightly around their semantic centroid (P4), and the dominant cluster is the one closest
to the reference. The bidirectional MLD hypothesis — that you can drive a description
through a code-embedding antipode loop and converge — looks **promising for short
functions and broken for long ones at current budgets**. Phase 5 (M17–M19) cannot
proceed on a 1/5 success rate, but the experiment also shouldn't be read as a refutation
of the underlying geometry: it's a refutation of *fixed budgets b=50/200* as the
operating regime.

The gate is strict, and it must remain strict. P3's split between "right answer" and
"truncated right answer" is exactly the AMBIGUOUS case Decision 1 was designed to catch.
We DEFER.

## Next Action

**DEFER.** Phase 5 (M17–M19) does not run.

Recommended follow-ups before retrying the gate:

1. **Raise the token budget** for the candidate-generation step on long-bodied probes.
   The data points strongly to b=800 or b=1600 as the right operating regime for
   antipode_test-class functions. The fact that P4 (one-liner) succeeds at b=50 while
   P5 (~40-line function with helpers and an adaptive threshold) fails at b=200 says
   the budget is the bottleneck, not the embedding geometry.
2. **Schema-level repair** for the JSON envelope. The truncations are uniformly the
   closing `"}` of `{"implementation":"..."}`. A streaming JSON parser with tail
   recovery, or a structured-output tool-use call (like the M9 Anthropic gate path),
   would sidestep this entirely.
3. **Re-probe P1 with a less generic description.** P1's 3/6 convergence is the only
   one that isn't budget-bound — the description "Call embed_text with store model,
   dimension, and input text" admits too many surface forms. M3's converged
   description there was already flagged ambiguous (gate_verdict=ambiguous in the
   source).
4. **Reconsider the P2 probe definition.** The probes.json source note acknowledges
   that the M3 description matches `tools/embed.py:main`, not the toy `MAIN_SRC`. The
   description is driving the model toward the wrong reference. Either re-describe
   the toy or move the probe to the production main.

After (1) and (2) ship, re-run the bidirectional probe suite. If ≥4/5 STABLE+CORRECT,
re-issue the gate.
