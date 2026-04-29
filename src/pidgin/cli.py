#!/usr/bin/env python3
# pidgin/cli.py — argparse entry point for the `pidgin` CLI.
# PD2: flags are per-subcommand via parents=. Global flags before the verb are NOT supported.
# PD3: --sync and --batch together → exit 2 with explicit error message.

# MODULE: cli
# DOES: Build the argparse parser tree for the pidgin CLI and dispatch to verb modules.
# EMITS: exit codes; delegates output to verb modules.
# READS: sys.argv (or argv kwarg).
# IMPLEMENTS: PD2 (per-subcommand flags via parents=); PD3 (--sync+--batch guard).
# DEPENDS: argparse, sys; pidgin.verbs.*

import argparse
import sys


def _shared_flags() -> argparse.ArgumentParser:
    """Return a parent parser carrying shared dispatch flags.

    PD2: attached via parents= so flags appear after the verb, not before it.
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument(
        "--write-db",
        action="store_true",
        help="Persist results to the local .pidgin/nest/ ChromaDB.",
    )
    p.add_argument(
        "--write-source",
        action="store_true",
        help="Allow writes back to source files (required for update/new).",
    )
    p.add_argument(
        "--sync",
        action="store_true",
        help="Force synchronous (non-batch) API dispatch.",
    )
    p.add_argument(
        "--batch",
        action="store_true",
        help="Force OpenAI Batch API dispatch.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-function status lines after the MLD pipeline completes.",
    )
    return p


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argparse parser for pidgin."""
    shared = _shared_flags()

    p = argparse.ArgumentParser(
        prog="pidgin",
        description="Pidgin — MLD-powered function description CLI.",
    )
    sub = p.add_subparsers(dest="verb", required=True)

    # index: pidgin index <path> [--write-db] [--sync] [--batch]
    pi = sub.add_parser(
        "index",
        parents=[shared],
        help="Discover public functions and (optionally) run the MLD pipeline.",
    )
    pi.add_argument(
        "path",
        help="Directory or file to index.",
    )
    pi.add_argument(
        "--exclude", action="append", default=[],
        metavar="GLOB",
        help="Glob pattern to exclude (relative to indexed root). May be "
             "passed multiple times.",
    )
    pi.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Preview: count functions, estimate API calls and cost, check "
             "API key availability. Does not call any APIs or write the nest.",
    )

    # update: pidgin update <path> [--write-source] [--edits-file FILE]
    pu = sub.add_parser(
        "update",
        parents=[shared],
        help="(stub) Rewrite function docstrings from MLD descriptions. Wired in M12.",
    )
    pu.add_argument(
        "path",
        help="Directory or file to update.",
    )
    pu.add_argument(
        "--edits-file",
        metavar="FILE",
        help="Path to an edits JSON file (wired in M12).",
    )

    # new: pidgin new <kind> [--write-source]
    # Kinds: origami, architecture, claude-md
    pn = sub.add_parser(
        "new",
        parents=[shared],
        help="Generate a new documentation file from a template. Wired in M12.",
    )
    pn.add_argument(
        "kind",
        help="Template kind: origami | architecture | claude-md.",
    )

    # query: pidgin query <text> [--raw] [--verbose]
    pq = sub.add_parser(
        "query",
        parents=[shared],
        help="Search the function vector store. Normalises queries via gpt-4.1-nano (M7).",
    )
    pq.add_argument(
        "text",
        help="Natural-language query string.",
    )
    pq.add_argument(
        "--raw",
        action="store_true",
        help="Skip query normalisation (use the input text verbatim).",
    )

    # init: pidgin init <path>
    pini = sub.add_parser(
        "init",
        parents=[shared],
        help="(stub) Initialise a .pidgin/ directory. Wired in M13.",
    )
    pini.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Target directory (default: current directory).",
    )

    # summarize: pidgin summarize <path|-> [--xml|--markdown]
    sp_summarize = sub.add_parser(
        "summarize", help="Single-file MLD to stdout (markdown or XML).")
    sp_summarize.add_argument("path", help="Path to source file or '-' for stdin.")
    group = sp_summarize.add_mutually_exclusive_group()
    group.add_argument("--markdown", action="store_true", help="Markdown output (default).")
    group.add_argument("--xml", action="store_true", help="XML output.")

    # egg: pidgin egg <path>
    sp_egg = sub.add_parser(
        "egg", help="Generate/update CLAUDE.md discovery files from the nest.")
    sp_egg.add_argument(
        "path",
        help="Directory to walk (must be inside an indexed repo).",
    )

    # depends: pidgin depends <path> [--json]
    sp_depends = sub.add_parser(
        "depends", help="Show import graph for a file.")
    sp_depends.add_argument("path", help="Path to a source file.")
    sp_depends.add_argument("--json", action="store_true",
        help="JSON output (for LLM consumption).")
    sp_depends.set_defaults(func=run_depends_main_entry)

    return p


def run_summarize_main_entry(args) -> int:
    """Lazy entry point for the summarize verb (wired in M8).

    Imports pidgin.verbs.summarize at call time to avoid loading API
    dependencies on every CLI invocation.
    """
    from pidgin.verbs.summarize import run
    return run(args)


def run_egg_main_entry(args) -> int:
    """Lazy entry point for the egg verb (wired in M9).

    Imports pidgin.verbs.egg at call time to avoid loading dependencies
    on every CLI invocation.
    """
    from pidgin.verbs.egg import run
    return run(args)


def run_depends_main_entry(args) -> int:
    """Lazy entry point for the depends verb (wired in M10).

    Imports pidgin.verbs.depends at call time to avoid loading dependencies
    on every CLI invocation.
    """
    from pidgin.verbs.depends import run_depends
    return run_depends(args)


def main(argv=None) -> int:
    """Parse argv and dispatch to the appropriate verb module.

    Returns an integer exit code (0 = success, 1 = error, 2 = usage error).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # PD3: --sync and --batch are mutually exclusive.
    if getattr(args, "sync", False) and getattr(args, "batch", False):
        print("Cannot specify both --sync and --batch.", file=sys.stderr)
        return 2

    # Dispatch to verb modules.
    from pidgin.verbs import index, update, new, query, init

    verbs = {
        "index": index.run,
        "update": update.run,
        "new": new.run,
        "query": query.run,
        "init": init.run,
        "summarize": run_summarize_main_entry,
        "egg": run_egg_main_entry,
        "depends": run_depends_main_entry,
    }

    verb_fn = verbs.get(args.verb)
    if verb_fn is None:
        print(f"Unknown verb: {args.verb}", file=sys.stderr)
        return 2

    try:
        result = verb_fn(args)
        return result if result is not None else 0
    except NotImplementedError as exc:
        print(f"NotImplementedError: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
