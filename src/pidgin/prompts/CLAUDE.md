# pidgin/prompts/

Discovery index for MLD convergence XML prompts. Provenance: tools/prompts/generate.md (v0.1).

## Files

### converge.xml
XML prompt for V2 MLD convergence generation. Migrated from generate.md in sprint tooling-v0.2 M3.

| Element | Count | Notes |
|---------|-------|-------|
| `rules/rule` | 8 | All hard rules from generate.md, verbatim |
| `examples/example` | 33 | Positive examples across all concision tiers and languages |
| `examples/anti_example` | 17 | Live validation failures + inline bad examples |
| `output_schema/field` | 3 | draft_1, draft_2, draft_3 |
| Cache boundary | 1 | `&lt;!-- ===== CACHE BOUNDARY ===== --&gt;` comment, once |

**Structure:**
- `<role>` — precision describer identity + three-draft discipline
- `<principles>` — placeholder for MLD-compressed principles (M5 injects)
- `<rules>` — 8 hard grammar rules (imperative verb, concision target, no hedging, etc.)
- `<concision_tiers>` — n=8/16/24/32 anatomy guides
- `<vocabulary>` — Origami service vocabulary (Convoy, Forklift, Catwalk, etc.)
- `<examples>` — 33 positive + 17 anti-examples by language and target tier
- `<!-- ===== CACHE BOUNDARY ===== -->` — preamble ends here
- `<payload>` — function body slot with [CDATA-OPEN]/[CDATA-CLOSE] placeholders
- `<output_schema>` — draft_1, draft_2, draft_3 field definitions

**Usage:**
```python
converge_xml = Path('pidgin/prompts/converge.xml').read_text()
result = await mld(input_text=fn_src, prompt="", prompt_text=converge_xml, ...)
```

**Downstream:** M5 templates.py wires `<principles>` injection and `[CDATA-OPEN/CLOSE]` substitution.

### gate.xml
XML validation gate prompt. Migrated from tools/prompts/validate.md in sprint tooling-v0.2 M4.

| Element | Count | Notes |
|---------|-------|-------|
| `criteria/criterion` | 11 | All grammar rules + selection criteria from validate.md |
| `examples/example` | 6 | 2 valid + 4 invalid, covering truncation, copula, hedging, passive |
| `output_schema/field` | 2 | `valid` (boolean), `reason` (string, ~60 tokens max) |
| Cache boundary | 1 | `<!-- ===== CACHE BOUNDARY ===== -->` comment, once |

**Structure:**
- `<role>` — validation gate identity: COMPLETE, CORRECT, FOLLOWS THE RULES
- `<criteria>` — 11 criteria: imperative verb, no hedging/filler, lossless, faithful, token count, no passive, no copula, complete sentence, specificity, behavior not name, domain vocabulary
- `<examples>` — 2 valid (embed_for_store, merge) + 4 invalid (truncated, copula, hedging, passive)
- `<!-- ===== CACHE BOUNDARY ===== -->` — preamble ends here
- `<payload>` — function body and candidate slots with `{{placeholders}}`
- `<output_schema strict="true">` — `valid` boolean + `reason` string

**Response format:** `json_schema` with `valid` (boolean) and `reason` (string). Use `claude-haiku-4-5` or better — gpt-4.1-nano misreads valid candidates.

**M4 gate regression (2026-04-27, claude-haiku-4-5):**

| Case | Candidate excerpt | verdict | reason excerpt |
|------|-------------------|---------|----------------|
| G1 | Call embed_text with the store model… | true | Imperative verb, 12 tokens, lossless |
| G2 | Parse CLI arguments for text, then print… | true | Imperative verb, 9 tokens, faithful |
| G3 | Merge delta into a copy of state, remove… | true | Imperative verb, 13 tokens, no truncation |
| G4 | Merge dictionaries a and b, prioritizing b… | true | Imperative verb, 11 tokens, active voice |
| G5 | Merge delta into a copy of state, | false | Trailing comma — truncated mid-clause |

**Downstream:** M5 templates.py wires `[CDATA-OPEN/CLOSE]` substitution and `{{placeholder}}` injection.

### templates.py
XML prompt assembler for the MLD convergence pipeline. Implements selective principle injection and cached_preamble/payload split. Provenance: NEW (sprint tooling-v0.2 M5).

**Exports:**
- `AssembledPrompt` — frozen dataclass: `cached_preamble`, `payload`, `full`, `principles_used`, `payload_vars`
- `Principle` — frozen dataclass: `id`, `title`, `mld`, `full`
- `PRINCIPLES` — `dict[int, Principle]`, populated at import from ORIGAMI.md (19 principles)
- `load_principle_registry(origami_path)` — parse ORIGAMI.md; returns `{}` + warning on missing/empty
- `assemble_xml_prompt(template_path, payload_vars, *, principles, registry)` — assemble template

**Behaviour:**
1. Reads template as text (no XML parsing; preserves `[CDATA-OPEN]/[CDATA-CLOSE]`).
2. Replaces `<principles>` inner content with `<principle id="{id}">{mld}</principle>` for each requested id.
3. Splits on the line containing `===== CACHE BOUNDARY =====` (line discarded).
4. Substitutes `{{key}}` in the payload region only; raises `KeyError` on missing keys.
5. Returns `AssembledPrompt`.

**Usage:**
```python
from pidgin.prompts import assemble_xml_prompt, PRINCIPLES

a = assemble_xml_prompt(
    "pidgin/prompts/converge.xml",
    {"file": "...", "name": "...", "line_start": "42", "function_body": "..."},
    principles=[1, 3, 7],
)
# a.cached_preamble -> everything above CACHE BOUNDARY (prompt-cacheable preamble)
# a.payload        -> everything below CACHE BOUNDARY (substituted payload + schema)
```

**Word-count proxy:** `len(text.split())`. 3 MLD principles = ~48 words vs ~613 words for full bodies.

### __init__.py
Module marker. Exports: `assemble_xml_prompt`, `AssembledPrompt`, `Principle`, `PRINCIPLES`, `load_principle_registry`.

## Validation (M3 regression, 2026-04-27)

All 4 reference probes passed at 15/15 convergence (threshold 8/15):

| Probe | Function | converged/15 | cluster |
|-------|----------|--------------|---------|
| P1 | embed_for_store (tools/utils/api.py) | 15/15 | True |
| P2 | main (tools/embed.py) | 15/15 | True |
| P3 | apply (tools/mld/probe.py) | 15/15 | True |
| P4 | merge (tools/mld/probe.py) | 15/15 | True |
