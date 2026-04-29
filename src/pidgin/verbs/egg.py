# pidgin/verbs/egg.py — egg verb: generate/update CLAUDE.md discovery files.
# Reads indexed function records from the nest; writes CLAUDE.md files to the
# filesystem under <path>. Idempotent: re-running preserves user content above
# the sentinel and replaces everything below it.

# MODULE: verbs.egg
# DOES: Walk the nest for <path>, group records by directory, write/update
#       CLAUDE.md discovery files. Preserves user-edited content above the
#       sentinel comment. Errors if the nest is empty for <path>.
# EMITS: CLAUDE.md files under <path>; stdout summary line.
# READS: per-repo .pidgin/nest/ (via nest_store.iter_records); existing CLAUDE.md files.
# IMPLEMENTS: M9 egg verb (idempotent CLAUDE.md generation from nest data).
# DEPENDS: pathlib, collections, sys; pidgin.store.nest, pidgin.utils.git

import sys
from pathlib import Path
from collections import defaultdict

EGG_SENTINEL = "<!-- egg:auto-generated below this line. Do not edit by hand. -->"


def _group_functions_by_directory(records: list) -> dict[str, list]:
    """Group FunctionRecord objects by their parent directory.

    Returns {dir_abs_path_str: [record, ...]} where each key is the
    string form of the absolute directory containing the record's file.
    """
    groups: dict[str, list] = defaultdict(list)
    for r in records:
        groups[str(Path(r.file_path).parent)].append(r)
    return groups


def _build_auto_section(dir_path: str, records: list) -> str:
    """Produce the markdown body that goes below the sentinel.

    Groups records by file, emits a level-2 heading per file with an
    optional file-level summary paragraph and a symbol table.
    """
    by_file: dict[str, list] = defaultdict(list)
    for r in records:
        by_file[r.file_path].append(r)

    lines = [f"# {Path(dir_path).name}/", ""]
    for fp in sorted(by_file):
        rel = str(Path(fp).relative_to(dir_path))
        lines.append(f"## {rel}")
        # File-level summary if available.
        file_summary = getattr(by_file[fp][0], "file_summary", None)
        if file_summary:
            lines.append("")
            lines.append(file_summary)
        lines.append("")
        lines.append("| Symbol | Kind | DOES |")
        lines.append("|--------|------|------|")
        for r in sorted(by_file[fp], key=lambda r: r.symbol_name):
            kind = getattr(r, "symbol_kind", "function")
            desc = (r.mld_description or "").replace("\n", " ").strip()
            lines.append(f"| `{r.symbol_name}` | {kind} | {desc} |")
        lines.append("")
    return "\n".join(lines)


def _splice_into_existing(existing: str, auto_section: str) -> str:
    """Merge the auto-generated section into an existing CLAUDE.md string.

    Three cases:
    1. Sentinel already present: replace everything after it.
    2. File has user content but no sentinel: append sentinel + section.
    3. File is empty: write sentinel + section from scratch.
    """
    if EGG_SENTINEL in existing:
        head, _, _ = existing.partition(EGG_SENTINEL)
        return f"{head.rstrip()}\n\n{EGG_SENTINEL}\n\n{auto_section}\n"
    if existing.strip():
        return f"{existing.rstrip()}\n\n{EGG_SENTINEL}\n\n{auto_section}\n"
    return f"{EGG_SENTINEL}\n\n{auto_section}\n"


def run(args) -> int:
    """Entry point for `pidgin egg <path>`.

    1. Resolves the project root from args.path.
    2. Loads all FunctionRecords from the nest for that root.
    3. Filters to records under args.path.
    4. Groups by directory and writes/updates CLAUDE.md files.
    5. Prints a summary line and returns 0, or 1 on error.
    """
    from pidgin.store import nest as nest_store
    from pidgin.utils.git import find_project_root

    root = find_project_root(args.path) or args.path
    records = list(nest_store.iter_records(root))
    if not records:
        print(
            f"[egg] FATAL: nest at {root} is empty. Run `pidgin index` "
            f"before `pidgin egg`.",
            file=sys.stderr,
        )
        return 1

    # Filter records to those under args.path.
    base = Path(args.path).resolve()
    filtered = [r for r in records if Path(r.file_path).resolve().is_relative_to(base)]
    if not filtered:
        print(f"[egg] FATAL: no indexed functions under {args.path}.", file=sys.stderr)
        return 1

    groups = _group_functions_by_directory(filtered)
    n_written = 0
    for dir_path, recs in sorted(groups.items()):
        auto = _build_auto_section(dir_path, recs)
        target = Path(dir_path, "CLAUDE.md")
        existing = target.read_text() if target.exists() else ""
        target.write_text(_splice_into_existing(existing, auto))
        n_written += 1

    print(f"[egg] Wrote {n_written} CLAUDE.md files under {args.path}.")
    return 0
