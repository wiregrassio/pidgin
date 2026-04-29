# Prompting Guide and Model Selection

## What Was Built

### cleanup-prompt skill

Location: `.claude/skills/cleanup-prompt/`

Two files:
- `SKILL.md` — skill definition, invocation (--audit, --teach), the ten principles as quick reference
- `prompting-reference.md` — full 13-section reference (context engineering, prompt structure, examples, output control, reasoning, tool use, agentic systems, CLAUDE.md, coding patterns, evaluation, cost/routing, anti-sycophancy, common mistakes)

Built from: official Anthropic/OpenAI/Gemini guides + deep research covering Willison, Husain, Yan, Ronacher, Steinberger, Cherny, Manus, Chroma, and academic papers through April 2026.

Design: markdown body with XML tags at structural boundaries. Model-agnostic — no model-specific quirks. Progressive disclosure — name+description always loaded, full reference on trigger.

### model_selector.xml

Location: `local/scratch/model_selector.xml`

Per-model entries for: gpt-5.5, gpt-5.4 (+ mini/nano note), gpt-5.3-codex, gpt-5.2, gpt-5.1, gpt-5, gpt-4.1. Each has: abstract, best-for, weak-at, quirk, prompting-style, pairs-with cross-references, copy-pasteable prompt snippets.

Anthropic models not yet added. No routing table yet — will be added once empirical testing establishes model-task mappings.

Status: complete for OpenAI. Separate operation still digesting per-model guides.

## Key Findings from Research

### What changed since 2024

1. **Context engineering replaced prompt engineering.** Quality is determined by total token state, not magic phrases.
2. **Measurement-driven iteration replaced vibes.** Binary LLM-as-judge eval pipelines validated against domain experts.
3. **"Think step by step" hurts reasoning models.** CoT delivers near-zero gain, adds 20-80% latency, and can cause up to 36-point accuracy drops.
4. **CLAUDE.md files degrade past 150 lines.** Gains reverse. If a rule gets ignored, prune — don't add emphasis.
5. **Context rot hits well before the advertised window.** 60% is the practical ceiling for agentic work.
6. **Fresh context + structured handoff beats long sessions.** The single most reliable productivity pattern.

### What we should validate on our own prompts

converge.xml audit findings:
1. **17 anti-examples may anchor the model on failure patterns.** Test removal — if convergence holds, cut them and save ~2K tokens.
2. **Duplicate example** (ex5 and ex_rust_simple are the same clamp function).
3. **Role section has contradictory framing** ("increasing refinement" vs "each one sentence").
4. **No explicit stopping condition** — add one.
5. **33+17 examples is heavy.** Could probably get same signal with 15-20 positive, zero negative.
6. **Use real examples from runs** instead of hand-crafted ones. Have haiku pick the best converged winners from M3/M12 data.

gate.xml and expand.xml should get the same audit treatment.

## Implications for Pidgin

### Model routing under consideration

| Task | Current | Candidate | Why |
|------|---------|-----------|-----|
| Generation (flock) | gpt-4.1-nano | gpt-5.1 at effort=none | Better calibration, direct 4.1 successor |
| Gate validation | claude-haiku-4-5 | gpt-5.4-mini | Consolidate to single provider |
| Architecture | Opus (via Claude Code) | No change | Judgment, not volume |

Testing plan: run M4's G1-G5 gate probes against gpt-5.4-mini and gpt-4.1 with tool-use. If either matches haiku accuracy, consolidate.

### Fine-tuning replaces prompts

converge.xml is 7.5K tokens of preamble. Every index run produces labeled training data. Fine-tune a nano-class model on converged winners. If it matches converge.xml+nano accuracy, the fine-tuned model IS the prompt — saves 7.5K tokens per call, eliminates the batch payload size problem, and makes the flock faster.

Same for gate: every gate call produces (description, valid/invalid, reason). Fine-tune replaces gate.xml.

### Skills rewrite

With Pidgin providing primitives, skills become thin orchestration:
- `/digest` → `pidgin index . --summarize`
- `/embed` → `pidgin index .`
- `/dissect` → cross-module analysis via `pidgin depends` + semantic queries
- `/finalize` → `pidgin index` + `pidgin egg` + `technologic`
- `/cleanup-prompt` → stays as-is (not Pidgin-dependent)
