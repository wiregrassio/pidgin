# Minimum Lossless Descriptions (MLD)

A consensus-driven compression pipeline for LLM-optimized
documentation.

---

## The Problem

Documentation is written for humans. LLMs consume it at inference
time as raw token cost — every word of prose padding, every hedged
clause, every interpretive flourish is a tax paid on every future
call that ingests it. At scale across a codebase or knowledge corpus,
that tax is real money and real context pressure. More critically,
natural language ambiguity that a human reader resolves charitably
is ambiguity an LLM may resolve differently on every call.

The goal is not shorter documentation. The goal is documentation
compressed to its information-theoretic floor — the point below
which meaning is lost and above which tokens are wasted.

---

## The Core Idea

Given an input — a function, a prose passage, a legal clause, an
image — find the minimum token budget at which an LLM reaches stable
semantic consensus about its content. That budget is the MLD token
count. The output at that budget is the MLD itself.

The pythonic analogy holds: there are many ways to describe a thing,
but there should be one obvious, unambiguous way. MLD finds it
empirically.

---

## The Pipeline

1. **Generate.** Using a high-temperature, low-cost model, produce N
   candidate descriptions at a fixed token budget. Temperature creates
   variance; variance is raw material.

2. **Filter.** Before embedding, apply a mechanical grammar filter.
   Candidates must conform to a domain-specific controlled vocabulary
   and structural rules. Vocabulary violations and structural failures
   are rejected and rerun. Reject rate is a calibration signal — high
   rates indicate grammar too tight or corpus too broad.

3. **Embed.** Compute vector embeddings for all passing candidates.
   Embedding dimension is tuned for discrimination between short
   texts, not for corpus-scale RAG — 64-128 dimensions may suffice.
   Same model as RAG embeddings, different `--dim` value.

4. **Test convergence.** Compute the centroid of the candidate cloud.
   Find the candidate nearest the centroid. Compute its antipode about
   the centroid (2C - P). Find the antipode's nearest neighbor among
   existing candidates. If the nearest neighbor is the centroid, the
   candidate cloud is sparse or directionally imbalanced — coverage
   is insufficient. Expand by 50% and repeat. When the antipode's
   nearest neighbor is a real candidate, the centroid is well-interior
   to the convex hull of the distribution. Consensus is achieved.

5. **Adjust budget.** If convergence is fast, halve the budget and
   rerun. If convergence fails, increase it. Binary search or
   20-questions bisection toward the minimum convergent budget. Set a
   max limit. Run all budget tiers in parallel from the start —
   sequential search is a false economy when generation costs
   fractions of a cent.

6. **Validate.** Pass the centroid-nearest candidate plus 3-4
   filtered alternatives — selected by different axes (median length,
   shortest above threshold, highest internal consistency) — to a
   reasoning model. It validates each in turn and selects the best,
   producing an explanation that becomes part of the artifact. The
   reasoning model judges; it does not create.

---

## Why the Geometry Works

The theoretical concern with centroid-based methods in
high-dimensional embedding space is that distances compress and the
geometry loses meaning. In practice this concern is largely resolved
by two factors.

First, the token budget constraint itself. A 16-token description of
a 15-line function cannot express many fundamentally distinct semantic
propositions. The constraint collapses the effective intrinsic
dimensionality of the candidate cloud before any geometry is computed.
The candidates occupy a low-dimensional manifold — the antipode
construction stays within that manifold, operating only on real
points, never navigating the empty regions of the ambient space.

Second, embedding dimension tuning. MLD convergence checking does not
require 1536 dimensions to discriminate between 16-token descriptions
of the same function. Operating at 64-128 dimensions keeps the
geometry genuinely informative. The right dimension is an empirical
finding — validate during initial deployment by testing against
known-simple and known-complex functions.

The antipode check captures something standard deviation cannot:
directionality. A tight cluster varying along many semantic axes looks
identical in spread to a flat one varying along two, but their
antipode behavior is completely different. The check is implicitly
sensitive to the shape of the distribution, not just its magnitude.

---

## The Economics

At sub-cent per million tokens for generation and low single cents for
embedding, the entire pipeline for a single function costs fractions
of a cent. Sequential budget search is a false economy — the dominant
cost is engineer wall time. Run all budget tiers in parallel from the
start. Generation and embedding are both parallelizable; total wall
time is approximately the latency of a single API call regardless of
candidate count. The reasoning model runs once per function. Expensive
judgment is applied exactly once, to the best filtered candidates,
where it adds value.

---

## What You Get

**The MLD itself.** The centroid-nearest candidate at the minimum
convergent budget. Concrete nouns, direct verbs, explicit object
relationships. No grammatical slack. No room for conjugation or
interpretive latitude. Two valid descriptions of the same thing,
generated independently, embed nearly identically.

**A compression complexity score.** The minimum convergent token
budget is a free per-function complexity metric. A function converging
at 8 tokens is semantically simple and compositionally isolated. One
requiring 48 is behaviorally complex or implicitly coupled. This
surfaces what static analysis cannot.

**A convergence confidence score.** How many candidates were needed.
Fast convergence at a low budget means the function is unambiguous and
well-bounded. Slow convergence flags something worth examining.

**Non-convergence as a signal.** A function that cannot converge at
any budget is a structural liability. A legal clause that cannot
converge was deliberately written to be ambiguous. A policy document
that cannot converge should not be acted on by an agent. The pipeline
does not fail on non-convergence — it issues a receipt.

---

## Beyond Code

The input is arbitrary. The method applies wherever there is
compressible meaning and a cost to ambiguity — the pipeline is
domain-agnostic by construction.

---

## The Deliverable

A codebase processed through MLD does not have documentation. It has
a precision-compressed semantic index, empirically validated by
consensus, optimized for LLM consumption, and compressed to the
minimum lossless description of every component. Every token above
that minimum was waste. Every token below it was loss. MLD finds the
line.
