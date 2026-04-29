# Tooling v0.2 — Context Index

Read in this order. Each document builds on the previous.

## Required Reading

1. **v2-founding-record.md** — What v0.1 proved, what v0.1 disproved, what outgrew v0.1. Start here. This is the empirical ground you stand on.

2. **pidgin-architecture.md** — The Pidgin identity as it crystallized during v0.1 execution. Four CLI verbs, three permission flags, the nest convention, the verb vocabulary for LLM interaction. This document captures what Pidgin IS, distinct from the tools v0.1 built.

3. **write-model.md** — The four write modes (index, update, new, compress) and why v0.1's CRISPR-for-everything approach was wrong. File-level commit bracketing versus operation-level. The transaction context manager pattern.

4. **xml-prompt-format.md** — The decision to move all Pidgin prompts and artifacts from markdown to XML-tagged documents. Anthropic's official guidance, the caching implications, the source annotation convention.

5. **batch-dispatch.md** — OpenAI Batch API integration. Auto-threshold (under 10 tasks: synchronous, over 10: batch). Two-round-trip pattern for MLD: generation batch, then embedding batch. Cost and rate limit implications.

6. **bidirectional-mld.md** — MLD convergence works in both directions: code→description and description→code. The convergence geometry doesn't know what it's converging on. Implications for sprint planning and code generation.

7. **origami-compression-findings.md** — What the Origami reprocessing revealed about MLD quality, the difference between principles and practice, and the operator's observation that supporting detail in principle bodies is pedagogy, not specification. The 0.80 confidence signals and what they mean.

8. **adaptive-candidates.md** — The proposed improvement to the convergence pipeline: if 3/5 converge, run 5 more and retest. Cost-of-uncertainty analysis.

## Cross-References

- v0.1 sprint plan: `local/sprints/tooling-v0.1/sprint.md`
- v0.1 execution log: `local/sprints/tooling-v0.1/log.md`
- v0.1 design document: `local/sprints/tooling-v0.1/design.md`
- v0.1 validation report: `local/sprints/tooling-v0.1/context/v2-mld-validation.md`
- v0 founding record: `local/sprints/tooling-v0.1/context/v1-founding-record.md`
