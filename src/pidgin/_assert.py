"""Pidgin-internal verification helper.

Routes through pidgin.api.generate_sync; uses the in-package assert
prompt copy at pidgin/prompts/assert.xml. The leading underscore marks
this module internal — callers outside pidgin should use the wiregrass
/assert skill.
"""
from __future__ import annotations

from pathlib import Path

from pidgin.api import generate_sync

_PROMPT_PATH = Path(__file__).parent / "prompts" / "assert.xml"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def run_assert(
    claim: str,
    a: str,
    b: str,
    model: str = "gpt-4.1",
) -> tuple[bool, str]:
    """Run the assert verification prompt.

    Returns (verdict, evidence). verdict is True iff the first non-blank
    line of the model's output starts with TRUE (case-insensitive).
    evidence is the full text body, stripped.
    """
    user_message = (
        f"CLAIM: {claim}\n\n"
        f"ARTIFACT A:\n{a}\n\n"
        f"ARTIFACT B:\n{b}"
    )
    result = generate_sync(
        prompt=_load_prompt(),
        content=user_message,
        model=model,
    )
    if isinstance(result, list):
        result = result[0]
    text = (result.text or "").strip()
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    verdict = first.upper().startswith("TRUE")
    return verdict, text
