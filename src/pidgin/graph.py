"""Import graph for the pidgin code indexer.

Wraps a rustworkx.PyDiGraph where every node payload is a repo-relative
file path (str, always ending in .py). Module-name strings never appear
in the graph or its serialized form.

Edge direction: A imports B → directed edge A → B.
  ancestors(B) = files that import B (directly or transitively)
  descendants(A) = files A imports (directly or transitively)

Persistence: node-link JSON at a caller-supplied Path.
  {"nodes": ["a.py", ...], "edges": [[src_idx, tgt_idx], ...]}
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import rustworkx


class ImportGraph:
    """In-memory directed import graph backed by rustworkx.PyDiGraph."""

    def __init__(self) -> None:
        """Create an empty PyDiGraph plus the file_path → node_index dict."""
        self._graph: rustworkx.PyDiGraph = rustworkx.PyDiGraph()
        # Maps repo-relative file path -> integer node index in _graph
        self._index: dict[str, int] = {}

    # ---------------------------------------------------------------------- #
    # Internal helpers                                                         #
    # ---------------------------------------------------------------------- #

    def _get_or_add(self, file_path: str) -> int:
        """Return the node index for file_path, adding it if necessary."""
        if file_path not in self._index:
            idx = self._graph.add_node(file_path)
            self._index[file_path] = idx
        return self._index[file_path]

    # ---------------------------------------------------------------------- #
    # Mutation                                                                 #
    # ---------------------------------------------------------------------- #

    def add_file(self, file_path: str, imported_files: list[str]) -> None:
        """Add a file node and edges to imported files.

        All arguments are repo-relative file paths. Target nodes are
        upserted (added if not already present). Duplicate edges are
        silently skipped.
        """
        src = self._get_or_add(file_path)
        for target_path in imported_files:
            tgt = self._get_or_add(target_path)
            # Only add the edge if it does not already exist.
            if not self._graph.has_edge(src, tgt):
                self._graph.add_edge(src, tgt, None)

    def remove_file(self, file_path: str) -> None:
        """Remove a file node and all its edges."""
        if file_path not in self._index:
            return
        idx = self._index.pop(file_path)
        self._graph.remove_node(idx)

    def update_file(self, file_path: str, imported_files: list[str]) -> None:
        """Upsert: remove old outbound edges from file_path, add new ones.

        Preserves the node index for existing nodes. Safe to call
        unconditionally — if file_path or any target is not yet a node
        it is added (FLAW-2 upsert semantics).
        """
        src = self._get_or_add(file_path)

        # Remove all existing outbound edges from src.
        outbound = self._graph.out_edges(src)
        for (u, v, _) in outbound:
            self._graph.remove_edge(u, v)

        # Add new target nodes and edges.
        for target_path in imported_files:
            tgt = self._get_or_add(target_path)
            if not self._graph.has_edge(src, tgt):
                self._graph.add_edge(src, tgt, None)

    # ---------------------------------------------------------------------- #
    # Traversal                                                                #
    # ---------------------------------------------------------------------- #

    def ancestors(self, file_path: str) -> set[str]:
        """Files that import this file (directly or transitively)."""
        if file_path not in self._index:
            return set()
        idx = self._index[file_path]
        ancestor_indices = rustworkx.ancestors(self._graph, idx)
        return {self._graph[i] for i in ancestor_indices}

    def descendants(self, file_path: str) -> set[str]:
        """Files this file imports, transitively."""
        if file_path not in self._index:
            return set()
        idx = self._index[file_path]
        descendant_indices = rustworkx.descendants(self._graph, idx)
        return {self._graph[i] for i in descendant_indices}

    def direct_importers(self, file_path: str) -> set[str]:
        """One-hop importers (predecessors)."""
        if file_path not in self._index:
            return set()
        idx = self._index[file_path]
        return {self._graph[i] for i in self._graph.predecessor_indices(idx)}

    def direct_imports(self, file_path: str) -> set[str]:
        """One-hop imports (successors)."""
        if file_path not in self._index:
            return set()
        idx = self._index[file_path]
        return {self._graph[i] for i in self._graph.successor_indices(idx)}

    def cycles(self) -> list[list[str]]:
        """Strongly connected components with more than one node."""
        sccs = rustworkx.strongly_connected_components(self._graph)
        result: list[list[str]] = []
        for component in sccs:
            if len(component) > 1:
                result.append([self._graph[i] for i in component])
        return result

    def topo_sort(self) -> list[str]:
        """Topological ordering. Raises CyclicError if cycles exist."""
        indices = rustworkx.topological_sort(self._graph)
        return [self._graph[i] for i in indices]

    # ---------------------------------------------------------------------- #
    # Persistence                                                              #
    # ---------------------------------------------------------------------- #

    def save(self, path: Path) -> None:
        """Serialize to node-link JSON, writing atomically via a .tmp file.

        Format: {"nodes": ["path/a.py", ...], "edges": [[i, j], ...]}
        Node indices in edges correspond to positions in the nodes list.
        """
        # Build a stable list from _index so serialized indices are consistent.
        # We'll use the node's position in the sorted list as the JSON index.
        node_list = sorted(self._index.keys())
        path_to_json_idx = {fp: i for i, fp in enumerate(node_list)}

        edges: list[list[int]] = []
        for src_graph_idx, tgt_graph_idx in self._graph.edge_list():
            src_path = self._graph[src_graph_idx]
            tgt_path = self._graph[tgt_graph_idx]
            # Both endpoints must be in our index; skip any orphans.
            if src_path in path_to_json_idx and tgt_path in path_to_json_idx:
                edges.append([path_to_json_idx[src_path], path_to_json_idx[tgt_path]])

        data = {"nodes": node_list, "edges": edges}

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "ImportGraph":
        """Deserialize from node-link JSON.

        If path does not exist, returns an empty graph without raising.
        """
        g = cls()
        if not path.exists():
            return g

        data = json.loads(path.read_text(encoding="utf-8"))
        node_list: list[str] = data.get("nodes", [])
        edges: list[list[int]] = data.get("edges", [])

        # Add all nodes first (preserving list order).
        for file_path in node_list:
            g._get_or_add(file_path)

        # Add edges using the JSON-index → graph-index mapping.
        json_idx_to_graph_idx = [g._index[fp] for fp in node_list]
        for src_json, tgt_json in edges:
            src_graph = json_idx_to_graph_idx[src_json]
            tgt_graph = json_idx_to_graph_idx[tgt_json]
            if not g._graph.has_edge(src_graph, tgt_graph):
                g._graph.add_edge(src_graph, tgt_graph, None)

        return g

    # ---------------------------------------------------------------------- #
    # Properties                                                               #
    # ---------------------------------------------------------------------- #

    @property
    def files(self) -> set[str]:
        """All file nodes in the graph."""
        return set(self._index.keys())

    @property
    def edge_count(self) -> int:
        """Number of directed edges in the graph."""
        return self._graph.num_edges()


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def _to_repo_relative(target_arg: str, repo_root: Path) -> str:
    """Normalize target argument to a repo-relative POSIX path."""
    p = Path(target_arg)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def main() -> int:
    import argparse
    import sys

    def log(msg: str) -> None:
        print(f"   graph | {msg}", file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(prog="pidgin graph",
                                     description="graph — pidgin import-graph queries")
    parser.add_argument("--target", required=True, help="File to analyze")
    parser.add_argument("--mode",
                        choices=["blast-radius", "depends", "cycles"],
                        default="blast-radius",
                        help="Query mode (default: blast-radius)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    from pidgin.nest import Nest

    nest = Nest()
    graph_path = nest.nest_path / "imports.json"
    graph = ImportGraph.load(graph_path)

    rel = _to_repo_relative(args.target, nest.repo_root)

    output: dict = {"file": rel}

    if args.mode == "blast-radius":
        output["blast_radius"] = sorted(graph.ancestors(rel))
    elif args.mode == "depends":
        output["depends"] = sorted(graph.descendants(rel))
    elif args.mode == "cycles":
        output["cycles"] = [sorted(c) for c in graph.cycles()]

    if args.json:
        print(json.dumps(output, indent=2))
        return 0

    print(f"file: {rel}")
    if args.mode == "blast-radius":
        anc = output["blast_radius"]
        print(f"\nblast-radius ({len(anc)} ancestors):")
        for a in anc:
            print(f"  {a}")
    elif args.mode == "depends":
        desc = output["depends"]
        print(f"\ndepends ({len(desc)} descendants):")
        for d in desc:
            print(f"  {d}")
    elif args.mode == "cycles":
        cycles = output["cycles"]
        print(f"\ncycles ({len(cycles)}):")
        for i, cyc in enumerate(cycles, 1):
            print(f"  [{i}] {' -> '.join(cyc)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
