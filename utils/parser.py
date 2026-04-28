#!/usr/bin/env python3
# pidgin v0.2 — moved from tools/utils/parser.py (v0.1).
# Provenance: tools/utils/parser.py — full move; all public functions preserved
#   unchanged. No behaviour change; only the module path changes.

# MODULE: parser
# DOES: Detect source language by extension and extract function/class records via AST or regex.
# EMITS: FunctionRecord lists, import graphs
# READS: source file text
# IMPLEMENTS: Python AST parsing; regex fallback for Rust, TypeScript, JavaScript, Go
# DEPENDS: ast, re, pathlib

import ast
import fnmatch
import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from pidgin.utils.git import find_project_root


# ---------------------------------------------------------------------------
# Filter-layer constants (M5)
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".py"}    # v0.3; v0.4 may add .rs/.ts/.go
SKIP_DIRS = {
    ".pidgin", ".git", "__pycache__", "node_modules",
    ".venv", "venv", ".tox", "build", "dist",
    ".mypy_cache", ".pytest_cache",
}


# ---------------------------------------------------------------------------
# Source-file walker (M5)
# ---------------------------------------------------------------------------

def walk_source_files(
    root: str,
    *,
    exclude_globs: "list[str] | None" = None,
) -> "Iterator[Path]":
    """Yield Path objects for every file under root that:
      - has an extension in SUPPORTED_EXTENSIONS,
      - is not inside a directory whose basename is in SKIP_DIRS,
      - is not under a child .git boundary (any directory containing
        .git that is NOT root itself),
      - does not match any of the exclude_globs (glob matched against
        the path relative to root).

    CF4: If root is a single file (not a directory), os.walk yields nothing.
    Guard added: when root is a file, yield it directly if it passes the
    extension and exclude_globs filters.
    """
    root_p = Path(root).resolve()
    exclude_globs = exclude_globs or []

    # CF4: single-file guard — os.walk on a file yields nothing.
    if root_p.is_file():
        if root_p.suffix in SUPPORTED_EXTENSIONS:
            rel = root_p.name
            if not any(fnmatch.fnmatch(rel, g) for g in exclude_globs):
                yield root_p
        return

    for dirpath, dirnames, filenames in os.walk(root_p):
        dp = Path(dirpath).resolve()
        # Prune skip-dir children.
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS
            and not (
                dp != root_p and (Path(dirpath, d) / ".git").exists()
            )
        ]
        # Detect child-git at the dirpath itself.
        if dp != root_p and (dp / ".git").exists():
            dirnames[:] = []
            continue
        for fn in filenames:
            p = Path(dirpath, fn)
            if p.suffix not in SUPPORTED_EXTENSIONS:
                continue
            rel = str(p.relative_to(root_p))
            if any(fnmatch.fnmatch(rel, g) for g in exclude_globs):
                continue
            yield p


def file_type_breakdown(
    root: str,
    *,
    exclude_globs: "list[str] | None" = None,
) -> "dict[str, int]":
    """Return {extension: count} for files that pass the filter, plus
    {'__skipped_dirs': N} as a sentinel summary."""
    counts: dict = {}
    skipped_dirs = 0

    root_p = Path(root).resolve()
    exclude_globs_list = exclude_globs or []

    for dirpath, dirnames, filenames in os.walk(root_p):
        dp = Path(dirpath).resolve()
        # Count and prune skip-dir children.
        pruned: list[str] = []
        for d in dirnames:
            child_dp = Path(dirpath, d)
            if d in SKIP_DIRS or (dp != root_p and (child_dp / ".git").exists()):
                skipped_dirs += 1
            else:
                pruned.append(d)
        dirnames[:] = pruned

        # Detect child-git at the dirpath itself.
        if dp != root_p and (dp / ".git").exists():
            dirnames[:] = []
            continue

        for fn in filenames:
            p = Path(dirpath, fn)
            if p.suffix not in SUPPORTED_EXTENSIONS:
                continue
            rel = str(p.relative_to(root_p))
            if any(fnmatch.fnmatch(rel, g) for g in exclude_globs_list):
                continue
            counts[p.suffix] = counts.get(p.suffix, 0) + 1

    counts["__skipped_dirs"] = skipped_dirs
    return counts



@dataclass
class FunctionRecord:
    """Hold extracted function name, signature, body, line range, module path, visibility, and language."""
    name: str
    signature: str
    body: str
    line_range: tuple
    module: str
    visibility: str
    language: str



_EXT_MAP = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
}


def detect_language(path) -> str:
    """Return language name from file extension or raise ValueError on unknown extension."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in _EXT_MAP:
        raise ValueError(f"Unknown language for extension {ext!r} (path: {path})")
    return _EXT_MAP[ext]



def parse_python(source: str, module_path: str) -> list[FunctionRecord]:
    """Extract top-level function and class records from Python source via AST.

    Two-pass extraction: module-level functions/classes first, then public
    methods within each class body.  Class methods are qualified as
    ClassName.method_name so identities are unique across classes.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    records: list[FunctionRecord] = []

    for node in ast.iter_child_nodes(tree):
        # Module-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rec = _python_record(node, lines, module_path, class_name=None)
            if rec is not None:
                records.append(rec)
        # Classes: record the class itself, then extract public methods
        elif isinstance(node, ast.ClassDef):
            class_rec = _python_record(node, lines, module_path, class_name=None)
            if class_rec is not None:
                records.append(class_rec)
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_rec = _python_record(
                        child, lines, module_path,
                        class_name=node.name,
                    )
                    if method_rec is not None:
                        records.append(method_rec)

    return records


def _init_has_meaningful_logic(node) -> bool:
    """Return True if __init__ body contains logic beyond self.x = x assignments.

    Checks for: function calls (not super().__init__()), control flow
    (if/for/while/try/with), list comprehensions, or any statement that is
    not a simple assignment.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            return True
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Call):
            # Allow super().__init__() but flag other calls
            func = child.value.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
                continue  # super().__init__()
            return True
    return False


def _python_record(
    node,
    lines: list[str],
    module_path: str,
    class_name: "str | None" = None,
) -> "FunctionRecord | None":
    """Return FunctionRecord from ast node if it is def, async def, or class.

    When class_name is provided the node is a class method: the record name
    is qualified as ClassName.method_name.  Private and dunder methods are
    excluded, with the sole exception of __init__ when it contains meaningful
    logic beyond simple attribute assignments.
    """
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return None

    name = node.name

    if class_name is not None:
        # Skip private methods (leading _) except __init__
        if name.startswith("_") and name != "__init__":
            return None
        # Skip __dunder__ methods except __init__
        if name.startswith("__") and name.endswith("__") and name != "__init__":
            return None
        # __init__: only keep if body has meaningful logic beyond assignment
        if name == "__init__":
            if not _init_has_meaningful_logic(node):
                return None
        name = f"{class_name}.{name}"
    else:
        # Module-level: skip private names except __init__
        if name.startswith("_") and name != "__init__":
            return None

    start = node.lineno
    end = getattr(node, "end_lineno", start) or start

    # Extract signature from first line of node.
    signature = lines[start - 1] if 0 <= start - 1 < len(lines) else ""
    # Extract body lines after signature.
    body_lines = lines[start:end] if end > start else []
    body = "\n".join(body_lines)

    visibility = "public"

    return FunctionRecord(
        name=name,
        signature=signature,
        body=body,
        line_range=(start, end),
        module=module_path,
        visibility=visibility,
        language="python",
    )



def _collect_braced_body(lines: list[str], start_idx: int) -> tuple[str, int]:
    """Walk forward from start_idx until braces balance, returning (body, end_idx)."""
    depth = 0
    started = False
    # Find first opening brace at or after start_idx.
    i = start_idx
    while i < len(lines) and i < start_idx + 3 and "{" not in lines[i]:
        i += 1
    if i >= len(lines) or "{" not in lines[i]:
        # No body found; return signature line only.
        return lines[start_idx], start_idx

    for j in range(i, len(lines)):
        line = lines[j]
        # Count braces to track nesting depth.
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
        if started and depth <= 0:
            return "\n".join(lines[start_idx : j + 1]), j
    # Unbalanced braces; return from start to EOF.
    return "\n".join(lines[start_idx:]), len(lines) - 1



_RUST_ITEM = re.compile(
    r"^\s*(?P<vis>pub(?:\(\w+\))?\s+)?"
    r"(?P<kind>fn|struct|enum|trait)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)


def parse_rust(source: str, module_path: str) -> list[FunctionRecord]:
    """Extract public function records from Rust source via regex."""
    lines = source.splitlines()
    records: list[FunctionRecord] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _RUST_ITEM.match(line)
        if m:
            name = m.group("name")
            visibility = "public" if (m.group("vis") or "").strip().startswith("pub") else "private"
            body, end_idx = _collect_braced_body(lines, i)
            records.append(FunctionRecord(
                name=name,
                signature=line,
                body=body,
                line_range=(i + 1, end_idx + 1),
                module=module_path,
                visibility=visibility,
                language="rust",
            ))
            i = end_idx + 1
            continue
        i += 1
    return records



_TS_ITEM = re.compile(
    r"^(?P<export>export\s+(?:default\s+)?)"
    r"(?P<kind>function|class|const|interface|type)\s+"
    r"(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)"
)


def _parse_ts_like(source: str, module_path: str, language: str,
                   skip_kinds: set) -> list[FunctionRecord]:
    """Parse TypeScript-like source (TypeScript or JavaScript) and extract exported items."""
    lines = source.splitlines()
    records: list[FunctionRecord] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _TS_ITEM.match(line)
        if m:
            kind = m.group("kind")
            if kind in skip_kinds:
                i += 1
                continue
            name = m.group("name")
            visibility = "public"
            # Collect braced body for function, class, and interface.
            if kind in ("function", "class", "interface"):
                body, end_idx = _collect_braced_body(lines, i)
            elif kind in ("const", "let", "var"):
                # Collect braced body if const has object or arrow function.
                if "{" in line or (i + 1 < len(lines) and "{" in lines[i + 1]):
                    body, end_idx = _collect_braced_body(lines, i)
                else:
                    body = line
                    end_idx = i
            else:
                body = line
                end_idx = i
            records.append(FunctionRecord(
                name=name,
                signature=line,
                body=body,
                line_range=(i + 1, end_idx + 1),
                module=module_path,
                visibility=visibility,
                language=language,
            ))
            i = end_idx + 1
            continue
        i += 1
    return records


def parse_typescript(source: str, module_path: str) -> list[FunctionRecord]:
    """Extract function and class records from TypeScript source via regex."""
    return _parse_ts_like(source, module_path, "typescript", skip_kinds=set())


def parse_javascript(source: str, module_path: str) -> list[FunctionRecord]:
    """Extract function and class records from JavaScript source via regex."""
    return _parse_ts_like(source, module_path, "javascript",
                          skip_kinds={"interface", "type"})



_GO_FUNC = re.compile(
    r"^\s*func\s+(?:\(\s*[^)]*\)\s+)?(?P<name>[A-Z][A-Za-z0-9_]*)"
)
_GO_TYPE = re.compile(
    r"^\s*type\s+(?P<name>[A-Z][A-Za-z0-9_]*)\s+"
)


def parse_go(source: str, module_path: str) -> list[FunctionRecord]:
    """Extract exported function records from Go source via regex."""
    lines = source.splitlines()
    records: list[FunctionRecord] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _GO_FUNC.match(line) or _GO_TYPE.match(line)
        if m:
            name = m.group("name")
            visibility = "public"
            # Collect braced body if type has struct definition.
            if "{" in line or (i + 1 < len(lines) and "{" in lines[i + 1]):
                body, end_idx = _collect_braced_body(lines, i)
            else:
                body = line
                end_idx = i
            records.append(FunctionRecord(
                name=name,
                signature=line,
                body=body,
                line_range=(i + 1, end_idx + 1),
                module=module_path,
                visibility=visibility,
                language="go",
            ))
            i = end_idx + 1
            continue
        i += 1
    return records



_TS_IMPORT = re.compile(r"""import\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]""")
_RUST_USE = re.compile(r"^\s*use\s+([^\s;]+)\s*;", re.MULTILINE)
_GO_IMPORT_SINGLE = re.compile(r'^\s*import\s+"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK = re.compile(r'import\s*\(([^)]*)\)', re.DOTALL)
_GO_IMPORT_BLOCK_ITEM = re.compile(r'"([^"]+)"')


def extract_imports(source: str, language: str) -> list[str]:
    """Return import paths from source text for the given language."""
    if language == "python":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    if language in ("typescript", "javascript"):
        return _TS_IMPORT.findall(source)

    if language == "rust":
        return [m.group(1) for m in _RUST_USE.finditer(source)]

    if language == "go":
        imports = list(_GO_IMPORT_SINGLE.findall(source))
        for block in _GO_IMPORT_BLOCK.findall(source):
            imports.extend(_GO_IMPORT_BLOCK_ITEM.findall(block))
        return imports

    return []



def build_import_graph(source_files: list, project_root) -> dict:
    """Build a dependency map from source file paths to their resolved imports."""
    project_root = Path(project_root).resolve()

    # Index files by absolute path and lookup keys.
    file_paths: list[Path] = [Path(f).resolve() for f in source_files]
    path_set = set(file_paths)

    # Build lookup tables by stem and dotted module path.
    by_stem: dict[str, list[Path]] = {}
    by_dotted: dict[str, Path] = {}
    for p in file_paths:
        by_stem.setdefault(p.stem, []).append(p)
        try:
            rel = p.relative_to(project_root).with_suffix("")
            dotted = ".".join(rel.parts)
            by_dotted[dotted] = p
        except ValueError:
            continue

    graph: dict = {}

    for p in file_paths:
        try:
            rel_key = str(p.relative_to(project_root))
        except ValueError:
            rel_key = str(p)

        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            graph[rel_key] = set()
            continue

        try:
            language = detect_language(p)
        except ValueError:
            graph[rel_key] = set()
            continue

        imports = extract_imports(src, language)
        edges: set = set()

        for imp in imports:
            target = _resolve_import(imp, p, project_root, by_stem, by_dotted, path_set, language)
            if target is not None:
                try:
                    edges.add(str(target.relative_to(project_root)))
                except ValueError:
                    edges.add(str(target))

        graph[rel_key] = edges

    return graph


def _resolve_import(imp: str, importing_file: Path, project_root: Path,
                    by_stem: dict, by_dotted: dict, path_set: set,
                    language: str):
    """Resolve an import string to a concrete file in the project, or None."""
    if not imp:
        return None

    # Try exact dotted path match for Python imports.
    if language == "python":
        if imp in by_dotted:
            return by_dotted[imp]
        # Try progressively shorter dotted prefixes.
        parts = imp.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in by_dotted:
                return by_dotted[candidate]
        # Fallback to last segment as filename stem.
        stem = parts[-1]
        if stem in by_stem and len(by_stem[stem]) == 1:
            return by_stem[stem][0]
        return None

    # Resolve relative imports for TypeScript and JavaScript.
    if language in ("typescript", "javascript"):
        if imp.startswith("."):
            base = importing_file.parent / imp
            for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
                cand = base.with_suffix(suffix)
                if cand in path_set:
                    return cand
            # Check for directory index files.
            for name in ("index.ts", "index.tsx", "index.js", "index.jsx"):
                cand = base / name
                if cand in path_set:
                    return cand
            return None
        # Try bare stem match for non-relative imports.
        stem = imp.split("/")[-1]
        if stem in by_stem and len(by_stem[stem]) == 1:
            return by_stem[stem][0]
        return None

    # Match last path segment for Rust and Go imports.
    if language in ("rust", "go"):
        segments = re.split(r"[:/]+", imp)
        stem = segments[-1] if segments else imp
        if stem in by_stem and len(by_stem[stem]) == 1:
            return by_stem[stem][0]
        return None

    return None


# ---------------------------------------------------------------------------
# High-level walker — extract public functions from a directory or file
# ---------------------------------------------------------------------------

_PARSERS = {
    "python": parse_python,
    "rust": parse_rust,
    "typescript": parse_typescript,
    "javascript": parse_javascript,
    "go": parse_go,
}


def extract_public_functions(path) -> list[dict]:
    """Walk a path (file or directory) and return public function dicts.

    Each dict has keys: name, file, body, line_start, line_end, module,
    visibility, language, signature.

    Only files with recognised extensions are parsed. Unknown extensions are
    silently skipped. Private functions (visibility != 'public') are excluded.
    The returned dicts are compatible with run_embedding_mld_pipeline_for_functions.
    """
    root = Path(path).resolve()

    # Collect candidate files.
    if root.is_file():
        candidates = [root]
    else:
        candidates = [
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in _EXT_MAP
        ]

    # Compute repo root once for stable relative module_path values.
    # find_project_root walks up from root (or its parent for single files)
    # to find the nearest .git boundary.  Falls back gracefully when no git
    # repo exists.
    _start_dir = str(root.parent if root.is_file() else root)
    repo_root = find_project_root(_start_dir)
    if repo_root:
        repo_root_p = Path(repo_root)
    else:
        repo_root_p = root.parent if root.is_file() else root

    results: list[dict] = []
    for file_path in sorted(candidates):
        try:
            lang = detect_language(file_path)
        except ValueError:
            continue

        parser_fn = _PARSERS.get(lang)
        if parser_fn is None:
            continue

        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            module_path = str(file_path.relative_to(repo_root_p))
        except ValueError:
            module_path = str(file_path)

        records: list[FunctionRecord] = parser_fn(source, module_path)
        for rec in records:
            if rec.visibility != "public":
                continue
            line_start, line_end = rec.line_range
            results.append({
                "name": rec.name,
                "file": str(file_path),
                "body": rec.body,
                "line_start": line_start,
                "line_end": line_end,
                "module": rec.module,
                "visibility": rec.visibility,
                "language": rec.language,
                "signature": rec.signature,
            })

    return results


# ---------------------------------------------------------------------------
# Full AST metadata extraction (M12)
# ---------------------------------------------------------------------------

@dataclass
class ParameterMeta:
    """Metadata for a single function parameter."""
    name: str
    annotation: "str | None"
    default: "str | None"        # repr of default literal, or None
    kind: str                    # "positional" | "keyword" | "vararg" | "kwarg"


@dataclass
class FunctionSignature:
    """Full signature metadata extracted from a function or async function node."""
    name: str
    parameters: "list[ParameterMeta]"
    return_annotation: "str | None"
    decorators: "list[str]"
    line: int
    is_async: bool


@dataclass
class ImportMeta:
    """Metadata for a single import statement."""
    kind: str                    # "import" | "from"
    module: str
    names: "list[str]"
    line: int


@dataclass
class FileMeta:
    """All extracted metadata for one source file."""
    path: str                    # relative to repo root
    imports: "list[ImportMeta]"
    functions: "list[FunctionSignature]"


def _annotation_str(node) -> "str | None":
    """Return the unparsed string form of an AST annotation node, or None."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def extract_file_meta(repo_root: str, file_abs_path: str) -> FileMeta:
    """Extract imports and function signatures from a Python source file.

    Walks the AST of file_abs_path and produces:
      - ImportMeta for every import/from-import statement.
      - FunctionSignature for every function/async function definition
        (including nested ones).

    path in the returned FileMeta is relative to repo_root.
    """
    text = open(file_abs_path).read()
    tree = ast.parse(text)
    rel = str(Path(file_abs_path).relative_to(repo_root))
    imports: list[ImportMeta] = []
    functions: list[FunctionSignature] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportMeta("import", alias.name, [], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            imports.append(ImportMeta(
                "from", node.module or "",
                [a.name for a in node.names], node.lineno))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params: list[ParameterMeta] = []
            args = node.args
            for a in args.args:
                params.append(ParameterMeta(
                    a.arg, _annotation_str(a.annotation), None, "positional"))
            if args.vararg:
                params.append(ParameterMeta(
                    args.vararg.arg, _annotation_str(args.vararg.annotation),
                    None, "vararg"))
            for a in args.kwonlyargs:
                params.append(ParameterMeta(
                    a.arg, _annotation_str(a.annotation), None, "keyword"))
            if args.kwarg:
                params.append(ParameterMeta(
                    args.kwarg.arg, _annotation_str(args.kwarg.annotation),
                    None, "kwarg"))
            # Defaults: zip from the right against positional params.
            defaults = list(args.defaults)
            for p, d in zip(reversed(params[:len(args.args)]), reversed(defaults)):
                p.default = _annotation_str(d) or "?"
            # kw_defaults parallel to kwonlyargs (None means no default).
            for a, d in zip(args.kwonlyargs, args.kw_defaults):
                if d is not None:
                    for pp in params:
                        if pp.name == a.arg:
                            pp.default = _annotation_str(d) or "?"
                            break
            functions.append(FunctionSignature(
                name=node.name,
                parameters=params,
                return_annotation=_annotation_str(node.returns),
                decorators=[_annotation_str(d) or "" for d in node.decorator_list],
                line=node.lineno,
                is_async=isinstance(node, ast.AsyncFunctionDef),
            ))

    return FileMeta(path=rel, imports=imports, functions=functions)


# ---------------------------------------------------------------------------
# Source-hash helpers (M13 — index idempotency)
# ---------------------------------------------------------------------------
#
# Hash domain: signature + body. Per M13 spec, ast.unparse on the AST node
# folds out line numbers and column offsets so that the same logical function
# hashes identically across whitespace and indentation differences. Comments
# and docstrings ARE included — a docstring change re-MLDs.
#
# Two surface helpers are exposed:
#
#   function_source_hash(node)   — when the caller has an AST node. Uses
#                                  ast.unparse for byte-stable normalisation.
#   function_dict_hash(fn_dict)  — when the caller has the dict shape produced
#                                  by extract_public_functions (signature/body
#                                  pair). The pipeline operates on dicts, so
#                                  this is the helper index.py uses.
#
# Both produce a 64-char sha256 hex digest. Different inputs => different
# digests; identical inputs => identical digests across processes.
#
# CF10: function_dict_hash and function_source_hash are NOT interchangeable.
# function_dict_hash uses raw-text rstrip normalisation (not AST unparse), so
# pure-whitespace edits that are NOT trailing (e.g. aligned spaces inside a
# function body) will produce a different hash and trigger unnecessary re-MLD.
# function_source_hash uses ast.unparse which folds all such whitespace.
# AST-based deduplication for the dict path is deferred to v0.4.

def _normalise_function_source(node) -> str:
    """Stable string form of a Python function AST node, suitable for hashing.

    Round-trips the node through ast.unparse, which renders the tree without
    line numbers or column offsets. Two functions whose source differs only
    in whitespace, indentation, or trailing-newline placement produce the
    same string. Comments and docstrings ARE preserved (a docstring change
    will re-MLD on the next index pass).
    """
    return ast.unparse(node)


def function_source_hash(node) -> str:
    """Return sha256 hex digest of the normalised AST source for `node`.

    `node` must be a Python AST FunctionDef / AsyncFunctionDef. For non-AST
    callers (e.g. the index pipeline, which carries dicts), use
    function_dict_hash.
    """
    return hashlib.sha256(
        _normalise_function_source(node).encode("utf-8")
    ).hexdigest()


def function_dict_hash(fn: dict) -> str:
    """Return sha256 hex digest of the normalised text for a function dict.

    `fn` is the dict shape produced by extract_public_functions: keys
    'signature' and 'body'. Hash domain is signature + body (signature-only
    changes such as annotation updates re-MLD, per the M13 spec). The body
    is rstripped per-line to fold out trailing-whitespace noise so that
    cosmetic edits do not invalidate the hash.
    """
    sig = (fn.get("signature") or "").rstrip()
    body = "\n".join(line.rstrip() for line in (fn.get("body") or "").splitlines())
    payload = f"{sig}\n{body}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_imports_json(repo_root: str, files: "list[FileMeta]") -> str:
    """Serialise a list of FileMeta objects to .pidgin/imports.json.

    Produces a canonical JSON file with three top-level keys:
      version   — schema version integer (1).
      files     — mapping of rel_path → {imports, functions} as dicts.
      imported_by — inverted index: module_name → [rel_path, ...].

    Returns the absolute path to the written file.
    """
    from collections import defaultdict
    inverted: dict = defaultdict(list)
    out_files: dict = {}
    for fm in files:
        out_files[fm.path] = {
            "imports": [asdict(i) for i in fm.imports],
            "functions": [asdict(f) for f in fm.functions],
        }
        for imp in fm.imports:
            inverted[imp.module].append(fm.path)
    payload = {
        "version": 1,
        "files": out_files,
        "imported_by": dict(inverted),
    }
    out_path = Path(repo_root) / ".pidgin" / "imports.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return str(out_path)
