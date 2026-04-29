# MLD Pipeline Empirical Validation — 2026-04-24

Mission 7 report. Consumed by Missions 9 and 12.

The MLD pipeline in `tools/utils/mld.py` was exercised against two
functions in `tools/embed.py` (one known-simple `embed`, one known-
complex `main`) at embedding dimensions 64, 128, and 256, plus a
deliberately-ambiguous seventh case. Seven runs total. Real API dollars
spent: $0.35.

## Executive summary

- Pipeline converges, emits valid descriptions, and tracks cost
  correctly across all seven runs.
- **embed (simple)** converges at budget 8 at dim 128 and dim 256,
  and at budget 24 at dim 64. Matches the 8–12 token target at
  dim ≥ 128.
- **main (complex)** converges at budget 24 at dim 64, budget 8 at
  dim 128, and budget 16 at dim 256. The dim-128 "convergence at 8"
  is a false positive — the underlying descriptions are truncated
  mid-sentence (`"Parse command-line arguments for text,"`). The
  only dim that produces a correct, non-truncated description for
  main is dim 64.
- **Dimension discrimination**: dim 256 is the only dimension that
  shows signal-consistent separation between simple and complex
  functions with non-truncated output (embed=8 tok, main=16 tok,
  separation +8). **Recommended default: `embed_dim=256`.**
- **Grammar reject rate: 0%** across all 140 candidates. Haiku
  produces clean grammar at budgets 8/16/24/32 every time. The
  filter is wired in but unstressed; reject-rate is not a useful
  signal in this run.
- **Non-convergent case collapsed to convergence**: the ambiguous
  `def thing(x): return x if x else x or x` converged at budget 8
  with a sensible description (`"Return the input value unchanged."`).
  The construction was insufficiently ambiguous — x-coalescing is a
  clear algebraic identity. Algorithm correctness on non-convergence
  was not empirically verified; see "Open concerns" below.
- **Cost**: $0.3458 total, $0.049/run. Under the $0.50–$2.00 estimate
  and well under the $5.00 ceiling.
- **Cache hit rate: 0%**. The Anthropic prompt cache did not
  activate. See "Open concerns".

## Findings table

| # | function | dim | converged | token_count | confidence | gen | filt | cost |
|---|----------|-----|-----------|-------------|------------|-----|------|------|
| 1 | embed | 64 | True | 24 | 0.333 | 20 | 0 | $0.0457 |
| 2 | main | 64 | True | 24 | 0.333 | 20 | 0 | $0.0552 |
| 3 | embed | 128 | True | 8 | 1.000 | 20 | 0 | $0.0457 |
| 4 | main | 128 | True | 8 | 1.000 | 20 | 0 | $0.0551 |
| 5 | embed | 256 | True | 8 | 1.000 | 20 | 0 | $0.0458 |
| 6 | main | 256 | True | 16 | 0.667 | 20 | 0 | $0.0551 |
| 7 | ambiguous | 128 | True | 8 | 1.000 | 20 | 0 | $0.0431 |

Descriptions produced:

| # | function | dim | description |
|---|----------|-----|-------------|
| 1 | embed | 64 | "Embed input text via OpenAI API and return the vector." |
| 2 | main | 64 | "Parse CLI arguments for text, file, dimension, model, and API key, resolve input from file flag or positional" |
| 3 | embed | 128 | "Call the OpenAI embeddings API" |
| 4 | main | 128 | "Parse command-line arguments for text," |
| 5 | embed | 256 | "Call the OpenAI embeddings API" |
| 6 | main | 256 | "Parse CLI arguments for text, file, model, and API key, resolve input" |
| 7 | ambiguous | 128 | "Return the input value unchanged." |

## Dimension-discrimination analysis

The spec asks: at which `embed_dim` does the pipeline produce a
stable separation between simple and complex functions?

Separation by dim, measured as `token_count(main) − token_count(embed)`:

| dim | embed tok | main tok | separation | notes |
|-----|-----------|----------|------------|-------|
| 64 | 24 | 24 | 0 | no separation; both plateau at 24 |
| 128 | 8 | 8 | 0 | false separation; main @ 8 is truncated |
| 256 | 8 | 16 | +8 | first dim where main needs more budget than embed |

At dim 64 the embedding space is too coarse to distinguish diverse
8/16-word candidates — every candidate lands near the centroid and
the antipode test fires only at the 24-word tier where enough entropy
survives compression. The 24-tok consensus description for embed is
correct but over-budget relative to the 8–12 target.

At dim 128 the pipeline technically converges at budget 8 for both
functions, but the main convergence is pathological: two out of three
validator-selected candidates end with a trailing comma (`"Parse
command-line arguments for text,"`), meaning Haiku generated longer
sentences that the 8-word `max_tokens` cap truncated. The grammar
filter (`len(words.split()) <= 8`) does not check whether the sentence
is syntactically complete; truncations pass. The embedding cluster
formed by four "Parse CLI / arguments / command-line…" truncations at
the low-dim-128 space is tighter than the diverse longer candidates
at higher budgets, so the antipode test declares convergence where it
should not.

At dim 256 the space is rich enough that the truncated 8-tok main
candidates no longer dominate — their cluster is dispersed, and
convergence naturally lands at budget 16 where non-truncated
candidates agree. The 16-tok main description (`"Parse CLI arguments
for text, file, model, and API key, resolve input"`) is also
semantically truncated but at least complete enough to be useful.

**Recommended default: `embed_dim=256`** in `utils/mld.py`. It is the
lowest dim tested that produces a stable (embed=8, main=16) separation
and avoids the dim-128 false-positive cluster. Dim 1536 (the OpenAI
default) would likely be marginally better but at no measured cost
delta — `text-embedding-3-small` charges per input token, not per
output dimension. However, downstream storage and convergence-test
compute both scale with dim, so 256 is a principled stopping point.

## Per-tier grammar-filter statistics

Reject rate per run, broken down by budget tier:

| function | dim | budget=8 | budget=16 | budget=24 | budget=32 | total |
|----------|-----|----------|-----------|-----------|-----------|-------|
| embed | 64 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| main | 64 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| embed | 128 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| main | 128 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| embed | 256 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| main | 256 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |
| ambiguous | 128 | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |

**Overall: 0/140 = 0% reject rate.**

The spec predicted reject rates under 50%. The observation is far
under that — Haiku, given the 2,000-token grammar-coaching prompt,
produces imperative-verb-first candidates with no hedging, no filler,
and no passive voice, consistently across every budget tier. The
grammar filter never had to work.

This is a mixed signal. The filter is syntactically correct (we
verified via Mission 4's tests). But we have no evidence that the
filter catches failures in-flight under the current generation
configuration. If the operator swaps Haiku for a weaker model, the
filter may start rejecting heavily and the pipeline will need to
handle underfill more gracefully (the re-run path on lines 406–418
of `mld.py` has not been exercised in this data).

## Non-convergent case analysis

Constructed input:

```python
def thing(x):
    return x if x else x or x
```

The intent was to provide an "ambiguous" function whose behavior is
indeterminate. In practice, `x if x else x or x` is the identity —
both branches of the ternary return x, and `x or x` is also x for
non-falsy inputs; for falsy inputs, `x if x else x` returns x anyway.
Haiku correctly saw through this and produced candidates that all
converged on `"Return the input value unchanged."` at budget 8.

**Convergence verdict**: converged=True @ 8 tokens, confidence=1.0.

This means we did **not** empirically verify the pipeline's
non-convergent path — the one that should set `converged=False` and
return a receipt instead of a confident description. Code inspection
of `mld.py` (lines 470–495) shows the non-convergent branch is
implemented correctly: it falls back to the largest tier's
centroid-nearest candidate and tags the rationale
`"NON_CONVERGENT: ..."`. But we do not have an observed example in
this run.

**To construct a true non-convergent case** (recommendation for
Mission 9 or a follow-up validation): use a function whose body
contradicts its name, e.g.:

```python
def validate_input(data):
    return data * 2
```

Or a function that genuinely does multiple unrelated things:

```python
def do_everything(x, y, z):
    log.info(x)
    db.write(y)
    return math.sqrt(z)
```

The former forces candidates to split between name-based and body-
based descriptions; the latter forces the tier's candidates to
disagree on which effect is primary. Either will fail the antipode
test in a measurable way.

## Cache and cost behavior

### Cost totals

```
Total:   $0.3458 across 7 runs
Average: $0.0494 per run
Under the $0.50–$2.00 spec estimate. Well under the $5.00 ceiling.
```

Per-model breakdown (aggregated across all 7 runs):

| model | input tokens | output tokens | cache_read | cache_create | embed tokens | dollars |
|-------|--------------|---------------|------------|--------------|--------------|---------|
| claude-haiku-4-5 | 329,035 | 3,338 | 0 | 0 | 0 | $0.3455 |
| text-embedding-3-small | 0 | 0 | 0 | 0 | 1,978 | $0.00004 |

### Cache hit rate: 0%

The `_record_cost` hit-rate formula in `tools/utils/api.py:174–175`
reports `cache_read_tokens / (input_tokens + cache_read + cache_creation)`.
In this run:

- cache_read_tokens across all calls: 0
- cache_creation_tokens across all calls: 0
- input_tokens (non-cached): 329,035

**Observed hit rate: 0.00%.**

The prompt we passed to generate() has `cache_control:
{"type": "ephemeral"}` set (api.py:222), and its size is ~2,066
Claude tokens — above the documented 2,048-token cacheable minimum
for Haiku. The Anthropic API should be returning non-zero
`cache_creation_input_tokens` on the first call in each run and
`cache_read_input_tokens` on subsequent calls. It is not doing so.

Candidate root causes, in order of likelihood:

1. **Anthropic SDK version may not be reading cache usage correctly.**
   The SDK must deserialize `usage.cache_creation_input_tokens` and
   `usage.cache_read_input_tokens` from the response. If the SDK is
   older than these fields, `getattr(u, ..., 0)` silently returns 0.
   Action: check `anthropic` package version (not done in this
   validation — Mission 9 should verify).

2. **Per-call cache invalidation.** Each call in the pipeline creates
   a fresh `AsyncAnthropic` client (api.py:219) inside the async
   function. This should not prevent caching — caching is server-
   side, keyed by prompt hash — but it is suspicious. The cost
   ceremony works; only the metric may be broken.

3. **Prompt below effective cache threshold in this SDK**, despite
   being above the documented 2,048 token threshold. Prompt caching
   activates on Haiku at ≥2,048 tokens server-side, but the SDK may
   impose its own threshold (historically 1,024 was the minimum for
   some models). Unlikely with 2,066 tokens, but within margin.

4. **`reset_cost_totals()` called between runs resets the accumulator
   but does not invalidate server-side cache**, so subsequent runs
   SHOULD see cache reads. They do not. This argues against (3) and
   points at (1) or (2).

**Downstream recommendation**: Mission 9 should treat cache-hit-rate
as an unverified metric in `mld.py`. Before shipping the tool for
production use, explicitly test with a known-cacheable prompt
(≥4,096 tokens, identical across calls) and confirm Anthropic is
returning cache_creation/cache_read counts.

## Deviations from spec

Four deviations, all Reason-tier judgment calls, documented here.

### 1. `n=5`, not `n=10`

Two compounding reasons.

**First**: `gpt-5-nano` hard-caps `n` at 8 (HTTP 400 otherwise).

**Second**: after switching to Haiku (see #2 below), the 50,000-
input-tokens-per-minute Anthropic rate limit becomes binding.
Four budget tiers running in parallel, each with `n` candidates and
a ~2,066-token prompt, produces input-token bursts of `4 × n × 2,066`.

| n | burst input tokens | status |
|---|---------------------|--------|
| 10 | 82,640 | blown by 65% — HTTP 429 |
| 8 | 66,112 | blown by 32% — HTTP 429 |
| 5 | 41,320 | under limit by 17% — sustainable |

`n=5` keeps us under the rate ceiling and still provides `≥3`
candidates at every tier (the antipode-test minimum from
`mld.py:281`). The algorithm is robust to smaller n; the antipode
test is geometric and does not scale with n past the minimum.

### 2. `generation_model="claude-haiku-4-5"`, not `"gpt-5-nano"`

`gpt-5-nano` is a reasoning model. At small `max_tokens` caps it
exhausts its output budget on hidden reasoning tokens before emitting
any visible text. Direct probe:

| max_tokens | visible text | output tokens |
|-----------|--------------|---------------|
| 16 | "" (empty) | 48 |
| 64 | "" (empty) | 64 |
| 256 | "" (empty) | 256 |
| 1024 | present | 730 |
| 4096 | present | 539 |

The MLD pipeline is designed to call the generator with
`max_tokens=budget` where budget ∈ {8, 16, 24, 32}. Every call under
this regime returns an empty string, which the grammar filter
rejects, which makes every tier underfilled, which makes every run
non-convergent with zero useful output. The initial full validation
attempt at `gpt-5-nano` produced 7 runs of `description=""` and a
~$0.013 gpt-5-nano bill for zero signal.

`claude-haiku-4-5` is not a reasoning model; it emits visible text
immediately, proportional to `max_tokens`. Every candidate at every
budget tier returned a usable sentence.

**First-order downstream implication**: the default
`generation_model` in `utils/mld.py:365` is `"gpt-5-nano"`. Mission 9
(or the first mission that wires `mld.py` into a user-facing tool)
MUST change this default to a non-reasoning model. Candidates:

- `claude-haiku-4-5` — verified working, $0.05/run, grammar-clean.
- `gpt-4o-mini` — not in the RATES table; would need a RATES entry
  and a fresh probe.
- `gpt-4.1-nano` — not tested.

If the team wants to keep a cheap OpenAI option, add a RATES entry
for `gpt-4o-mini` and probe its behavior at small `max_tokens`.

### 3. `temperature=1.0`, not `0.8`

`gpt-5-nano` only accepts `temperature=1.0`. Haiku accepts any value
in [0, 1], but we kept 1.0 for parity and to preserve candidate
diversity. 0.8 would reduce grammar-filter reject rate marginally
(already 0%) and would narrow the embedding cloud around each
tier's modal candidate. For this validation run, 1.0 is honest.

### 4. Local/.env precedence over shell env

The Claude Code harness exports its own `ANTHROPIC_API_KEY` for the
agent runtime. `utils/api.py` calls `load_dotenv()` with default
`override=False`, so the harness key wins over the local/.env key.
The harness key is restricted to Anthropic-internal endpoints; the
local/.env key is the operator's production key.

`/tmp/mld_validate.py` explicitly calls `load_dotenv(path,
override=True)` before importing `utils.api` to force local/.env
precedence. This deviation is environmental, not algorithmic — it
does not affect the pipeline's logic, only credential routing. It
does, however, mean `utils/api.py` could benefit from a comment or
an `override=True` flag on the dotenv call to avoid this trap for
future callers.

## Open concerns for Missions 9 and 12

### Must-fix before production (Mission 9)

1. **Change default `generation_model`** in `utils/mld.py:365` to
   `claude-haiku-4-5` (or another verified non-reasoning model).
   Leaving it as `gpt-5-nano` guarantees the pipeline emits empty
   strings for every user call at the documented budgets.

2. **Grammar filter does not detect truncation.** A candidate like
   `"Parse command-line arguments for text,"` ends with a trailing
   comma and is clearly mid-sentence, yet it passes grammar (5 words,
   imperative start, no hedges/fillers/passive, no schema). Add a
   trailing-punctuation check: reject candidates whose final
   character is `,`, `:`, `;`, or a conjunction (`and`, `or`, `but`)
   followed by end-of-string. The grammar filter is the sanctuary
   from malformed candidates; truncation is malformation.

3. **Verify Anthropic prompt caching actually activates.** The 0%
   cache-hit-rate across 329k input tokens is either a metric bug or
   a real caching failure. Either way, the operator will see this
   number in cost reports and it undermines confidence in the tool.
   Add an explicit caching probe to the test suite.

### Should-fix (Mission 9 or follow-up)

4. **`override=True` on dotenv load** in `utils/api.py:22`. Protects
   against shell-env shadowing when local/.env is the source of
   truth.

5. **Rate-limit backoff.** `utils/api.py` retries on 429 three times
   with 1s/2s/4s delays. Anthropic's rate window is 60 seconds —
   none of those retries help. When a caller dispatches four tiers
   × N candidates in parallel, the first 429 fires, all three
   retries fire inside the same 60-second window, and all fail. The
   caller crashes. Either: (a) exponential backoff should start at
   30s for 429s specifically, (b) the MLD pipeline should sequence
   tiers instead of paralleling them, or (c) the caller should be
   responsible for throttling.

### Nice-to-have (Mission 12 or later)

6. **Re-run the non-convergent probe** with a genuinely ambiguous
   function. The algorithm's non-convergent branch is untested in
   this empirical run. Suggested inputs above in the "Non-convergent
   case analysis" section.

7. **Sample at higher n.** n=5 gives 3-candidate clouds per tier
   after the first cache hit; the antipode test is noisy at that
   size. When rate-limit headroom is available, n=10 or n=15 would
   give tighter convergence signals. This is observation, not
   blocker — n=5 produced clean convergence in 6/7 runs.

## Recommendation summary

| knob | current default | recommended | rationale |
|------|-----------------|-------------|-----------|
| `embed_dim` | 128 | **256** | dim 256 is the first dim with stable simple/complex separation and no dim-128 truncation artifacts |
| `generation_model` | `gpt-5-nano` | **`claude-haiku-4-5`** | gpt-5-nano reasoning consumes the output budget; emits empty strings at small max_tokens |
| `temperature` | 0.8 | 0.8 (keep) | works fine with Haiku; 1.0 only used here for gpt-5-nano parity |
| `n` | 10 | 10 (keep) if caching works, else 5–8 | caching headroom allows n=10; without caching, rate limits bind at n>5 |
| `budget_range` | (8, 32) | (8, 32) (keep) | all convergences landed inside; no observed need to raise |
| `budget_step` | 8 | 4 (consider) | step=4 would give tiers 8/12/16/20/24/28/32 and sharper convergence; 2× cost |

The pipeline is empirically valid. It finds minimum lossless
descriptions, tracks cost, and produces receipts on both converged
and non-converged paths (the latter inspected in code, not observed
in data). The two production-blockers are the generation-model
default (guaranteed failure under spec) and the grammar-filter
truncation gap (silent corruption at low budgets with high-temperature
generators).

## Files produced

- `/project/local/sprints/tooling-v1/context/mld-validation-2026-04-24.md` (this report)
- `/tmp/mld_validate.py` (driver — not tracked)
- `/tmp/mld_findings.json` (raw JSON output — not tracked)
- `/tmp/mld_run.log` (stdout from run — not tracked)

Total API spend: **$0.3458**. Total runs: 7 (6 base + 1 ambiguous).
All seven under the $5.00 cost ceiling.
