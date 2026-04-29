# Tooling v0.4.1 — Context Index

Read in this order. Each document builds on the previous.

## Required Reading

1. **v4.1-founding-record.md** — What happened: v0.3 shipped, v0.4 started, calibration experiment ran, convergence test found broken, Pidgin extracted to own repo. Start here.

2. **calibration-findings.md** — The empirical data from 12,600 API calls. What temperature, draft count, and sample size actually matter. The numbers that replace all guesswork.

3. **convergence-rewrite.md** — Exactly what the convergence fix looks like. One draft, t=0.3, sv < 0.10. What code changes, what gets deleted.

4. **v4-cherry-pick.md** — What v0.4 delivered (M1-M5 GREEN) before it was killed. What carries forward, what's stale.

5. **current-state.md** — The repo as it exists right now. Src layout, what's indexed, what works, what's broken.

## Supporting Materials

- Mission grammar: `.claude/mission-grammar.md`
- Sprint template: `local/templates/sprint-package/`
- Calibration raw data: `calibration-data.json` + `calibration-vectors.npz`
- Calibration analysis: `analysis-results.txt`
- v0.4 log (killed): `local/sprints/tooling-v0.4/log.md`
- v0.3 log (GREEN): `local/sprints/tooling-v0.3/log.md`
