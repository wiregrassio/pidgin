#!/usr/bin/env python3
# pidgin/store/discovery.py — nested nest discovery and registry. Wired in M13.

# MODULE: store.discovery
# DOES: Walk a root directory up to max_depth, discover child directories that
#       contain .pidgin/nest/, and persist/load a JSON registry of discovered
#       nests. Does NOT register the root itself as a child nest.
# EMITS: NestPointer dataclass instances; registry.json file writes.
# READS: filesystem (os.walk); <root>/.pidgin/registry.json on load.
# IMPLEMENTS: discover_nests, register_nests, load_registry.
# DEPENDS: dataclasses, json, os, datetime, timezone.

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Noise directories — never recurse into these.
# ---------------------------------------------------------------------------

_SKIP_DIRS: frozenset[str] = frozenset(
    [".git", "node_modules", "__pycache__", ".venv", "venv", ".pidgin"]
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NestPointer:
    """Pointer to a child nest discovered under a root directory.

    repo_root:  Absolute path to the child repo root (directory containing .pidgin/).
    nest_path:  Absolute path to the ChromaDB store (.pidgin/nest/).
    namespace:  Short label used for display and registry keys; defaults to
                basename(repo_root). Collision suffix (_2, _3, …) appended when
                two children share the same basename.
    """

    repo_root: str
    nest_path: str
    namespace: str


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_nests(
    root: str,
    *,
    max_depth: int = 4,
    follow_symlinks: bool = False,
) -> list[NestPointer]:
    """Walk root up to max_depth. Return one NestPointer per child dir
    that contains .pidgin/nest/ (but NOT root itself).

    Skip: .git/, node_modules/, __pycache__/, .venv/, venv/, .pidgin/.

    Namespace defaults to basename(repo_root). When two children share the
    same basename, the second gets "_2", the third "_3", and so on.
    """
    root = os.path.abspath(root)
    results: list[NestPointer] = []
    namespace_counts: dict[str, int] = {}

    for dirpath, dirnames, _filenames in os.walk(
        root, topdown=True, followlinks=follow_symlinks
    ):
        # Compute depth relative to root.
        rel = os.path.relpath(dirpath, root)
        if rel == ".":
            depth = 0
        else:
            depth = rel.count(os.sep) + 1

        # Prune noise dirs and dirs that exceed max_depth in place (modifies
        # dirnames to stop os.walk from recursing further).
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and depth < max_depth
        ]

        # Skip the root itself.
        if dirpath == root:
            continue

        # Check whether this directory has a .pidgin/nest/ child.
        nest_dir = os.path.join(dirpath, ".pidgin", "nest")
        if os.path.isdir(nest_dir):
            base = os.path.basename(dirpath)
            count = namespace_counts.get(base, 0) + 1
            namespace_counts[base] = count
            if count == 1:
                namespace = base
            else:
                namespace = f"{base}_{count}"

            results.append(
                NestPointer(
                    repo_root=dirpath,
                    nest_path=nest_dir,
                    namespace=namespace,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Registry persistence
# ---------------------------------------------------------------------------


def register_nests(root: str, nests: list[NestPointer]) -> str:
    """Write JSON registry to <root>/.pidgin/registry.json. Return path.

    JSON schema:
      {
        "version": 1,
        "root": "<abs path to root>",
        "registered_at": "<ISO-8601 UTC>",
        "nests": [{"repo_root": ..., "nest_path": ..., "namespace": ...}, ...]
      }
    """
    root = os.path.abspath(root)
    pidgin_dir = os.path.join(root, ".pidgin")
    os.makedirs(pidgin_dir, exist_ok=True)

    registry_path = os.path.join(pidgin_dir, "registry.json")
    payload = {
        "version": 1,
        "root": root,
        "registered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nests": [asdict(n) for n in nests],
    }

    with open(registry_path, "w") as fh:
        json.dump(payload, fh, indent=2)

    return registry_path


def load_registry(root: str) -> list[NestPointer] | None:
    """Read <root>/.pidgin/registry.json. Return None if not found.

    Returns a list of NestPointer instances reconstructed from the JSON.
    Returns None (not an empty list) when the file does not exist, so callers
    can distinguish "no registry" from "registry with zero entries".
    """
    root = os.path.abspath(root)
    registry_path = os.path.join(root, ".pidgin", "registry.json")

    if not os.path.isfile(registry_path):
        return None

    try:
        with open(registry_path) as fh:
            payload = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    nests = []
    for entry in payload.get("nests", []):
        try:
            nests.append(
                NestPointer(
                    repo_root=entry["repo_root"],
                    nest_path=entry["nest_path"],
                    namespace=entry["namespace"],
                )
            )
        except KeyError:
            continue

    return nests
