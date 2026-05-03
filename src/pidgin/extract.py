"""AST-based symbol and import extraction for Python source.

Provides:
  - Symbol dataclass
  - extract_symbols(source) -> list[Symbol]
  - extract_symbol_by_name(source, name) -> Symbol | None
  - extract_imports(source, file_path=None) -> list[str]   (module names)
  - scan_package_roots(repo_files) -> dict[str, str]
  - resolve_import_to_file(module_name, repo_root, repo_files, package_roots=None) -> str | None
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


# --------------------------------------------------------------------------- #
# Symbol model                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Symbol:
    name: str           # "function_name" or "ClassName.method_name"
    kind: str           # "function" | "class" | "method"
    signature: str      # "def foo(x: int) -> str:" or "class Foo(Base):"
    source: str         # extracted source text (decorators included)
    start_line: int     # 1-based, includes decorators
    end_line: int       # 1-based, inclusive
    parent: str | None  # enclosing class name for methods, else None


# --------------------------------------------------------------------------- #
# Symbol extraction                                                           #
# --------------------------------------------------------------------------- #

_FunctionLike = (ast.FunctionDef, ast.AsyncFunctionDef)


def _decorator_start_line(node: ast.AST) -> int:
    """Earliest line owned by a node, accounting for decorators.

    ast nodes report `lineno` of the def/class keyword. Decorator
    lines precede that, so we take the min of all decorator linenos.
    """
    base = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", []) or []
    if not decorators:
        return base
    return min([base] + [d.lineno for d in decorators])


def _node_end_line(node: ast.AST) -> int:
    """Inclusive end line for a node, falling back to start if absent."""
    end = getattr(node, "end_lineno", None)
    if end is not None:
        return end
    return getattr(node, "lineno", 1)


def _slice_source(lines: list[str], start: int, end: int) -> str:
    """Return source text for inclusive 1-based [start, end] line range."""
    # Clamp into the available range.
    s = max(1, start)
    e = min(len(lines), end)
    if s > e:
        return ""
    return "\n".join(lines[s - 1:e])


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render `def name(args) -> Ret:` or `async def ...` from an AST node."""
    args_src = ast.unparse(node.args)
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    if node.returns is not None:
        return f"{prefix} {node.name}({args_src}) -> {ast.unparse(node.returns)}:"
    return f"{prefix} {node.name}({args_src}):"


def _class_signature(node: ast.ClassDef) -> str:
    """Render `class Name(Base, kw=val):` from a ClassDef."""
    parts: list[str] = []
    for base in node.bases:
        parts.append(ast.unparse(base))
    for kw in node.keywords:
        if kw.arg is None:
            parts.append(f"**{ast.unparse(kw.value)}")
        else:
            parts.append(f"{kw.arg}={ast.unparse(kw.value)}")
    if parts:
        return f"class {node.name}({', '.join(parts)}):"
    return f"class {node.name}:"


def extract_symbols(source: str) -> list[Symbol]:
    """Extract all top-level functions, classes, and class methods.

    Methods include any FunctionDef/AsyncFunctionDef directly inside a
    ClassDef body. Nested functions inside other functions are not
    enumerated as separate symbols (they remain part of the outer
    function's source).
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    symbols: list[Symbol] = []

    for node in tree.body:
        if isinstance(node, _FunctionLike):
            start = _decorator_start_line(node)
            end = _node_end_line(node)
            symbols.append(Symbol(
                name=node.name,
                kind="function",
                signature=_function_signature(node),
                source=_slice_source(lines, start, end),
                start_line=start,
                end_line=end,
                parent=None,
            ))
        elif isinstance(node, ast.ClassDef):
            cls_start = _decorator_start_line(node)
            cls_end = _node_end_line(node)
            symbols.append(Symbol(
                name=node.name,
                kind="class",
                signature=_class_signature(node),
                source=_slice_source(lines, cls_start, cls_end),
                start_line=cls_start,
                end_line=cls_end,
                parent=None,
            ))
            for child in node.body:
                if isinstance(child, _FunctionLike):
                    m_start = _decorator_start_line(child)
                    m_end = _node_end_line(child)
                    symbols.append(Symbol(
                        name=f"{node.name}.{child.name}",
                        kind="method",
                        signature=_function_signature(child),
                        source=_slice_source(lines, m_start, m_end),
                        start_line=m_start,
                        end_line=m_end,
                        parent=node.name,
                    ))

    return symbols


def extract_symbol_by_name(source: str, name: str) -> Symbol | None:
    """Return the symbol matching `name`, or None.

    Accepts top-level names ('foo') and dotted method names
    ('ClassName.method_name').
    """
    for sym in extract_symbols(source):
        if sym.name == name:
            return sym
    return None


# --------------------------------------------------------------------------- #
# Import extraction                                                           #
# --------------------------------------------------------------------------- #

def _derive_package(file_path: Path) -> str | None:
    """Derive the dotted package path containing `file_path`.

    Walks upward from `file_path`'s parent collecting directories that
    contain __init__.py. Stops at the first parent directory that does
    NOT contain __init__.py — that boundary is the package root.

    Returns a dotted package name (e.g. 'pidgin') or None if the file
    is not inside a package.
    """
    fp = Path(file_path).resolve()
    parts: list[str] = []
    cur = fp.parent
    while (cur / "__init__.py").exists():
        parts.append(cur.name)
        if cur.parent == cur:
            break
        cur = cur.parent
    if not parts:
        return None
    return ".".join(reversed(parts))


def extract_imports(
    source: str,
    file_path: Path | None = None,
) -> list[str]:
    """Extract module names imported by Python source.

    Shape:
      - 'import foo'             -> 'foo'
      - 'import foo.bar.baz'     -> 'foo.bar.baz'
      - 'from foo import bar'    -> 'foo'
      - 'from foo.bar import x'  -> 'foo.bar'
      - 'from . import foo'      -> '<pkg>.foo'
      - 'from .sub import x'     -> '<pkg>.sub'

    Relative imports require `file_path` to be set; otherwise they
    are skipped. The result is order-preserving and deduplicated.
    """
    tree = ast.parse(source)
    seen: set[str] = set()
    out: list[str] = []

    pkg: str | None = None
    if file_path is not None:
        pkg = _derive_package(file_path)

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            module = node.module  # may be None for 'from . import x'

            if level == 0:
                # Absolute: 'from foo.bar import x' -> 'foo.bar'
                if module:
                    add(module)
                continue

            # Relative — needs a package anchor.
            if pkg is None:
                continue

            pkg_parts = pkg.split(".")
            # `level` walks up: level=1 stays in pkg, level=2 goes one up.
            if level - 1 > len(pkg_parts):
                # Walks past repo root; skip rather than guess.
                continue
            base_parts = pkg_parts[: len(pkg_parts) - (level - 1)]

            if module:
                # 'from .sub import x' -> '<base>.sub'
                # 'from ..pkg.mod import x' -> '<grandparent>.pkg.mod'
                resolved = ".".join(base_parts + module.split("."))
                if resolved:
                    add(resolved)
            else:
                # 'from . import foo, bar' -> '<base>.foo', '<base>.bar'
                for alias in node.names:
                    resolved = ".".join(base_parts + [alias.name])
                    if resolved:
                        add(resolved)

    return out


# --------------------------------------------------------------------------- #
# Package root registry                                                       #
# --------------------------------------------------------------------------- #

_LAYOUT_DIRS = {"src", "lib", "pkg"}


def scan_package_roots(repo_files: set[str]) -> dict[str, str]:
    """Discover Python package roots and return {package_name: repo_relative_prefix}.

    A package root is the deepest __init__.py-bearing directory whose parent
    directory does NOT contain __init__.py. The prefix is the repo-relative
    path to the directory that contains the package root (ending with "/").

    Entries already covered by the fixed prefixes "" and "src/" are omitted.
    On name conflicts the shortest prefix wins; a warning is emitted to stderr.
    """
    init_dirs: set[str] = set()
    for f in repo_files:
        if f.endswith("/__init__.py"):
            init_dirs.add(f[: -len("/__init__.py")])

    registry: dict[str, str] = {}

    for d in sorted(init_dirs):
        slash = d.rfind("/")
        parent = d[:slash] if slash != -1 else ""

        if parent in init_dirs:
            continue

        package_name = d.split("/")[-1]
        prefix = (parent + "/") if parent else ""

        if prefix in ("", "src/"):
            continue

        if package_name in _LAYOUT_DIRS:
            continue

        if package_name in registry:
            existing = registry[package_name]
            if len(prefix) < len(existing):
                print(
                    f"pidgin warning: package root conflict for '{package_name}': "
                    f"'{prefix}' replaces '{existing}'",
                    file=sys.stderr,
                )
                registry[package_name] = prefix
            else:
                print(
                    f"pidgin warning: package root conflict for '{package_name}': "
                    f"keeping '{existing}', ignoring '{prefix}'",
                    file=sys.stderr,
                )
        else:
            registry[package_name] = prefix

    return registry


# --------------------------------------------------------------------------- #
# Module-name -> repo-relative file path                                      #
# --------------------------------------------------------------------------- #

def resolve_import_to_file(
    module_name: str,
    repo_root: Path,
    repo_files: set[str],
    package_roots: dict[str, str] | None = None,
) -> str | None:
    """Map a Python module name to a repo-relative file path.

    Resolution attempts per dotted-component iteration:
      1. 'foo.bar' -> 'foo/bar.py'
      2. 'foo.bar' -> 'foo/bar/__init__.py'
      3. 'foo.bar' -> 'src/foo/bar.py'
      4. 'foo.bar' -> 'src/foo/bar/__init__.py'
      5. registry lookup via package_roots (monorepo layouts)
      6. Drop rightmost dotted component, retry 1-5.

    Only paths that appear in `repo_files` are returned. `repo_root`
    is accepted for API symmetry but is not used in resolution.
    """
    _ = repo_root  # accepted for API symmetry; not used in resolution.
    if not module_name:
        return None

    parts = module_name.split(".")
    while parts:
        as_module = "/".join(parts) + ".py"
        if as_module in repo_files:
            return as_module
        as_package = "/".join(parts) + "/__init__.py"
        if as_package in repo_files:
            return as_package
        as_module_src = "src/" + as_module
        if as_module_src in repo_files:
            return as_module_src
        as_package_src = "src/" + as_package
        if as_package_src in repo_files:
            return as_package_src
        if package_roots:
            top_level = parts[0]
            if top_level in package_roots:
                prefix = package_roots[top_level]
                as_module_reg = prefix + "/".join(parts) + ".py"
                if as_module_reg in repo_files:
                    return as_module_reg
                as_package_reg = prefix + "/".join(parts) + "/__init__.py"
                if as_package_reg in repo_files:
                    return as_package_reg
        parts = parts[:-1]

    return None
