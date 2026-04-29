"""pidgin depends <file>: show the file's import graph.

DP5 (v0.3): minimal inline extractor; M12 replaces with imports.json.
"""

import ast
import json
import sys
from pathlib import Path
from collections import defaultdict

def _extract_minimal_imports(file_path: Path) -> list[dict]:
    """Return a list of {'kind': 'import'|'from', 'module': str,
    'names': [str], 'line': int}."""
    try:
        tree = ast.parse(file_path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []
    out: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append({"kind": "import", "module": alias.name,
                            "names": [], "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            out.append({"kind": "from", "module": module,
                        "names": [a.name for a in node.names],
                        "line": node.lineno})
    return out


def _build_minimal_graph(repo_root: Path) -> dict:
    from pidgin.utils.parser import walk_source_files
    graph = {"by_file": {}, "imported_by": defaultdict(list)}
    for fp in walk_source_files(str(repo_root)):
        rel = str(fp.relative_to(repo_root))
        imps = _extract_minimal_imports(fp)
        graph["by_file"][rel] = imps
        for imp in imps:
            graph["imported_by"][imp["module"]].append(rel)
    graph["imported_by"] = dict(graph["imported_by"])  # for json
    return graph


def _format_human(rel: str, imports: list[dict],
                  imported_by: list[str]) -> str:
    lines = [f"# depends: {rel}", ""]
    lines.append("## Imports")
    if not imports:
        lines.append("_(none)_")
    else:
        for imp in imports:
            if imp["kind"] == "import":
                lines.append(f"- `import {imp['module']}` (line {imp['line']})")
            else:
                names = ", ".join(imp["names"]) or "*"
                lines.append(f"- `from {imp['module']} import {names}` (line {imp['line']})")
    lines.append("")
    lines.append("## Imported by")
    if not imported_by:
        lines.append("_(none in this repo)_")
    else:
        for f in sorted(imported_by):
            lines.append(f"- `{f}`")
    return "\n".join(lines) + "\n"


CANONICAL_IMPORTS_FILENAME = "imports.json"


def _load_canonical_graph(repo_root: Path) -> "dict | None":
    """Load imports.json if present; return None if absent or malformed."""
    candidate = repo_root / ".pidgin" / CANONICAL_IMPORTS_FILENAME
    if not candidate.exists():
        return None
    try:
        data = json.loads(candidate.read_text())
        if data.get("version") == 1 and "files" in data and "imported_by" in data:
            return data
    except Exception:
        pass
    return None


def run_depends(args) -> int:
    from pidgin.utils.git import find_project_root
    root = find_project_root(args.path)
    if root is None:
        print(f"[depends] FATAL: no .git found above {args.path}.",
              file=sys.stderr)
        return 1
    repo_root = Path(root)

    target = Path(args.path).resolve()
    try:
        rel = str(target.relative_to(repo_root))
    except ValueError:
        print(f"[depends] FATAL: {args.path} is outside {repo_root}.",
              file=sys.stderr)
        return 1

    # M12: prefer imports.json (canonical, full AST) over the legacy minimal graph.
    canonical = _load_canonical_graph(repo_root)
    if canonical is not None:
        # imports.json present — use its imported_by index directly.
        file_entry = canonical["files"].get(rel, {})
        imports = file_entry.get("imports", [])
        imported_by = canonical.get("imported_by_file", {}).get(rel, [])
        if not imported_by:
            # Fall back to module-level inverted index when per-file index absent.
            rel_no_ext = rel[:-3] if rel.endswith(".py") else rel
            candidate_module_names = {
                rel_no_ext.replace("/", "."),
                rel_no_ext.split("/")[-1],
            }
            imported_by_set: list[str] = []
            for module, by in canonical["imported_by"].items():
                if module in candidate_module_names or any(
                    module.endswith("." + n) for n in candidate_module_names
                ):
                    imported_by_set.extend(by)
            imported_by = sorted(set(imported_by_set) - {rel})
        else:
            imported_by = sorted(set(imported_by) - {rel})
    else:
        # Fall back to minimal graph (pre-M12 or imports.json not yet written).
        # _save_graph removed in M19: the legacy minimal graph file is no longer
        # written. The canonical imports.json (written by the index verb) is preferred.
        graph = _build_minimal_graph(repo_root)

        imports = graph["by_file"].get(rel, [])

        rel_no_ext = rel[:-3] if rel.endswith(".py") else rel
        candidate_module_names = {
            rel_no_ext.replace("/", "."),
            rel_no_ext.split("/")[-1],
        }
        imported_by_set2: list[str] = []
        for module, by in graph["imported_by"].items():
            if module in candidate_module_names or any(
                module.endswith("." + n) for n in candidate_module_names
            ):
                imported_by_set2.extend(by)
        imported_by = sorted(set(imported_by_set2) - {rel})

    if args.json:
        sys.stdout.write(json.dumps(
            {"file": rel, "imports": imports, "imported_by": imported_by},
            indent=2, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_human(rel, imports, imported_by))
    return 0
