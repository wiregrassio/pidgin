# Model Strategy and Project Restructuring

## Model Routing Decision

Based on model_research.xml data (verified 2026-04-27), the operator is
consolidating to OpenAI for all API calls. Anthropic API is being dropped
except for Opus 4.6 via Claude Code (subscription, not API).

### Rationale

| Task | Current | Proposed | Cost delta |
|------|---------|----------|------------|
| Generation (flock) | gpt-4.1-nano ($0.10/$0.40) | gpt-4.1-nano (no change) | — |
| Gate validation | claude-haiku-4-5 ($1.00/$5.00) | gpt-4.1-mini ($0.40/$1.60) | -60% input, -68% output |
| Embeddings | text-embedding-3-small ($0.02/M) | no change | — |
| Architecture/reasoning | Opus via Claude Code ($0/token) | no change | — |
| Sprint execution | Sonnet via Claude Code ($0/token) | no change | — |

Key factors:
- gpt-4.1-nano is the ONLY nano-class model with fine-tuning (SFT, DPO, RFT)
- gpt-4.1-mini supports all three fine-tuning methods at 2.5x cheaper than haiku
- Anthropic has no fine-tuning API (Bedrock only, requires Provisioned Throughput)
- Anthropic Tier 1 rate limits are 10x worse than OpenAI for request-bound workloads
- Fine-tuning generation + gate on OpenAI 4.1 family eliminates the 7.5K preamble,
  solving the batch payload ceiling and reducing per-function cost ~50x

### Validation Required

Before switching gate calls: run M4's G1-G5 gate probes against gpt-4.1-mini
(non-reasoning, literal instruction following, tool-use structured output).
If accuracy matches haiku, switch. If not, try gpt-5.4-mini (reasoning).

### Fine-Tuning Pipeline (OpenAI 4.1 family)

gpt-4.1-nano for generation: SFT on converged MLD winners
gpt-4.1-nano for gate: SFT on (description, valid/invalid, reason) triples
gpt-4.1-mini for complex gate: SFT or DPO on borderline validation cases

Distillation path: capture stored completions from gpt-5.4 in production,
filter via evals, use as SFT data for 4.1-nano. This is OpenAI's canonical
large→small workflow.

## Agent File Rewrite

Current agent files (Execute/Reason/Scout → Sonnet/Opus/Haiku) are several
generations old. v0.4 scope:

- Update model references (haiku → gpt-4.1-mini for any direct API calls)
- Add Pidgin tool instructions: "Before modifying code, run pidgin query and
  pidgin depends. After modifying code, run pidgin index --sync on changed files."
- Trim instructions using prompting-reference.md best practices
- Do NOT restructure the Execute/Reason/Scout taxonomy — that's v0.5

## Project Restructuring

### venv location
Move tools/.venv → .venv at project root. The venv serves the whole project.

### tools/ directory
Cannot delete yet — 5 skill files depend on it. Sequence:
1. v0.4: rewrite skills to use Pidgin verbs
2. v0.4: mark tools/ as "legacy, do not add new code" in CLAUDE.md
3. v0.5: delete tools/ when zero dependents remain

### templates/ directory
Move sprint-package template into .claude/skills/new-sprint/templates/.
Delete templates/ at root.

### pidgin.egg-info/
Already in .gitignore. Recreated automatically by pip install -e. Ignore.

### pyproject.toml
Correct location is fe-toolkit root. Pidgin is a package inside this workspace.
Moves to its own repo root when wiregrass/pidgin ships.

## Documentation Restructuring

### docs/pidgin.md (new)
"What is Pidgin, how does it work, what can it do." Not a sprint log.
Audience: someone who needs to understand Pidgin without reading 3 sprints.

### CLAUDE.md
Audit with cleanup-prompt skill. Currently over 150 lines with stale references.
Prune to budget.

### ORIGAMI.md
Audit carefully — templates.py parses it for the 19 principles. Restructuring
must not break the parser. Audit first, restructure second, verify principle
extraction.

### Architecture.md
Lowest priority. Audit when everything else stabilizes.

## Pidgin as Agent Tool

v0.4 scope: agents use Pidgin alongside bash, not instead of it.

Add to agent instructions:
- Before modifying code: `pidgin query` + `pidgin depends` for context
- After modifying code: `pidgin index --sync` on changed files
- For understanding a codebase: `pidgin query` instead of grep

This covers ~10-15% of agent operations. The remaining 85% (file I/O, tests,
git, scripts) stays in bash. The 90% Pidgin vision requires write verbs,
test integration, and git operations that don't exist yet — v0.6+.

### Low-hanging fruit for Pidgin verb additions
Things bash does that Pidgin could wrap with MLD awareness:
- `pidgin diff` — show what changed with MLD description delta
- `pidgin status` — git status enriched with function-level descriptions
- `pidgin review` — diff + query + depends for a change set
These are v0.5+ but worth noting for the roadmap.
