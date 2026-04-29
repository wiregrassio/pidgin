#!/usr/bin/env python3
# MODULE: embed
# DOES: Generate an OpenAI embedding vector from text and write it as a JSON array to stdout.
# EMITS: JSON float array → stdout; dimension/char-count metadata → stderr
# READS: text from positional arg, --file flag, or stdin; OPENAI_API_KEY from env or local/.env
# IMPLEMENTS: text-embedding-3-small (default, 1536-dim) via OpenAI embeddings API
# DEPENDS: openai; python-dotenv (optional, for local/.env auto-load)

import argparse
import json
import os
import sys
from pathlib import Path

# Load credentials from local/.env (two levels up from tools/embed.py)
try:
    from dotenv import load_dotenv
    _local_env = Path(__file__).resolve().parent.parent / "local" / ".env"
    if _local_env.exists():
        load_dotenv(_local_env)
except ImportError:
    pass  # dotenv not installed — fall back to environment


def embed(text: str, api_key: str, model: str, dim: int) -> list[float]:
    """Call the OpenAI embeddings API and return the float vector."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    if len(text) > 30000:
        text = text[:30000]
    resp = client.embeddings.create(model=model, input=text, dimensions=dim)
    return resp.data[0].embedding


def main():
    """Parse CLI args, resolve input and API key, embed text, write JSON to stdout."""
    p = argparse.ArgumentParser(description="Generate an embedding vector")
    p.add_argument("text", nargs="?", default=None, help="Text to embed (or pipe via stdin)")
    p.add_argument("--file", "-f", default=None, help="Read text from file")
    p.add_argument("--dim", "-d", type=int, default=1536, help="Embedding dimensions (default: 1536)")
    p.add_argument("--model", "-m", default="text-embedding-3-small", help="Model (default: text-embedding-3-small)")
    p.add_argument("--api-key", default=None, help="OpenAI API key (default: OPENAI_API_KEY env)")
    p.add_argument("--compact", action="store_true", help="No indentation in JSON output")
    args = p.parse_args()

    # Resolve API key: flag > environment
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set and --api-key not provided", file=sys.stderr)
        return 1

    # Resolve input: --file > positional arg > stdin
    if args.file:
        text = open(args.file, encoding="utf-8").read()
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print("ERROR: provide text as argument, --file, or pipe via stdin", file=sys.stderr)
        return 1

    text = text.strip()
    if not text:
        print("ERROR: empty input", file=sys.stderr)
        return 1

    vector = embed(text, api_key, args.model, args.dim)

    # Vector to stdout (pipeable), metadata to stderr
    indent = None if args.compact else 2
    json.dump(vector, sys.stdout, indent=indent)
    sys.stdout.write("\n")
    print(f"{len(vector)} dimensions, {len(text)} chars input", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
