"""Assert — public binary verification verb.

Wraps the assert prompt at pidgin/prompts/assert.xml. verify() is a
delegating alias of pidgin._assert.run_assert; main() is the CLI
entry point that goes through resolve()+run_skill so callers get
file/stdin/literal resolution and cost reporting.
"""
from __future__ import annotations
import argparse
from pathlib import Path

from pidgin._assert import run_assert
from pidgin.resolve import resolve
from pidgin.skill_runner import make_log, run_skill

_PROMPT_PATH = Path(__file__).parent / "prompts" / "assert.xml"


def verify(claim: str, a: str, b: str, model: str = "gpt-4.1") -> tuple[bool, str]:
    """Public alias for the internal assert helper."""
    return run_assert(claim, a, b, model)


def main() -> int:
    log = make_log("assert")
    parser = argparse.ArgumentParser(prog="pidgin assert")
    parser.add_argument("--claim", required=True)
    parser.add_argument("--a", required=True, dest="artifact_a")
    parser.add_argument("--b", required=True, dest="artifact_b")
    parser.add_argument("--model", default="gpt-4.1")
    args = parser.parse_args()
    log(f"model={args.model}")
    a = resolve(args.artifact_a, "--a", log=log)
    b = resolve(args.artifact_b, "--b", log=log)
    user = f"CLAIM: {args.claim}\n\nARTIFACT A:\n{a}\n\nARTIFACT B:\n{b}"
    run_skill(name="assert", user_message=user, model=args.model,
              prompt=_PROMPT_PATH.read_text(), log=log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
