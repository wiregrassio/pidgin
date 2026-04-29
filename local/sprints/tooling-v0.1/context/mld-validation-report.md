# MLD Validation Report
**Missions 7 + 7-E · 2026-04-24 · 54 runs · $0.49 total**

---

## What this is

The MLD (Minimum Lossless Description) pipeline generates N candidate descriptions
of a function at each token budget, embeds them, runs a geometric convergence test,
and picks the shortest budget where the embedding cloud "settles." This report shows
what the candidates actually said at each budget tier across three probe cases, what
the geometric convergence looked like, and where the pipeline made wrong calls.

---

## The three probe cases

| Case | Model | Function | Dim | N | Budget range | Result |
|------|-------|----------|-----|---|-------------|--------|
| 1 | claude-haiku-4-5 | `embed()` | 256 | 5 | (8, 32) | converged @ tok=16 ✓ |
| 2 | claude-haiku-4-5 | `main()` | 256 | 5 | (8, 32) | converged @ tok=16 ✓ |
| 3 | gpt-4.1-nano | `apply()` | 768 | 10 | (8, 24) | converged @ tok=8 ⚠ |

Case 3 converged correctly by the algorithm's rules but produced a semantically
incomplete description. That's the quality gap this report documents.

---

## Case 1 — `embed()` with haiku (converged @ tok=16)

```python
def embed(text: str, dim: int = 1536, model: str = "text-embedding-3-small") -> list[float]:
    """..."""
    text = text[:30_000]
    resp = openai.embeddings.create(model=model, input=[text], dimensions=dim)
    return resp.data[0].embedding
```

### Budget=8 — DEGENERATE CLOUD — converged=False

avg cosine similarity: **1.0000** (all vectors identical)

```
[1] "Call the OpenAI embeddings API"
[2] "Call the OpenAI embeddings API"
[3] "Call the OpenAI embeddings API"
[4] "Call the OpenAI embeddings API"
[5] "Call the OpenAI embeddings API"
```

At 8 tokens, haiku produces one phrase, repeated verbatim. The embedding cloud is
a single point. The antipode formula returns `antipode == centroid == nearest`,
so `neighbor_idx == nearest_idx` → `converged=False`. Correct behavior.

### Budget=16 — TWO CLUSTERS — converged=True ✓

avg cosine similarity: **0.8239** · min: **0.7203**

```
[1] "Call the OpenAI embeddings API with the given model and dimensions, trunc"  ← centroid_nearest
[2] "Call the OpenAI embeddings API with the given model and return the float"
[3] "Call the OpenAI embeddings API with the given model and dimensions, trunc"  ← centroid_nearest
[4] "Call the OpenAI embeddings API with the given model and dimensions, trunc"  ← centroid_nearest
[5] "Call the OpenAI embeddings API with the given model and return the vector"
```

The cloud splits into two semantic clusters:
- **"trunc" cluster** (3 candidates): describes the truncation side-effect
- **"return the vector" cluster** (2 candidates): describes the return value

The centroid sits closer to the "trunc" cluster (3 > 2). Antipode points toward
"return the vector." Its nearest neighbor is in the "trunc" cluster → different →
`converged=True`.

**Winner picked:** `"Call the OpenAI embeddings API with the given model and dimensions, trunc"`

This is a grammar filter miss. `"trunc"` is haiku running out of tokens mid-word
while trying to say "truncating." The full thought at budget=24 is:
`"...truncating input text to thirty thousand characters,"` — which is accurate
(the function does truncate at 30,000 chars) but ends with a trailing comma.

### Budget=24 — TIGHTER, ONE CLUSTER — converged=True

avg cosine similarity: **0.8562** · min: **0.6561**

```
[1] "Call the OpenAI embeddings API with the given model and return the vector."
[2] "Call the OpenAI embeddings API with the given model and dimensions, truncate input text to thirty thousand characters,"
[3] "Call the OpenAI embeddings API with the given model and dimensions, truncate input text to thirty thousand characters,"
[4] "Call the OpenAI embeddings API with the given model and dimensions, truncating text to thirty thousand characters, and"  ← centroid_nearest
[5] "Call the OpenAI embeddings API with the given model and dimensions, truncating input text to thirty thousand characters,"
```

One outlier [1] separates from the "truncating..." majority. Pipeline converges
but picks budget=16 (minimum), not budget=24.

### Budget=32 — DEGENERATE AGAIN — converged=False

avg cosine similarity: **0.9017** · min: **0.7542**

```
[1] "...truncating text to thirty thousand characters, and return the embedding vector."  ← centroid_nearest
[2] "...truncating text to thirty thousand characters, and return the embedding vector."  ← centroid_nearest
[3] "...truncating text to thirty thousand characters, and return the embedding vector."  ← centroid_nearest
[4] "Call the OpenAI embeddings API with the given model and return the float vector."
[5] "...truncating text to thirty thousand characters, and return the embedding vector."  ← centroid_nearest
```

4/5 candidates are identical again → near-degenerate → `converged=False`. The full
description at 32 tokens is actually good (`"...truncating text...and return the embedding
vector."`) but the pipeline can't select it because the antipode test fails on
near-degenerate clouds just like on fully degenerate ones.

### Summary for Case 1

```
budget=8   avg_sim=1.0000  ░░░░░░░░░░  converged=False  (degenerate — all same)
budget=16  avg_sim=0.8239  ████████░░  converged=True ✓ (two clusters, min selected)
budget=24  avg_sim=0.8562  █████████░  converged=True   (dominated cluster)
budget=32  avg_sim=0.9017  █████████░  converged=False  (near-degenerate again)
```

Pipeline picks tok=16. The winner is a truncation artifact. The best description
of this function (`"...truncating text to thirty thousand characters, and return the
embedding vector."`) appears at tok=32 but the cloud is too tight for convergence.

---

## Case 2 — `main()` with haiku (converged @ tok=16)

```python
def main():
    """..."""
    p = argparse.ArgumentParser(...)
    p.add_argument("text", ...)
    p.add_argument("--file", ...)
    p.add_argument("--dim", ...)
    p.add_argument("--model", ...)
    args = p.parse_args()
    text = open(args.file).read() if args.file else args.text
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or ...
    vector = embed(text, dim=args.dim, model=args.model)
    print(json.dumps(vector))
```

### Budget=8 — DEGENERATE — converged=False

avg cosine similarity: **1.0000**

```
[1] "Parse CLI arguments for text, file,"  ← centroid_nearest (all identical)
[2] "Parse CLI arguments for text, file,"
[3] "Parse CLI arguments for text, file,"
[4] "Parse CLI arguments for text, file,"
[5] "Parse CLI arguments for text, file,"
```

Same pattern as embed(). 8 tokens → repetition → degenerate cloud → `converged=False`.
Note the trailing comma: haiku is trying to list more arguments but runs out of budget.
The grammar filter accepts it.

### Budget=16 — ULTRA-TIGHT CLUSTER — converged=True ✓

avg cosine similarity: **0.9916** · min: **0.9860**

```
[1] "Parse CLI arguments for text, file, dimension, and model, resolve the input"
[2] "Parse CLI arguments for text, file, dimension, and model, resolve the input"
[3] "Parse CLI arguments for text, file, dimension, and model, resolve input from"  ← centroid_nearest
[4] "Parse CLI arguments for text, file, dimension, and model, resolve input from"  ← centroid_nearest
[5] "Parse CLI arguments for text, file, dimension, and model, resolve input from"  ← centroid_nearest
```

The five candidates differ by exactly two words: `"the input"` vs `"input from"`.
Average cosine similarity is **0.9916** — these are nearly the same sentence.
The cloud has barely any spread, but the antipode test still fires: the antipode
points away from `"input from"` (majority) toward `"the input"` (minority), and
their nearest neighbors differ → `converged=True`.

**Winner:** `"Parse CLI arguments for text, file, dimension, and model, resolve the input"`

The description ends mid-clause. The grammar filter passes it. In a Phase B run
where these five candidates happened to cluster even more tightly, the antipode
test would have returned `converged=False` — which is the stochastic failure mode
observed 8/9 times with haiku.

### Budget=24 — GENUINE SPREAD — converged=True

avg cosine similarity: **0.8928** · min: **0.8510**

```
[1] "...resolve the input source and API key, embed the text"         ← centroid_nearest
[2] "...resolve input from file or stdin, embed via OpenA"
[3] "Parse CLI arguments for text input source, API key, model, and dimension, resolve the input from file or stdin,"
[4] "...resolve input from file or stdin, embed via OpenA"
[5] "...resolve the input source and API key, embed the text"         ← centroid_nearest
```

Real variation now: some candidates name the API key resolution, some name the
stdin fallback, some hit both. `"embed via OpenA"` is another truncation artifact
(mid-word: "OpenAI"). Avg similarity drops to 0.89 — genuine semantic spread.

### Budget=32 — FULL DESCRIPTIONS — converged=True

avg cosine similarity: **0.8902** · min: **0.8147**

```
[1] "...resolve the input and API key, embed the text, and write the vector as JSON to stdout"
[2] "...resolve the input source and API key, embed the text, and write the vector as JSON to"  ← centroid_nearest
[3] "...resolve input and API key, embed the text, and write the vector as JSON to stdout."
[4] "...resolve the input source and API key, embed the text via OpenAI, and write the"
[5] "Parse CLI arguments for text input source, API key, model, and dimensions, resolve the input from file or stdin, embed via OpenAI, and write"
```

Candidate [2] ends mid-sentence ("as JSON to"). Candidate [4] is cut off ("and write").
Both pass the grammar filter. The best descriptions here ([1], [3]) are complete and
accurate. The pipeline picks tok=16 (minimum converged) so these never surface.

### Summary for Case 2

```
budget=8   avg_sim=1.0000  ░░░░░░░░░░  converged=False  (degenerate — all same)
budget=16  avg_sim=0.9916  ██████████  converged=True ✓ (near-identical, min selected)
budget=24  avg_sim=0.8928  █████████░  converged=True   (genuine spread)
budget=32  avg_sim=0.8902  █████████░  converged=True   (full but cuts off)
```

The minimum-converged budget of 16 picks an incomplete description. The full
description at 32 tokens is never selected. The stochastic instability at budget=16
(0.9916 avg similarity — nearly degenerate) explains why haiku converges here
in some runs and not others.

---

## Case 3 — `apply()` with gpt-4.1-nano (converged @ tok=8, quality concern)

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

This function has two behaviors: (1) merge delta into a state copy, (2) delete keys
where delta value is None, (3) optionally enforce strict key validation. A lossless
description needs to name at least behaviors 1 and 2. Budget=8 cannot fit both.

### Budget=8 — CONVERGED, BUT WRONG — converged=True ⚠

avg cosine similarity: **0.9104** · min: **0.8091**

```
[1]  "Merge delta into a copy of state,"  ← centroid_nearest
[2]  "Merge delta into a copy of state,"  ← centroid_nearest
[3]  "Merge delta into a copy of state,"  ← centroid_nearest
[4]  "Update a copy of state by merging delta"
[5]  "Merge delta into a copy of state,"  ← centroid_nearest
[6]  "Merge delta into a copy of state,"  ← centroid_nearest
[7]  "Merge delta into a copy of state,"  ← centroid_nearest
[8]  "Update a copy of state by merging delta"
[9]  "Merge delta into a copy of state,"  ← centroid_nearest
[10] "Update a copy of state with delta,"
```

7/10 candidates are `"Merge delta into a copy of state,"` (trailing comma).
The other 3 are near-synonyms. The cloud is tight (avg_sim=0.91) but not
degenerate (min_sim=0.81 — some spread between "Merge..." and "Update...").

The antipode points from the "Merge" centroid toward the "Update" outliers.
Their nearest neighbor is back in the "Merge" cluster → different → `converged=True`.

**Winner:** `"Merge delta into a copy of state,"` — a trailing-comma fragment.
The None-key deletion and strict-mode behaviors are completely absent.

### Budget=12 — BETTER, STILL CONVERGED

avg cosine similarity: **0.9010** · min: **0.7864**

```
[1]  "Merge delta into a copy of state, remove keys with None"    ← centroid_nearest
[2]  "Merge delta into a copy of state, removing keys with None"
[3]  "Merge delta into a copy of state, deleting None keys,"
[4]  "Merge delta into copy of state, update or remove keys,"
[5]  "Merge delta into a copy of state, removing keys with None"
[6]  "Merge delta into a copy of state, removing keys with None"
[7]  "Merge delta into a copy of state, remove keys with None"    ← centroid_nearest
[8]  "Merge delta into a copy of state, remove missing keys,"
[9]  "Merge delta into a copy of state, optionally validate keys,"
[10] "Merge delta into a copy of state, removing keys with None"
```

The None-deletion behavior appears in most candidates now. [4] is interesting:
`"update or remove keys"` — correctly captures the branching behavior. [9] mentions
`"optionally validate keys"` — describes the strict mode. No candidate names
both behaviors completely within 12 tokens.

### Budget=16 — APPROACHING COMPLETE — converged=True

avg cosine similarity: **0.9086** · min: **0.7574**

```
[1]  "Merge delta into a copy of state, update keys, delete None keys, raise"
[2]  "Update a copy of state with delta, removing keys with None values, raising on"
[3]  "Merge delta into a copy of state, removing keys with None values, optionally enforce"  ← centroid_nearest
[4]  "Merge delta into a copy of state, remove keys with None values, and enforce"
[5]  "Merge delta into a copy of state, removing keys with None values, and enforce"
[6]  "Merge delta into a copy of state, removing keys with None values, and optionally"
[7]  "Merge delta into a copy of state, removing keys with None values, optionally enforce"  ← centroid_nearest
[8]  "Merge delta into a copy of state, removing keys with None values, and optionally"
[9]  "Merge delta into a copy of state, removing None keys, with optional strict key"
[10] "Merge delta into a copy of state, removing keys with None values, optionally enforce"  ← centroid_nearest
```

Every candidate at budget=16 correctly names both the merge AND the None-deletion.
[1] even names the `raise`: `"delete None keys, raise"`. [3], [7], [10] (the
centroid cluster) say `"optionally enforce"` — correctly qualifying the strict mode.
All 10 are cut off mid-phrase.

### Budget=20 — MOST COMPLETE — converged=True

avg cosine similarity: **0.8692** · min: **0.7124**

```
[1]  "Merge delta into a copy of state, delete None keys, enforce strict keys if specified."
[2]  "Merge delta into a copy of state, remove keys with None values, enforce strict keys if specified."
[3]  "Merge delta into a copy of state, remove None keys, enforce strict keys if specified."
[4]  "Merge delta into a copy of state, removing or updating keys accordingly."       ← vague
[5]  "Merge delta into a copy of state, removing keys with None values, optionally enforcing strict key presence."
[6]  "Update a copy of state with delta, remove keys with None values, enforce strict keys if specified."
[7]  "Merge delta into a copy of state, updating or removing keys accordingly."       ← vague
[8]  "Merge delta into a copy of state, remove missing keys, and return the result."  ← wrong
[9]  "Merge delta into a copy of state, removing None keys and optionally enforcing strict keys."  ← centroid_nearest
[10] "Merge delta into a copy of state, removing keys with None values."              ← incomplete
```

Candidates [1], [2], [3], [5] are lossless descriptions of `apply()`. The
centroid_nearest is [9] which is also complete. [4] and [7] are too vague
("accordingly"). [8] is wrong ("remove missing keys" ≠ "remove keys where delta
value is None"). [10] drops strict mode.

The minimum converged budget is 8 — the pipeline never surfaces these 20-token
descriptions because it stopped at the first convergence.

### Summary for Case 3

```
budget=8   avg_sim=0.9104  █████████░  converged=True ⚠  WINNER (incomplete, trailing comma)
budget=12  avg_sim=0.9010  █████████░  converged=True    (None-deletion appears)
budget=16  avg_sim=0.9086  █████████░  converged=True    (both behaviors, cut-off)
budget=20  avg_sim=0.8692  ████████░░  converged=True    (complete descriptions exist)
budget=24  avg_sim=0.8934  █████████░  converged=True    (also complete)
```

The algorithm converges correctly at every budget. The quality failure is at the
grammar filter: `"Merge delta into a copy of state,"` passes because it starts
with an imperative verb, is 8 tokens, and has no hedging or filler. The trailing
comma is not caught.

---

## What the data reveals about the algorithm

### The degenerate cloud problem (haiku)

When haiku runs out of tokens, it repeats rather than varies. At budget=8, 5/5
candidates are identical. The embedding cloud is a single point:

```
cosine similarity matrix at budget=8 (haiku, embed):

         [1]   [2]   [3]   [4]   [5]
   [1]  1.000 1.000 1.000 1.000 1.000
   [2]  1.000 1.000 1.000 1.000 1.000
   [3]  1.000 1.000 1.000 1.000 1.000
   [4]  1.000 1.000 1.000 1.000 1.000
   [5]  1.000 1.000 1.000 1.000 1.000
```

antipode = 2*centroid - nearest = 2*P - P = P — the antipode IS the point.
Every candidate is "nearest" to the antipode. `argmin` returns index 0 by
convention = same as nearest → `converged=False`. Correct.

The same problem emerges at budget=32 when haiku produces 4/5 identical outputs
(near-degenerate). The algorithm correctly refuses to converge on a near-point cloud.

### Why gpt-4.1-nano never triggers this

```
budget=8 (nano, apply):

avg_cosine_sim=0.9104  min_cosine_sim=0.8091

         [1]     [4]     [10]
   [1]  1.000   0.83    0.87    "Merge delta into a copy of state,"
   [4]  0.830   1.000   0.91    "Update a copy of state by merging delta"
  [10]  0.870   0.910   1.000   "Update a copy of state with delta,"
```

Even at 8 tokens, nano produces three distinct phrasings. The minimum similarity
(0.81) gives the antipode test geometric room to work. The algorithm converges
at every budget tested.

### The quality gap: tight ≠ lossless

The algorithm correctly identifies the minimum budget where candidate descriptions
stabilize. But stable does not mean complete. At budget=8, `apply()` generates
stable descriptions of the merge behavior only. The None-key deletion — equally
important — appears only at budget=12 and above.

The grammar filter is the intended catch for this, but it operates on syntax only:
- Does the description start with an imperative verb? ✓ ("Merge", "Update")
- Is it within the token budget? ✓
- Does it contain hedge words? ✗

It has no semantic completeness check. It cannot know that `"Merge delta into a
copy of state,"` omits a critical behavior.

---

## Grammar filter failures — live catches

Every one of these passed the grammar filter in this experiment:

```
"Call the OpenAI embeddings API with the given model and dimensions, trunc"
 └─ mid-word truncation ("trunc" = truncating)

"Parse CLI arguments for text, file,"
 └─ trailing comma — continues a list

"Parse CLI arguments for text, file, dimension, and model, resolve the input"
 └─ ends mid-clause ("resolve the input [from...]")

"...truncating text to thirty thousand characters, and"
 └─ trailing conjunction

"Merge delta into a copy of state,"
 └─ trailing comma — sentence fragment

"Merge delta into a copy of state, remove missing keys, and return the result."
 └─ semantically wrong ("missing keys" ≠ "None-valued keys") — syntactically fine
```

Three rules needed for Mission 9:

```python
TRAILING_BAD = {',', ';', ':'}
TRAILING_CONJUNCTIONS = {'and', 'or', 'but', 'with', 'for', 'to', 'from', 'the'}

def grammar_filter_additions(text: str, budget: int) -> bool:
    words = text.rstrip().split()
    if not words:
        return False  # reject empty
    last = words[-1].rstrip('.,;:')
    # trailing comma/semicolon/colon on the sentence
    if text.rstrip()[-1] in TRAILING_BAD:
        return False
    # trailing conjunction or preposition
    if last.lower() in TRAILING_CONJUNCTIONS:
        return False
    # mid-word truncation: last word is alpha-only, short, no space after
    # and doesn't look like a complete word (heuristic: length < 5)
    if last.isalpha() and len(last) < 5 and last.lower() not in {'call', 'read', 'get', 'set', 'run', 'use', 'add'}:
        return False
    return True
```

---

## Recommendation table

| Parameter | Before | After | Why |
|-----------|--------|-------|-----|
| `generation_model` | `"gpt-5-nano"` | **`"gpt-4.1-nano"`** | gpt-5-nano emits empty strings at low budgets (reasoning model). nano: 18/18 convergences, cheapest. |
| `embed_dim` | `128` | **`256`** | 128 showed false-positive convergence via haiku truncation artifact in M7. No quality delta between 256/512/768. |
| `n` | `10` | **`5`** | Zero reject rate and identical convergence at n=10,15. n=5 is sufficient. |
| `budget_step` | `8` | **`8`** | Unchanged. |
| `budget_range` | `(8, 32)` | **`(8, 32)`** | Unchanged. Covers full observed range. |

**mld.py lines that change in Mission 9:**
```python
# line 365 (before)
generation_model: str = "gpt-5-nano",
# line 365 (after)
generation_model: str = "gpt-4.1-nano",

# line 367 (before)
embed_dim: int = 128,
# line 367 (after)
embed_dim: int = 256,

# line 363 (before)
n: int = 10,
# line 363 (after)
n: int = 5,
```

**api.py — add to RATES table:**
```python
"gpt-4.1-nano": {
    "input": 0.10,
    "output": 0.40,
    "cache_read": 0.025,
    "cache_write": 0.0,
},
```

---

## Cost and cache summary

```
Total spend:    $0.49 across 54 runs
Ceiling:        $10.00  (headroom: $9.51)

Per model:
  claude-haiku-4-5   13 runs  $0.156  $0.012/run  cache=95.2%  wall=10.3s avg
  gpt-4.1-nano       18 runs  $0.084  $0.005/run  cache=49.6%  wall= 5.1s avg
  gpt-4o-mini        16 runs  $0.094  $0.006/run  cache=44.3%  wall= 4.2s avg

M7 cache hit rate was 0% — prompt was 2,066 tokens, below Haiku's 4,096-token
cache floor. The 7-E prompt at 4,549 tokens caches at 95.2%. DP-4 validated.
```

---

## Open questions for Mission 9

1. **Grammar filter** — add trailing-comma/conjunction/truncation checks before shipping.
2. **Degenerate cloud handling** — consider adding a pre-check: if `avg_cosine_sim > 0.999`, skip the antipode test and return `converged=False` directly. Avoids floating-point edge cases.
3. **Minimum candidate diversity** — if 4/5 candidates are identical, the n=5 sample is effectively n=2. Consider a dedup step before embedding: if >50% of candidates are identical, rerun the generation tier once. This would help haiku without changing the algorithm.
4. **Quality vs. losslessness** — the algorithm finds the minimum *stable* budget, not the minimum *complete* budget. Consider a post-convergence completeness check: embed the input function body and the winning description, compute cosine similarity, flag if below a threshold.
5. **converged=False path** — was not empirically exercised. To trigger it: use a function with genuinely equivocal semantics AND n≥10 with a model that produces varied phrasings at every budget tier. Suggested: `def merge(a, b, prefer_b=True): return {**a, **b} if prefer_b else {**b, **a}` at budget_range=(8,12).
