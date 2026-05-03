#!/usr/bin/env python3
"""Shared runner for thin skill scripts.

Centralizes the boilerplate every eval/reasoning skill repeats:
- log function bound to a skill name
- prompt loading (from file or passed directly)
- generate_sync call with cost reporting
- multi-response output formatting
"""

import sys
from pathlib import Path
from typing import Callable

from pidgin.api import generate_sync, cost_totals
from pidgin.resolve import load_prompt


def make_log(name: str) -> Callable[[str], None]:
    pad = name.rjust(8)

    def log(msg: str):
        print(f"{pad} | {msg}", file=sys.stderr, flush=True)

    return log


def run_skill(
    *,
    name: str,
    user_message: str,
    model: str,
    skill_dir: Path | None = None,
    prompt: str | None = None,
    prompt_filename: str = "prompt.xml",
    n: int = 1,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    """Run a skill end-to-end: load prompt, call API, print results.

    Either `prompt` (passed directly) or `skill_dir` (load from disk) must be
    provided. Prints generated text to stdout, multi-response output is split
    by `---` separators. Cost summary is logged to stderr.
    """
    if log is None:
        log = make_log(name)

    if prompt is None:
        if skill_dir is None:
            raise ValueError("run_skill requires either prompt or skill_dir")
        prompt = load_prompt(skill_dir, filename=prompt_filename, log=log)

    log("calling API...")
    kwargs: dict = {
        "prompt": prompt,
        "content": user_message,
        "model": model,
        "n": n,
        "reasoning_effort": reasoning_effort,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    result = generate_sync(**kwargs)

    totals = cost_totals()
    log(f"done | ${totals.dollars:.4f}")

    if isinstance(result, list):
        for i, r in enumerate(result):
            if i > 0:
                print("\n---\n")
            print(r.text)
    else:
        print(result.text)
