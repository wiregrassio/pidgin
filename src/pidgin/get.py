"""Symbol extraction with optional LanceDB description lookup.

Combines AST-based extraction (extract.py) with Nest record lookup
(nest.py) to return source, signature, and description in one call.
Graceful degradation: description is None when nest is not provided
or the symbol has not been indexed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pidgin.extract import extract_symbol_by_name
from pidgin.nest import Nest


# --------------------------------------------------------------------------- #
# Result model                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class GetResult:
    name: str
    kind: str
    source: str
    signature: str | None    # from AST (always available unless module)
    description: str | None  # from LanceDB (None if not indexed)
    file_path: str
    start_line: int
    end_line: int


# --------------------------------------------------------------------------- #
# get()                                                                       #
# --------------------------------------------------------------------------- #

def get(
    file_path: Path,
    name: str,
    nest: Nest | None = None,
) -> GetResult:
    """Extract a symbol by name from a Python file.

    Returns a GetResult with source from the AST and an optional
    description from LanceDB. When `nest` is None, the LanceDB
    lookup is skipped and `description` is None — graceful
    degradation for files that have not yet been indexed.

    Resolution steps:
      1. Read file source from disk.
      2. Use extract_symbol_by_name to get a Symbol; raise ValueError
         if the symbol is not found.
      3. If `nest` is provided, look up the LanceDB record by id
         '{repo_relative_file_path}::{name}'.
      4. Populate description from the record if it exists.
      5. Return GetResult with all fields populated.
    """
    file_path = Path(file_path)
    source = file_path.read_text(encoding="utf-8")

    sym = extract_symbol_by_name(source, name)
    if sym is None:
        raise ValueError(f"symbol {name!r} not found in {file_path}")

    description: str | None = None

    if nest is not None:
        repo_root = nest.repo_root
        try:
            rel_path = file_path.resolve().relative_to(repo_root)
            repo_rel = str(rel_path)
        except ValueError:
            repo_rel = str(file_path.resolve())

        symbol_id = f"{repo_rel}::{name}"
        record = nest.get_by_id(symbol_id)
        if record is not None:
            description = record.get("description")

    return GetResult(
        name=sym.name,
        kind=sym.kind,
        source=sym.source,
        signature=sym.signature,
        description=description,
        file_path=str(file_path),
        start_line=sym.start_line,
        end_line=sym.end_line,
    )


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import sys

    def log(msg: str) -> None:
        print(f"     get | {msg}", file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(prog="pidgin get",
                                     description="get — pidgin symbol extractor")
    parser.add_argument("--name", required=True,
                        help="Symbol name (supports Class.method)")
    parser.add_argument("--file", required=True, help="Python file")
    parser.add_argument("--source-only", action="store_true",
                        help="Skip LanceDB lookup (source only)")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        log(f"error: {file_path} is not a file")
        return 1

    nest: Nest | None = None
    if not args.source_only:
        nest = Nest()
        nest.ensure_table()

    try:
        result = get(file_path, args.name, nest=nest)
    except ValueError as exc:
        log(f"error: {exc}")
        return 1

    if result.description:
        print(f"# {result.description}")
    print(result.source, end="" if result.source.endswith("\n") else "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
