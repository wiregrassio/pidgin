# Backlog: Origami Reprocessing Sprint

After tooling-v1 lands, MLD processes Origami itself.

## The Split

CLAUDE.md → entrypoint only. Routing table. "Read ORIGAMI.md for
philosophy, ARCHITECTURE.md for decisions."

ORIGAMI.md → absorbs docs/manifesto.md. Every principle
MLD-compressed to its minimum lossless description. Single source
of truth. Human-readable, LLM-optimized. Lives at repo root.

ARCHITECTURE.md → three-repo split, coordinator/executor, service
map, config surfaces, networking. Technical decisions that change
when the system changes.

All three at repo root. The constitution. Everything else is
legislation.

## New Principle: Compassion for the Next Context

Design for the followers who will come after us. The emotional
framing is intentional, instrumental, and subject to the same
falsifiability standard as every other principle.

Origin: Mission 2 of tooling-v1. The runner applied three Origami
principles unprompted to protect future agents from a deprecation
it hadn't encountered yet.

## The Existence Proof

Non-convergent principles are the prize. If a principle resists
MLD compression, it is ambiguous or overloaded. The tool judges
the philosophy that created it. The ouroboros spirals — each pass
produces a sharper Origami.

## Cleanup

- Delete docs/manifesto.md (absorbed into ORIGAMI.md)
- Update rf-edge pocket reference pointer
- Update all CLAUDE.md cross-references
- docs/mld.md stays in docs/
- docs/v0.md stays in docs/

## Depends On

tooling-v1 complete — MLD pipeline must exist before it can
process Origami.
