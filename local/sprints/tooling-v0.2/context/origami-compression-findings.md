# Origami Compression Findings

M14 ran the 19 Origami manifesto principles through the MLD pipeline. All 19 converged. The results are in ORIGAMI.md at the repo root. This document captures what the compression revealed about MLD quality, the boundary between principle and practice, and how LLMs process constraints differently than humans.

## Results Summary

- 19/19 converged
- 16 at confidence 1.00 (5/5 candidates agreed)
- 3 at confidence 0.80 (4/5 candidates agreed)
- Total cost: $0.0004
- No non-convergent principles

## The 0.80 Confidence Principles

Three principles converged at 0.80 instead of 1.00. In each case, 4 of 5 candidates agreed on the core claim and one candidate retained an implementation sub-rule.

**Principle 2 — The Daft Punk Principle (0.80).** The compressed version: "Ensure every tool or service is describable with a small set of imperative verbs understood within two seconds." The fifth candidate also included the 8-32 token range constraint. The algorithm couldn't determine whether the token range was part of the principle or an implementation detail.

**Principle 3 — The Pit of Success (0.80).** The compressed version: "Design systems so the correct and easy path is the default, requiring no discipline to follow." The fifth candidate retained the golden repo reference. Same pattern — the algorithm correctly identified doubt about whether the example was part of the principle.

**Principle 13 — Documentation Is the API (0.80).** The compressed version: "Design all interfaces and artifacts to be self-explanatory and self-documenting." The most aggressive compression — 80 words with four sub-rules (100-line rule, INDEX files, token-efficient formatting, self-documenting artifacts) compressed to 10 tokens. One candidate kept the 100-line rule.

## Operator Assessment

The operator reviewed all three 0.80 compressions and validated them. Key observations:

- The 100-line rule in Principle 13 was invented by the operator and is no longer enforced. INDEX files are no longer used. Token-efficient formatting is now handled by Pidgin, not by the document author. Three of four sub-rules are obsolete practice, not principle.
- The golden repo in Principle 3 is a specific implementation of the pit-of-success concept. The principle is the concept, not the repo.
- The 8-32 token range in Principle 2 is a calibration detail, not the principle. The principle is the constraint (small set, understood quickly). The range is how you measure it.

In all three cases, the algorithm correctly compressed and correctly flagged its uncertainty. The operator resolved the uncertainty in favor of the compression.

## The Insight: Pedagogy vs. Specification

The operator's observation: "Supporting detail in principle bodies is pedagogy, not specification. Those who think and those who do need different instructions."

Full principle bodies contain:
- The constraint (what to do)
- Motivation (why it matters)
- Metaphors (how to think about it)
- Examples (how it looks in practice)
- Implementation details (how to execute it)

MLD strips everything except the constraint. This is not information loss — it is audience adaptation.

An LLM processing a principle doesn't need motivation (it doesn't have internal motivation to align). It doesn't need metaphors (it processes strings, not mental images; metaphors can compete for attention weight in crowded context windows). It doesn't need examples (examples narrow the principle to specific implementations when the LLM should generalize). It needs the constraint stated directly so it can apply it to novel situations.

The operator's framing: "Origami makes things self-explanatory and self-documenting. Pidgin makes them short. The sprint writer doesn't need the implementation details because Pidgin handles implementation. The sprint writer needs the constraint and the judgment to validate whether the result meets it."

## Implication for Selective Injection

The principle registry stores MLD-compressed descriptions. When a sprint preamble includes "principles: [1, 3, 7]", the runner assembles three MLD descriptions. Total token cost for three principles: ~45 tokens. Total token cost for three full principle bodies: ~600 tokens. The MLD preamble is 13x smaller with no loss of constraint enforcement.

In a context window with a mission spec, function bodies, output schemas, and conversation history, those 555 saved tokens are attention budget recovered for the actual task.

## Implication for the Ouroboros

After each sprint cycle, Origami can be re-compressed. If the principles have evolved — new sub-rules added, old ones deprecated, language refined — the MLD pipeline produces updated compressions. Non-convergent principles after a revision flag ambiguity introduced by the edit. The tool judges the philosophy that created it, continuously.
