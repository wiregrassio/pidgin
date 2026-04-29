# Bidirectional MLD

The MLD convergence geometry doesn't know what it's converging on. It measures whether N candidates have reached semantic consensus at a given complexity level. V1 and V2 use it in one direction: code→description. The algorithm works identically in the other direction: description→code.

## Code → Description (validated)

Give the model a function body. Generate N candidate descriptions. Embed them. Run the antipode test. The minimum budget at which candidates converge is the information-theoretic floor for describing that function. Tokens above the floor are waste. Tokens below are loss.

This is the V1/V2 use case. 54 + 4 empirical runs. Validated.

## Description → Code (proposed)

Give the model an MLD description. Generate N candidate implementations. Embed them. Run the antipode test. The candidates that converge are the implementations the model is most confident about.

**Non-convergence is a specification signal.** If 10 candidate implementations don't converge, the description permits multiple valid interpretations. The spec is ambiguous. This is a signal back to the sprint planner: refine the description before writing code.

**Convergence is a correctness signal.** If candidates converge, the model has a stable interpretation of the spec. The converged implementation is the one the model would produce regardless of sampling variation. This isn't proof of correctness — the model could be confidently wrong — but it eliminates the class of errors where the model produces different code on different runs because the prompt was ambiguous.

## The Unified Verb

The Pidgin verb isn't `describe` or `implement`. It's `converge`. The caller specifies:
- **Input:** code (for code→description) or description (for description→code)
- **Direction:** compress (code→description) or expand (description→code)
- **Target complexity:** the conciseness budget for the output

The pipeline is identical in both directions. Three-draft generation, embedding, antipode test, gate, selection. The only thing that changes is the prompt template — one for compression, one for expansion.

## Sprint Plan Application

A sprint mission description is an MLD-compressed specification. When Pidgin processes a sprint plan:

1. **Pass 1 (human):** Sprint writer produces natural language mission descriptions.
2. **Pass 2 (compress):** Pidgin MLD-compresses each description. The compressed version is the specification.
3. **Pass 3 (expand):** Pidgin takes each compressed description and runs description→code convergence. The converged implementation is the proposed code.
4. **Pass 4 (validate):** Sprint writer reviews the generated code against the compressed spec. Non-convergent sections are flagged for human refinement.

Each pass reads and writes specific XML-tagged regions of the sprint document. The document accumulates state across passes.

## Empirical Gap

Description→code convergence has not been empirically validated. The geometry should work — cosine similarity on code embeddings, antipode test on implementation candidates — but the embedding space for code may behave differently than for natural language descriptions. Code has syntactic structure that descriptions don't. Two implementations that do the same thing might embed differently because of variable names, control flow patterns, or formatting.

The validation plan: take 5 MLD descriptions from V2 (embed, main, apply, merge, plus one complex function), run description→code convergence at N=10 with budget_range=(50, 200), and check whether the converged implementations are (a) syntactically valid, (b) semantically correct against the original function, and (c) stable across runs. If convergence is unreliable in the code embedding space, the direction may need a different embedding model or a different similarity metric.

## Implications

If bidirectional MLD works, Pidgin is not just a documentation tool. It's a specification-driven code generation system where the specification is a minimum lossless description and the generation is a convergent implementation. The sprint runner doesn't write code — it writes specs and validates convergent implementations. The quality guarantee shifts from "the model wrote good code" to "the model wrote code that it agrees with itself about, given this spec."
