# pidgin v0.2 — NEW.
# Implements selective-principle injection per
# origami-compression-findings.md: ~45 tokens for 3 MLD principles vs
# ~600 tokens for full bodies. The cached_preamble/payload split makes
# the prompt-caching boundary explicit at call time.

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_CACHE_BOUNDARY_MARKER = "===== CACHE BOUNDARY ====="


@dataclass(frozen=True)
class Principle:
    id: int
    title: str           # e.g. "Daft Punk Principle"
    mld: str             # MLD-compressed body (single sentence)
    full: str | None     # full body if available, else None


@dataclass(frozen=True)
class AssembledPrompt:
    cached_preamble: str   # XML fragment, everything ABOVE the boundary
    payload: str           # XML fragment, everything BELOW (payload + schema)
    full: str              # cached_preamble + "\n" + payload
    principles_used: list[int]
    payload_vars: dict     # the substitution dict actually applied


def load_principle_registry(
    origami_path: str = "/project/ORIGAMI.md",
) -> dict[int, Principle]:
    """Read ORIGAMI.md and return a mapping of principle id -> Principle.

    Parses the summary table for id/title/mld, then collects full body text
    from the '## Principles in Detail' section. Returns {} and logs a warning
    if the file is missing or no principles parse.
    """
    try:
        with open(origami_path, encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        logger.warning("load_principle_registry: ORIGAMI.md not found at %s", origami_path)
        return {}

    # --- Parse summary table ---
    # Table row format: | ID | Title | MLD Description | Converged | Confidence |
    table_row_re = re.compile(
        r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*[✓✗\-]*\s*\|\s*[\d.]*\s*\|",
        re.MULTILINE,
    )
    principles: dict[int, dict] = {}
    for m in table_row_re.finditer(content):
        pid = int(m.group(1))
        title = m.group(2).strip()
        mld = m.group(3).strip()
        principles[pid] = {"id": pid, "title": title, "mld": mld, "full": None}

    if not principles:
        logger.warning("load_principle_registry: no principles parsed from %s", origami_path)
        return {}

    # --- Parse full bodies from '## Principles in Detail' and 'Part II/III' sections ---
    # Headers look like: ### N. Title  (in "## Principles in Detail")
    # or: ### N. Title (in "### N. Config as Control Surface" under Part II)
    # We want the body text for each numbered section.
    detail_section_re = re.compile(
        r"###\s+(\d+)\.\s+[^\n]+\n(.*?)(?=\n###\s+\d+\.|\n---|\n##\s|$)",
        re.DOTALL,
    )
    for m in detail_section_re.finditer(content):
        pid = int(m.group(1))
        body = m.group(2).strip()
        if pid in principles and body:
            principles[pid]["full"] = body

    result: dict[int, Principle] = {}
    for pid, data in principles.items():
        result[pid] = Principle(
            id=data["id"],
            title=data["title"],
            mld=data["mld"],
            full=data["full"],
        )

    return result


# Populated at import time
PRINCIPLES: dict[int, Principle] = load_principle_registry(
    origami_path="/Users/elliotwillis/Desktop/fe-toolkit/ORIGAMI.md"
)


def _inject_principles(xml_text: str, ids: list[int], registry: dict[int, Principle]) -> str:
    """Replace the inner content of <principles>...</principles> with selected principles.

    Uses text replacement (not DOM parsing) to preserve [CDATA-OPEN]/[CDATA-CLOSE] tokens.
    If ids is empty, the <principles> element is left with empty inner content.
    """
    if ids:
        sorted_ids = sorted(ids)
        lines = []
        for pid in sorted_ids:
            if pid in registry:
                mld = registry[pid].mld
                lines.append(f'    <principle id="{pid}">{mld}</principle>')
        inner = "\n" + "\n".join(lines) + "\n  "
    else:
        inner = ""

    # Replace everything between <principles> and </principles>
    replaced = re.sub(
        r"<principles>.*?</principles>",
        f"<principles>{inner}</principles>",
        xml_text,
        flags=re.DOTALL,
    )
    return replaced


def _substitute_placeholders(text: str, payload_vars: dict) -> str:
    """Replace {{key}} placeholders in text with values from payload_vars.

    Raises KeyError if a placeholder is present but the key is missing.
    """
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        if key not in payload_vars:
            raise KeyError(key)
        return str(payload_vars[key])

    return re.sub(r"\{\{(\w+)\}\}", replacer, text)


def _split_on_cache_boundary(text: str) -> tuple[str, str]:
    """Split text on the line containing '===== CACHE BOUNDARY ====='.

    The boundary line itself is discarded. Returns (preamble, payload).
    Raises ValueError if no boundary line is found.
    """
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if _CACHE_BOUNDARY_MARKER in line:
            preamble = "".join(lines[:i]).rstrip("\n")
            payload = "".join(lines[i + 1:]).lstrip("\n")
            return preamble, payload
    raise ValueError(
        f"Cache boundary marker '{_CACHE_BOUNDARY_MARKER}' not found in template"
    )


def assemble_xml_prompt(
    template_path: str,
    payload_vars: dict,
    *,
    principles: list[int] = (),
    registry: dict[int, Principle] | None = None,
) -> AssembledPrompt:
    """Assemble an XML prompt template with principle injection and placeholder substitution.

    Reads the template as text, injects requested principles into the <principles>
    block, substitutes {{key}} placeholders in the payload region from payload_vars,
    splits at the CACHE BOUNDARY comment, and returns an AssembledPrompt.

    Raises KeyError if a {{placeholder}} in the payload region has no matching key
    in payload_vars. Raises ValueError if the template has no CACHE BOUNDARY line.
    """
    if registry is None:
        registry = PRINCIPLES

    # Step 1: Read template as text
    with open(template_path, encoding="utf-8") as fh:
        template_text = fh.read()

    # Step 2: Inject principles into <principles> block
    ids_list = list(principles) if principles else []
    template_text = _inject_principles(template_text, ids_list, registry)

    # Step 3: Split on cache boundary
    cached_preamble, payload_region = _split_on_cache_boundary(template_text)

    # Step 4: Substitute {{key}} placeholders in the payload region only
    # This ensures KeyError is raised for missing keys used in the payload.
    payload_region = _substitute_placeholders(payload_region, payload_vars)

    full = cached_preamble + "\n" + payload_region

    return AssembledPrompt(
        cached_preamble=cached_preamble,
        payload=payload_region,
        full=full,
        principles_used=sorted(set(ids_list)),
        payload_vars=dict(payload_vars),
    )
