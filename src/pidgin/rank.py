"""Rank — ordinal evaluation. Returns options ordered by criteria.

rank() implements the call directly. main() is the CLI entry point that
goes through resolve() + run_skill so callers get file/stdin/literal
resolution and cost reporting.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pidgin.api import generate_sync
from pidgin.resolve import resolve
from pidgin.skill_runner import make_log, run_skill

_PROMPT_PATH = Path(__file__).parent / "prompts" / "rank.xml"


def rank(criteria: str, options: list[str], model: str = "gpt-4.1") -> str:
    """Rank options against criteria.

    Resolves each option via resolve() (file, directory, git ref, or string
    literal), builds the user message with numbered OPTION blocks, and calls
    generate_sync directly. Returns the model's text response (ranked list).
    """
    option_blocks = []
    for i, opt in enumerate(options, 1):
        content = resolve(opt, f"option-{i}")
        option_blocks.append(f"OPTION {i}: {opt}\n{content}")

    user_message = f"CRITERIA: {criteria}\n\n" + "\n".join(option_blocks)
    result = generate_sync(
        prompt=_PROMPT_PATH.read_text(),
        content=user_message,
        model=model,
    )
    if isinstance(result, list):
        return result[0].text
    return result.text


def main() -> int:
    log = make_log("rank")
    parser = argparse.ArgumentParser(prog="pidgin rank",
                                     description="Rank — ordinal evaluation")
    parser.add_argument("--criteria", required=True, help="What 'better' means")
    parser.add_argument("--options", required=True, nargs="+",
                        help="Options to rank (min 2)")
    parser.add_argument("--model", default="gpt-4.1",
                        help="OpenAI model (default: gpt-4.1)")
    args = parser.parse_args()

    if len(args.options) < 2:
        log("error: at least 2 options required")
        sys.exit(1)

    log(f"model={args.model} | {len(args.options)} options")

    option_blocks = []
    for i, opt in enumerate(args.options, 1):
        content = resolve(opt, f"option-{i}", log=log)
        option_blocks.append(f"OPTION {i}: {opt}\n{content}")

    user_message = f"CRITERIA: {args.criteria}\n\n" + "\n".join(option_blocks)

    run_skill(
        name="rank",
        user_message=user_message,
        model=args.model,
        prompt=_PROMPT_PATH.read_text(),
        log=log,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
