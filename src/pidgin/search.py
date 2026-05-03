"""Semantic search over a Nest symbol store.

Embeds the query, searches both description_vector and
signature_vector, merges on record id (keeping the higher
similarity score), and returns ranked SearchResults stripped
of raw vectors and LanceDB internals.
"""
from __future__ import annotations

from dataclasses import dataclass

from pidgin.api import embed_for_store_sync
from pidgin.nest import Nest


@dataclass
class SearchResult:
    id: str
    file_path: str
    kind: str
    name: str              # extracted from id: "path/to/file.py::Name" → "Name"
    description: str | None
    signature: str | None
    similarity: float      # 1 - cosine_distance, in [0, 2]
    match_field: str       # "description" or "signature"


def _to_similarity(distance: float) -> float:
    """Convert LanceDB cosine _distance to similarity.

    LanceDB cosine distance = 1 - cosine_similarity, so:
        similarity = 1 - distance

    Pure function, no side effects.
    """
    return 1.0 - distance


def _extract_name(record_id: str) -> str:
    """Extract the symbol name from a record id.

    "path/to/file.py::ClassName.method_name" → "ClassName.method_name"
    "path/to/file.py::__module__"            → "__module__"
    If no '::' separator is present, return the full id.
    """
    sep = "::"
    idx = record_id.find(sep)
    if idx == -1:
        return record_id
    return record_id[idx + len(sep):]


def _row_to_result(row: dict, match_field: str) -> SearchResult:
    """Build a SearchResult from a raw LanceDB row dict."""
    record_id = row["id"]
    return SearchResult(
        id=record_id,
        file_path=row["file_path"],
        kind=row["kind"],
        name=_extract_name(record_id),
        description=row.get("description"),
        signature=row.get("signature"),
        similarity=_to_similarity(row["_distance"]),
        match_field=match_field,
    )


def search(
    query: str,
    nest: Nest,
    top_k: int = 10,
) -> list[SearchResult]:
    """Semantic search within a repo's nest.

    1. Embed the query with embed_for_store_sync().
    2. Search description_vector and signature_vector independently.
    3. Build SearchResults with similarity = 1 - _distance.
    4. Merge: if a record id appears in both lists, keep the higher
       similarity score (and its match_field).
    5. Sort by similarity descending.
    6. Return the top_k results.

    Raw embedding vectors and LanceDB internals are stripped from
    the returned SearchResults.
    """
    q_vecs = embed_for_store_sync(query)
    q_vec = q_vecs[0]

    desc_rows = nest.search(q_vec, "description_vector", top_k)
    sig_rows = nest.search(q_vec, "signature_vector", top_k)

    # Merge on record id, keeping the higher similarity.
    merged: dict[str, SearchResult] = {}

    for row in desc_rows:
        result = _row_to_result(row, "description")
        merged[result.id] = result

    for row in sig_rows:
        result = _row_to_result(row, "signature")
        existing = merged.get(result.id)
        if existing is None or result.similarity > existing.similarity:
            merged[result.id] = result

    ranked = sorted(merged.values(), key=lambda r: r.similarity, reverse=True)
    return ranked[:top_k]


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import sys

    def log(msg: str) -> None:
        print(f"  search | {msg}", file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(prog="pidgin search",
                                     description="search — pidgin semantic search")
    parser.add_argument("--query", required=True, help="Declarative phrase")
    parser.add_argument("-n", "--top-k", type=int, default=10,
                        help="Number of results (default: 10)")
    parser.add_argument(
        "--min-similarity", type=float, default=0.0,
        help="Filter results below this similarity (default 0.0; "
             "observed range for 256-dim text-embedding-3-small: 0.45–0.55)",
    )
    args = parser.parse_args()

    nest = Nest()
    nest.ensure_table()

    results = search(args.query, nest, top_k=args.top_k)
    if args.min_similarity > 0.0:
        results = [r for r in results if r.similarity >= args.min_similarity]

    if not results:
        log("no results")
        return 0

    for r in results:
        print(f"{r.similarity:6.3f}  {r.kind:8s}  {r.file_path}::{r.name}  ({r.match_field})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
