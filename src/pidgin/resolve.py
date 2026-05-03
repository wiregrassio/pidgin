#!/usr/bin/env python3
"""Shared input resolution for evaluation skills (assert, rank, score)."""

import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"__pycache__", "node_modules", ".venv", ".claude"}


def load_prompt(skill_dir: Path, filename: str = "prompt.xml", log=None):
    path = skill_dir / filename
    prompt = path.read_text()
    if log:
        log(f"prompt from {path.name} ({len(prompt.splitlines())} lines)")
    return prompt


def resolve(ref: str, label: str, log=None) -> str:
    if ref == "-":
        return sys.stdin.read()

    if "::" in ref:
        filepath, symbol = ref.split("::", 1)
        p = Path(filepath)
        if p.is_file():
            content = p.read_text()
            if log:
                log(f"{label}: {ref} (file::symbol, {len(content)} chars)")
            return f"--- {ref} ---\n{content}\n[Symbol: {symbol}]"

    p = Path(ref)
    if p.is_file():
        content = p.read_text()
        if log:
            log(f"{label}: {ref} (file, {len(content)} chars)")
        return f"--- {ref} ---\n{content}"
    if p.is_dir():
        parts = []
        for f in sorted(p.rglob("*")):
            rel = f.relative_to(p)
            if any(part in SKIP_DIRS for part in rel.parts[:-1]):
                continue
            if f.is_file() and f.suffix in (
                ".py", ".md", ".xml", ".toml", ".yaml", ".yml", ".json", ".txt",
            ):
                try:
                    parts.append(f"--- {f} ---\n{f.read_text()}")
                except (UnicodeDecodeError, PermissionError):
                    continue
        content = "\n".join(parts) if parts else f"[empty directory: {ref}]"
        if log:
            log(f"{label}: {ref} (dir, {len(parts)} files, {len(content)} chars)")
        return content

    if ".." in ref or ref.startswith("HEAD"):
        result = subprocess.run(
            ["git", "diff", ref], capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout:
            if log:
                log(f"{label}: {ref} (git diff, {len(result.stdout)} chars)")
            return f"--- git diff {ref} ---\n{result.stdout}"
        result = subprocess.run(
            ["git", "show", ref], capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout:
            if log:
                log(f"{label}: {ref} (git show, {len(result.stdout)} chars)")
            return f"--- git show {ref} ---\n{result.stdout}"

    if log:
        log(f"{label}: \"{ref}\" (string literal)")
    return ref
