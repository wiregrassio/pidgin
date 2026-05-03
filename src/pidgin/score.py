"""Score — single-axis cardinal evaluation (1-10).

score() implements the call directly (no internal helper). main() is the
CLI entry point that goes through resolve() + run_skill so callers get
file/stdin/literal resolution and cost reporting.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pidgin.api import generate_sync
from pidgin.resolve import resolve
from pidgin.skill_runner import make_log, run_skill

_PROMPT_PATH = Path(__file__).parent / "prompts" / "score.xml"


def score(quality: str, target: str, model: str = "gpt-4.1-mini") -> str:
    """Score a target on a single quality axis (1-10).

    Resolves `target` via resolve() (file, directory, git ref, or string
    literal), builds the user message, and calls generate_sync directly.
    Returns the model's text response (score + evidence).
    """
    content = resolve(target, "target")
    user_message = f"QUALITY: {quality}\n\nTARGET: {target}\n{content}"
    result = generate_sync(
        prompt=_PROMPT_PATH.read_text(),
        content=user_message,
        model=model,
    )
    if isinstance(result, list):
        return result[0].text
    return result.text


def main() -> int:
    log = make_log("score")
    parser = argparse.ArgumentParser(prog="pidgin score",
                                     description="Score — cardinal evaluation (1-10)")
    parser.add_argument("--quality", required=True, help="The axis to evaluate")
    parser.add_argument("--target", required=True, help="The target to evaluate")
    parser.add_argument("--model", default="gpt-4.1-mini",
                        help="OpenAI model (default: gpt-4.1-mini)")
    args = parser.parse_args()

    log(f"model={args.model}")
    content = resolve(args.target, "target", log=log)
    user_message = f"QUALITY: {args.quality}\n\nTARGET: {args.target}\n{content}"

    run_skill(
        name="score",
        user_message=user_message,
        model=args.model,
        prompt=_PROMPT_PATH.read_text(),
        log=log,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
