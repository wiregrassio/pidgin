# Tooling v0.4 — Context Index

Read in this order. Each document builds on the previous.

## Required Reading

1. **v4-founding-record.md** — What v0.3 delivered, what broke during real-world indexing, what the operator wants for v0.4. Start here.

2. **operational-reliability.md** — The blocking track: incremental writes, graceful shutdown, progress tracking, abandoned batch recovery. Nothing else ships until these are solid.

3. **wishlist.md** — Everything else accumulated across v0.2 and v0.3: fine-tuning, prompt audits, model routing experiments, tree-sitter, carry-forward debt.

4. **observed-failures.md** — Raw failure log from the first real-world indexing attempt against the OpenAI Python SDK. What happened, why, and what it cost.

5. **model-strategy.md** — Model routing consolidation to OpenAI, agent file rewrite scope, project restructuring (venv, tools/, templates/, docs), and Pidgin-as-agent-tool scoping.

6. **roadmap.md** — v0.4 through v1.0. What's achievable now, what's next sprint, and where we're going. The designer reads this for scope boundaries.

7. **sprint-conventions.md** — Mission grammar, tier assignments, review flags, phase structure, carry-forward tracking. How to write a design.md.

## Cross-References

- v0.3 sprint plan: `local/sprints/tooling-v0.3/sprint.xml`
- v0.3 execution log: `local/sprints/tooling-v0.3/log.md`
- v0.3 design document: `local/sprints/tooling-v0.3/design.md`
- v0.3 gate decision: `local/sprints/tooling-v0.3/gate.xml`
- v0.3 founding record: `local/sprints/tooling-v0.3/context/v3-founding-record.md`
- v0.3 stress test findings: `local/sprints/tooling-v0.3/context/stress-test-findings.md`
- v0.2 execution log: `local/sprints/tooling-v0.2/log.md`
- Pidgin package: `pidgin/`
- Pidgin CLAUDE.md: `pidgin/CLAUDE.md`
- Prompting reference: `.claude/skills/cleanup-prompt/prompting-reference.md`
- Model selector: `local/scratch/model_selector.xml`
