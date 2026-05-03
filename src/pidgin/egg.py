"""CLAUDE.md generation from LanceDB-indexed symbols.

Egg reads symbol records from a Nest and writes CLAUDE.md files into
directories.  User-written content is preserved above a sentinel marker.
Pre-existing inline <index> blocks are replaced in place.

Sentinel strategy:
  <!-- pidgin:auto-generated below -->

Four-branch write logic per CLAUDE.md:
  1. File missing            → write sentinel + new block.
  2. Sentinel present        → keep everything above sentinel, replace below.
  3. Inline <index> present  → replace existing block in place (prefixed with
                               sentinel on its own line).
  4. Neither                 → append sentinel + new block to end of file.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from pidgin.nest import Nest


# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #

SENTINEL = "<!-- pidgin:auto-generated below -->"

# Non-greedy DOTALL match for any top-level <index ...>...</index> block.
INDEX_BLOCK_RE = re.compile(r"<index\b[^>]*>.*?</index>", re.DOTALL)

# Match the args section and optional return annotation from a Python signature.
# Handles: def foo(x: int, y: str) -> bool:
#          async def bar(a, b):
#          class Foo(Base):
_SIG_ARGS_RE = re.compile(
    r"^(?:async\s+)?def\s+\w+\((?P<args>[^)]*)\)(?:\s*->\s*(?P<ret>.+?))?\s*:$",
    re.DOTALL,
)


# --------------------------------------------------------------------------- #
# Signature parsing                                                             #
# --------------------------------------------------------------------------- #

def _parse_signature(sig: str) -> tuple[str | None, str | None]:
    """Parse args and return type from a Python def signature string.

    Returns (args_str, returns_str).  Both may be None if parsing fails
    or if the signature is not a def (e.g. a class signature).

    Examples:
        "def foo(x: int, y: str) -> bool:"  -> ("x: int, y: str", "bool")
        "def bar():"                         -> ("", None)
        "class Foo(Base):"                   -> (None, None)
    """
    if not sig:
        return None, None
    m = _SIG_ARGS_RE.match(sig.strip())
    if not m:
        return None, None
    args = m.group("args") or ""
    # Normalise multi-line args (rare but possible from AST unparse).
    args = " ".join(args.split())
    ret = m.group("ret")
    if ret:
        ret = ret.strip()
    return args, ret or None


# --------------------------------------------------------------------------- #
# XML formatting                                                               #
# --------------------------------------------------------------------------- #

def format_index_block(records: list[dict], directory: Path) -> str:
    """Format LanceDB records into an <index> XML block.

    Groups records by file_path.  For each file:
      <file path="name.py" doc="module description">
        <fn name="..." args="..." returns="..." />
        <cls name="...">
          <method name="..." args="..." returns="..." />
        </cls>
      </file>

    Matches the existing wiregrass .claude/tools/CLAUDE.md format exactly.
    The block is returned without a trailing newline.
    """
    # Group records by file_path, preserving insertion order.
    files: dict[str, list[dict]] = {}
    for rec in records:
        fp = rec.get("file_path", "")
        files.setdefault(fp, []).append(rec)

    lines: list[str] = ["<index>"]

    for file_path, file_records in files.items():
        # Derive a filename relative to directory for the path= attribute.
        try:
            rel = Path(file_path).relative_to(directory)
        except ValueError:
            # file_path may already be relative (LanceDB stores repo-relative).
            # If directory can't be subtracted, use just the filename portion
            # that follows the last directory component matching directory.name.
            rel = Path(file_path)

        # Module record carries the file-level doc attribute.
        module_rec = next(
            (r for r in file_records if r.get("kind") == "module"), None
        )
        doc = (module_rec or {}).get("description") or ""

        # Separate symbols by kind.
        functions = [r for r in file_records if r.get("kind") == "function"]
        classes = [r for r in file_records if r.get("kind") == "class"]
        methods = [r for r in file_records if r.get("kind") == "method"]

        # Build a class -> methods mapping.
        class_methods: dict[str, list[dict]] = {}
        for m in methods:
            # sym.name for methods is "ClassName.method_name"; extract class.
            sym_name = m.get("id", "").rsplit("::", 1)[-1]
            if "." in sym_name:
                cls_name = sym_name.split(".")[0]
            else:
                # Fallback: skip orphaned methods.
                cls_name = "__unknown__"
            class_methods.setdefault(cls_name, []).append(m)

        # File opening tag.
        if doc:
            doc_escaped = doc.replace('"', "&quot;")
            lines.append(f'  <file path="{rel}" doc="{doc_escaped}">')
        else:
            lines.append(f'  <file path="{rel}">')

        # Top-level functions.
        for fn_rec in functions:
            fn_id = fn_rec.get("id", "")
            fn_name = fn_id.rsplit("::", 1)[-1]
            sig = fn_rec.get("signature", "")
            args, ret = _parse_signature(sig)
            attrs = f'name="{fn_name}"'
            if args is not None:
                attrs += f' args="{args}"'
            if ret is not None:
                attrs += f' returns="{ret}"'
            lines.append(f"    <fn {attrs} />")

        # Classes (with nested methods).
        for cls_rec in classes:
            cls_id = cls_rec.get("id", "")
            cls_name = cls_id.rsplit("::", 1)[-1]
            cls_methods_list = class_methods.get(cls_name, [])
            if cls_methods_list:
                lines.append(f'    <cls name="{cls_name}">')
                for meth_rec in cls_methods_list:
                    meth_id = meth_rec.get("id", "")
                    meth_full = meth_id.rsplit("::", 1)[-1]
                    meth_name = meth_full.split(".")[-1] if "." in meth_full else meth_full
                    sig = meth_rec.get("signature", "")
                    args, ret = _parse_signature(sig)
                    attrs = f'name="{meth_name}"'
                    if args is not None:
                        attrs += f' args="{args}"'
                    if ret is not None:
                        attrs += f' returns="{ret}"'
                    lines.append(f"      <method {attrs} />")
                lines.append("    </cls>")
            else:
                lines.append(f'    <cls name="{cls_name}" />')

        lines.append("  </file>")

    lines.append("</index>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLAUDE.md write logic                                                         #
# --------------------------------------------------------------------------- #

def _write_claude_md(claude_md: Path, new_block: str) -> None:
    """Apply the four-branch write strategy for one CLAUDE.md file.

    Branch 1 — file missing:
        Write SENTINEL + newline + new_block.
    Branch 2 — file contains SENTINEL:
        Keep everything up to and including SENTINEL, replace below.
    Branch 3 — file contains a top-level <index> block (no sentinel):
        Replace the existing block in place, prefixed with SENTINEL.
        If multiple <index> blocks exist, only the first is replaced;
        a warning is written to stderr.
    Branch 4 — neither sentinel nor <index> block:
        Append newline + SENTINEL + newline + new_block.
    """
    if not claude_md.exists():
        # Branch 1.
        claude_md.write_text(SENTINEL + "\n" + new_block, encoding="utf-8")
        return

    existing = claude_md.read_text(encoding="utf-8")

    if SENTINEL in existing:
        # Branch 2 — keep everything above the sentinel (inclusive).
        sentinel_pos = existing.index(SENTINEL)
        above = existing[: sentinel_pos + len(SENTINEL)]
        claude_md.write_text(above + "\n" + new_block, encoding="utf-8")
        return

    matches = list(INDEX_BLOCK_RE.finditer(existing))
    if matches:
        # Branch 3 — replace first <index> block in place.
        if len(matches) > 1:
            print(
                f"warning: {claude_md} contains {len(matches)} <index> blocks; "
                "only the first will be replaced.",
                file=sys.stderr,
            )
        m = matches[0]
        replacement = SENTINEL + "\n" + new_block
        updated = existing[: m.start()] + replacement + existing[m.end() :]
        claude_md.write_text(updated, encoding="utf-8")
        return

    # Branch 4 — append.
    tail = "\n" + SENTINEL + "\n" + new_block
    claude_md.write_text(existing + tail, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #

def egg(
    directory: Path,
    nest: Nest,
    recursive: bool = True,
) -> list[Path]:
    """Generate CLAUDE.md files from indexed LanceDB data.

    1. Query nest for all records whose file_path starts with `directory`
       (relative to repo root).  Nest.get_by_directory() handles the
       trailing '/' normalisation (FLAW-6).
    2. Group records by their immediate parent directory (relative to
       repo root).
    3. For each parent directory with at least one record:
       a. Build the new <index> block via format_index_block().
       b. Resolve the existing CLAUDE.md and apply the four-branch
          write strategy.
       c. Write atomically via Path.write_text().
    4. In non-recursive mode, only the top-level directory itself is
       written (records are still filtered to immediate children only).
    5. Return the list of CLAUDE.md paths written.

    Args:
        directory: Absolute or relative path to the target directory.
        nest: Open Nest instance (repo root is used for relative path
              computation).
        recursive: If True, write CLAUDE.md files for every subdirectory
                   that has indexed records.  If False, only write for
                   `directory` itself.

    Returns:
        List of Path objects pointing to the CLAUDE.md files that were
        written (one per unique parent directory encountered).
    """
    directory = Path(directory).resolve()
    repo_root = nest.repo_root.resolve()

    # Derive the repo-relative string for the query.
    try:
        dir_rel = directory.relative_to(repo_root).as_posix()
    except ValueError:
        # directory is outside repo root; query whole nest and filter below.
        dir_rel = ""

    records = nest.get_by_directory(dir_rel)

    if not records:
        return []

    # Group records by their immediate parent directory (repo-relative path).
    dir_records: dict[str, list[dict]] = {}
    for rec in records:
        fp = rec.get("file_path", "")
        parent = str(Path(fp).parent.as_posix())
        dir_records.setdefault(parent, []).append(rec)

    written: list[Path] = []

    for parent_rel, parent_recs in dir_records.items():
        parent_abs = repo_root / parent_rel

        # Non-recursive: skip subdirectories.
        if not recursive and parent_abs != directory:
            continue

        new_block = format_index_block(parent_recs, Path(parent_rel))
        claude_md = parent_abs / "CLAUDE.md"
        _write_claude_md(claude_md, new_block)
        written.append(claude_md)

    return written


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import sys

    def log(msg: str) -> None:
        print(f"     egg | {msg}", file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(prog="pidgin egg",
                                     description="egg — pidgin CLAUDE.md generator")
    parser.add_argument("--target", required=True,
                        help="Directory to generate CLAUDE.md for")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Don't recurse into subdirectories")
    args = parser.parse_args()

    from pathlib import Path
    from pidgin.nest import Nest

    target = Path(args.target).resolve()
    if not target.is_dir():
        log(f"error: {target} is not a directory")
        return 1

    nest = Nest()
    nest.ensure_table()

    written = egg(target, nest, recursive=not args.no_recursive)

    if not written:
        log("no records found for target; nothing written")
        return 0

    for path in written:
        log(f"wrote {path}")
    log(f"done | {len(written)} CLAUDE.md files")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
