# Tooling v0.3 — Context Index

Read in this order. Each document builds on the previous.

## Required Reading

1. **v3-founding-record.md** — What v0.2 delivered, what broke during stress testing, what design decisions were made in the post-sprint session. Start here.

2. **stress-test-findings.md** — First real-world Pidgin run against the OpenAI Python SDK. Every bug discovered, root causes, and fixes required.

3. **verb-redesign.md** — Kill compress, add summarize/egg/depends. The four human verbs. Query normalization. Flag conventions.

4. **pipeline-improvements.md** — Batch chunking, draft stratification (per-draft centroid tracking), adaptive stopping, import/signature extraction, fine-tuning data collection.

5. **prompting-guide.md** — The cleanup-prompt skill, the prompting reference, the model selector. What we learned from the deep research and how it changes Pidgin's prompts.

## Cross-References

- v0.2 sprint plan: `local/sprints/tooling-v0.2/sprint.xml`
- v0.2 execution log: `local/sprints/tooling-v0.2/log.md`
- v0.2 design document: `local/sprints/tooling-v0.2/design.md`
- v0.2 gate decision: `local/sprints/tooling-v0.2/probes/m14-bidirectional/GATE.md`
- v0.2 progress snapshot: `local/sprints/tooling-v0.2/progress-snapshot.md`
- v0.1 context: `local/sprints/tooling-v0.1/context/INDEX.md`
- Prompting reference: `.claude/skills/cleanup-prompt/prompting-reference.md`
- Model selector (WIP): `local/scratch/model_selector.xml`
