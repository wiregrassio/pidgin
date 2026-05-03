"""File- and directory-level Python code indexer for pidgin.

Reads Python source, extracts AST symbols, calls the LLM for
one-sentence descriptions (structured JSON), embeds descriptions and
signatures, and upserts everything into LanceDB via Nest.

Import edges are resolved to repo-internal file paths and written
into the ImportGraph.  Incremental re-indexing is driven by SHA-256
source hashes.  All indexing is sequential (no threads, no async).

Caller responsibility for graph persistence:
    graph = ImportGraph.load(nest.nest_path / "imports.json")
    index_directory(directory, nest, graph, ...)
    graph.save(nest.nest_path / "imports.json")
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pidgin.api import embed_for_store_sync, generate_sync
from pidgin.extract import (
    extract_imports,
    extract_symbols,
    resolve_import_to_file,
)
from pidgin.graph import ImportGraph
from pidgin.nest import Nest

# --------------------------------------------------------------------------- #
# LLM prompt and JSON schema                                                   #
# --------------------------------------------------------------------------- #

INDEX_SYSTEM_PROMPT = (
    "You are a code documentation assistant. The user provides Python "
    "source. Return a JSON object describing the module and every "
    "function, class, and method in it. Each description is one "
    "sentence starting with an imperative verb (Parse, Return, "
    "Build — not 'This function parses'). The 'parent' field is the "
    "class name for methods, null for top-level functions and classes."
)

INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "module_description": {"type": "string"},
        "symbols": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["function", "class", "method"],
                    },
                    "parent": {"type": ["string", "null"]},
                    "description": {"type": "string"},
                },
                "required": ["name", "kind", "parent", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["module_description", "symbols"],
    "additionalProperties": False,
}

# --------------------------------------------------------------------------- #
# Result dataclass                                                              #
# --------------------------------------------------------------------------- #

@dataclass
class IndexResult:
    file_path: str
    symbols_found: int       # from AST
    symbols_described: int   # from model (had descriptions)
    skipped: bool            # True if source_hash matched
    error: str | None

# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

_EXCLUDE_DIRS = {".pidgin", "__pycache__", ".venv"}


def collect_repo_files(repo_root: Path) -> set[str]:
    """Return the set of repo-relative *.py paths under repo_root.

    Excludes .pidgin/, .claude/.venv/, and __pycache__ directories.
    Paths are normalized to forward slashes.

    FLAW-8 fix: single source of truth for the repo's index scope.
    Both index_directory and index_file (via caller) use this helper.
    """
    repo_root = repo_root.resolve()
    result: list[str] = []
    for py_file in repo_root.rglob("*.py"):
        rel = py_file.relative_to(repo_root)
        parts = rel.parts
        # Skip if any path component is an excluded directory name.
        if any(p in _EXCLUDE_DIRS for p in parts[:-1]):
            continue
        # Also exclude .claude/.venv/ subtree specifically.
        if len(parts) >= 2 and parts[0] == ".claude" and parts[1] == ".venv":
            continue
        result.append(rel.as_posix())
    return set(result)


def _git_metadata(file_path: Path, repo_root: Path) -> tuple[str, str]:
    """Return (iso_timestamp, author) from git log for file_path.

    Falls back to current ISO timestamp and 'unknown' if git is
    unavailable or the file is untracked.
    """
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%aI|%aN", "--", str(rel)],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if out and "|" in out:
            ts, author = out.split("|", 1)
            return ts.strip(), author.strip()
    except Exception:
        pass
    ts = datetime.now(tz=timezone.utc).isoformat()
    return ts, "unknown"


def _repo_id(repo_root: Path) -> str:
    """Return owner/repo from git remote origin, or repo_root.name."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        # Handles https://github.com/owner/repo.git and git@github.com:owner/repo.git
        if url:
            url = url.rstrip("/").removesuffix(".git")
            if ":" in url and "@" in url:
                # SSH style: git@github.com:owner/repo
                owner_repo = url.split(":")[-1]
            else:
                # HTTPS style: https://github.com/owner/repo
                parts = url.split("/")
                owner_repo = "/".join(parts[-2:]) if len(parts) >= 2 else repo_root.name
            return owner_repo
    except Exception:
        pass
    return repo_root.name


def _symbol_id(rel_path: str, sym_name: str, kind: str, parent: str | None) -> str:
    """Compute the canonical ID for a symbol record."""
    if kind == "method":
        # sym_name for methods is "ClassName.method_name" from AST
        return f"{rel_path}::{sym_name}"
    elif kind == "class":
        return f"{rel_path}::{sym_name}"
    else:  # function
        return f"{rel_path}::{sym_name}"


def _module_id(rel_path: str) -> str:
    return f"{rel_path}::__module__"


def _bare_name(sym_name: str) -> str:
    """Return the un-dotted method name from 'ClassName.method_name'."""
    return sym_name.split(".")[-1]

# --------------------------------------------------------------------------- #
# Core indexing                                                                 #
# --------------------------------------------------------------------------- #

def index_file(
    file_path: Path,
    nest: Nest,
    graph: ImportGraph,
    repo_files: set[str],
    model: str = "gpt-5.4-mini",
    effort: str = "medium",
    force: bool = False,
) -> IndexResult:
    """Index one Python file. Sequential, single-threaded.

    Steps:
    1. Read source, compute SHA-256 hash.
    2. Check for unchanged source (incremental skip).
    3. Extract AST symbols and imports.
    4. Resolve imports to repo file paths.
    5. Call LLM for structured descriptions.
    6. Match model descriptions to AST symbols.
    7. Embed descriptions and signatures in two batched calls.
    8. Build LanceDB records (one per symbol + one module record).
    9. Delete old records, upsert new ones, update graph.
    """
    rel_path = file_path.resolve().relative_to(nest.repo_root.resolve()).as_posix()

    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return IndexResult(
            file_path=rel_path,
            symbols_found=0,
            symbols_described=0,
            skipped=False,
            error=f"read error: {exc}",
        )

    # Step 1 — hash
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()

    # AD-8 / FLAW-4 — fetch existing records unconditionally for
    # mutation_count inheritance. The early-skip path below still uses
    # this same `existing` value to decide whether the source matches.
    existing = nest.get_by_file(rel_path)
    prior_by_id: dict[str, int] = {
        r["id"]: r.get("mutation_count", 0) for r in existing
    }

    # Step 2 — incremental skip
    if not force:
        if existing:
            stored_hash = existing[0].get("source_hash", "")
            if stored_hash == source_hash:
                return IndexResult(
                    file_path=rel_path,
                    symbols_found=0,
                    symbols_described=0,
                    skipped=True,
                    error=None,
                )

    # Step 3 — AST extraction
    try:
        symbols = extract_symbols(source)
    except Exception as exc:
        return IndexResult(
            file_path=rel_path,
            symbols_found=0,
            symbols_described=0,
            skipped=False,
            error=f"AST parse error: {exc}",
        )

    # Step 4 — import resolution
    try:
        imports = extract_imports(source, file_path)
    except Exception:
        imports = []

    resolved = [
        resolve_import_to_file(m, nest.repo_root, repo_files)
        for m in imports
    ]
    resolved_files = sorted({r for r in resolved if r is not None})

    # Step 5 — LLM call for descriptions
    model_result: dict | None = None
    try:
        gen_result = generate_sync(
            prompt=INDEX_SYSTEM_PROMPT,
            content=source,
            model=model,
            schema=INDEX_SCHEMA,
            reasoning_effort=effort,
        )
        # generate_sync returns GenerateResult or list[GenerateResult]
        if isinstance(gen_result, list):
            gen_result = gen_result[0]
        if gen_result.structured and isinstance(gen_result.structured, dict):
            model_result = gen_result.structured
    except Exception:
        model_result = None

    # FLAW-3 — surface a silent LLM failure as a non-None error string
    # so callers (e.g. pidgin.flush) can raise instead of producing
    # records with description=None.
    llm_error: str | None = None
    if model_result is None:
        llm_error = "LLM returned no structured output"

    # Step 6 — match model descriptions to AST symbols
    # The model returns bare method names; AST sym.name for methods is
    # "ClassName.method_name".  We match on (parent, bare_name).
    desc_lookup: dict[tuple[str | None, str], str] = {}
    module_desc: str | None = None
    if model_result is not None:
        for model_sym in model_result.get("symbols", []):
            key = (model_sym.get("parent"), model_sym.get("name"))
            desc = model_sym.get("description")
            if desc:
                desc_lookup[key] = desc
        module_desc = model_result.get("module_description") or None

    # Step 7 — build embedding item lists
    # desc_items: (symbol_index, text); sentinel -1 for module description
    desc_items: list[tuple[int, str]] = []
    for i, sym in enumerate(symbols):
        bare = _bare_name(sym.name)
        desc = desc_lookup.get((sym.parent, bare))
        if desc:
            desc_items.append((i, desc))

    if module_desc:
        desc_items.append((-1, module_desc))

    sig_items: list[tuple[int, str]] = [
        (i, sym.signature) for i, sym in enumerate(symbols)
        if sym.signature  # never embed empty strings
    ]

    # Step 8 — embed (two API calls max, both batched)
    ZERO: list[float] = [0.0] * 256

    if desc_items:
        try:
            desc_vecs_raw = embed_for_store_sync([d for _, d in desc_items])
        except Exception:
            desc_vecs_raw = [ZERO] * len(desc_items)
    else:
        desc_vecs_raw = []

    if sig_items:
        try:
            sig_vecs_raw = embed_for_store_sync([s for _, s in sig_items])
        except Exception:
            sig_vecs_raw = [ZERO] * len(sig_items)
    else:
        sig_vecs_raw = []

    desc_vecs: dict[int, list[float]] = {
        i: v for (i, _), v in zip(desc_items, desc_vecs_raw)
    }
    sig_vecs: dict[int, list[float]] = {
        i: v for (i, _), v in zip(sig_items, sig_vecs_raw)
    }

    # Step 8b — git metadata and repo_id (shared across all records)
    last_modified, git_author = _git_metadata(file_path, nest.repo_root)
    rid = _repo_id(nest.repo_root)

    # Step 9 — build records
    records: list[dict] = []

    symbols_described = 0

    # One record per AST symbol
    for i, sym in enumerate(symbols):
        bare = _bare_name(sym.name)
        desc = desc_lookup.get((sym.parent, bare))
        if desc:
            symbols_described += 1

        sym_id = _symbol_id(rel_path, sym.name, sym.kind, sym.parent)
        if existing:
            mutation_count = prior_by_id.get(sym_id, 0) + 1
        else:
            mutation_count = 0
        record = {
            "id": sym_id,
            "file_path": rel_path,
            "kind": sym.kind,
            "description": desc,
            "description_vector": desc_vecs.get(i, ZERO),
            "signature": sym.signature or "",
            "signature_vector": sig_vecs.get(i, ZERO),
            "source_hash": source_hash,
            "last_modified": last_modified,
            "git_author": git_author,
            "mutation_count": mutation_count,
            "repo_id": rid,
        }
        records.append(record)

    # Module record (kind='module', name='__module__')
    mod_id = _module_id(rel_path)
    if existing:
        module_mutation_count = prior_by_id.get(mod_id, 0) + 1
    else:
        module_mutation_count = 0
    module_record = {
        "id": mod_id,
        "file_path": rel_path,
        "kind": "module",
        "description": module_desc,
        "description_vector": desc_vecs.get(-1, ZERO),
        "signature": "",
        "signature_vector": ZERO,
        "source_hash": source_hash,
        "last_modified": last_modified,
        "git_author": git_author,
        "mutation_count": module_mutation_count,
        "repo_id": rid,
    }
    records.append(module_record)

    # Step 10 — delete old, upsert new
    nest.delete_by_file(rel_path)
    nest.upsert(records)

    # Step 11 — update import graph
    graph.update_file(rel_path, resolved_files)

    return IndexResult(
        file_path=rel_path,
        symbols_found=len(symbols),
        symbols_described=symbols_described,
        skipped=False,
        error=llm_error,
    )


def index_directory(
    directory: Path,
    nest: Nest,
    graph: ImportGraph,
    model: str = "gpt-5.4-mini",
    effort: str = "medium",
    force: bool = False,
) -> list[IndexResult]:
    """Index all .py files in a directory tree, sequentially.

    Mutates graph in place.  Persistence is the caller's responsibility —
    this function does NOT call graph.save().

    Caller pattern:
        graph = ImportGraph.load(nest.nest_path / "imports.json")
        results = index_directory(directory, nest, graph, ...)
        graph.save(nest.nest_path / "imports.json")
    """
    # Step 1 — build the full repo file set (single source of truth)
    repo_files = collect_repo_files(nest.repo_root)

    # Step 2 — walk directory for *.py files
    directory = directory.resolve()
    py_files: list[Path] = []
    for py_file in directory.rglob("*.py"):
        rel_parts = py_file.relative_to(directory).parts
        if any(p in _EXCLUDE_DIRS for p in rel_parts[:-1]):
            continue
        if len(rel_parts) >= 2 and rel_parts[0] == ".claude" and rel_parts[1] == ".venv":
            continue
        py_files.append(py_file)

    py_files.sort()

    # Step 3 — index each file sequentially
    results: list[IndexResult] = []
    for py_file in py_files:
        try:
            result = index_file(
                py_file,
                nest,
                graph,
                repo_files,
                model=model,
                effort=effort,
                force=force,
            )
            results.append(result)
        except Exception as e:
            results.append(IndexResult(
                file_path=str(py_file.relative_to(nest.repo_root)).replace("\\", "/"),
                symbols_found=0,
                symbols_described=0,
                skipped=False,
                error=str(e),
            ))

    # Step 4 — return results; caller persists graph
    return results


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import sys

    def log(msg: str) -> None:
        print(f"   index | {msg}", file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(prog="pidgin index",
                                     description="index — pidgin LanceDB indexer")
    parser.add_argument("--target", required=True, help="Python file or directory to index")
    parser.add_argument("--model", default="gpt-5.4-mini", help="Model for descriptions")
    parser.add_argument("--effort", default="medium", choices=["low", "medium", "high"],
                        help="Reasoning effort")
    parser.add_argument("--force", action="store_true",
                        help="Force re-index even if source_hash matches")
    args = parser.parse_args()

    from pidgin.nest import Nest
    from pidgin.graph import ImportGraph

    target = Path(args.target).resolve()
    if not target.exists():
        log(f"error: {target} not found")
        return 1

    nest = Nest()
    nest.ensure_table()

    graph_path = nest.nest_path / "imports.json"
    graph = ImportGraph.load(graph_path)

    if target.is_file():
        repo_files = collect_repo_files(nest.repo_root)
        results = [index_file(
            target, nest, graph, repo_files,
            model=args.model, effort=args.effort, force=args.force,
        )]
    elif target.is_dir():
        results = index_directory(
            target, nest, graph,
            model=args.model, effort=args.effort, force=args.force,
        )
    else:
        log(f"error: {target} is neither a file nor a directory")
        return 1

    graph.save(graph_path)

    indexed = sum(1 for r in results if not r.skipped and r.error is None)
    skipped = sum(1 for r in results if r.skipped)
    failed = sum(1 for r in results if r.error is not None)
    total_syms = sum(r.symbols_found for r in results)
    total_described = sum(r.symbols_described for r in results)

    log(f"files | {indexed} indexed, {skipped} skipped, {failed} failed")
    log(f"symbols | {total_described}/{total_syms} described")
    log(f"graph | {graph.edge_count} edges across {len(graph.files)} files")

    for r in results:
        if r.error is not None:
            log(f"FAILED {r.file_path}: {r.error}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
