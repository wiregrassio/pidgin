# pidgin/verbs/init.py — wired in M13.

# MODULE: verbs.init
# DOES: Discover child nests under a root directory and optionally persist a
#       JSON registry. Prints discovered nests to stdout.
# EMITS: Discovery report to stdout; optional registry.json write.
# READS: args.path (or cwd); filesystem via discovery.discover_nests.
# IMPLEMENTS: nest discovery; registry persistence; --write-db gate.
# DEPENDS: pidgin.store.discovery; os, sys.

import os


def run(args) -> int:
    """Run the init verb.

    Discovers child directories containing .pidgin/nest/ under the given root
    (defaulting to cwd). Prints each discovered nest. If --write-db is set,
    persists a JSON registry at <root>/.pidgin/registry.json.
    """
    from pidgin.store import discovery, nest

    root = os.path.abspath(getattr(args, "path", None) or os.getcwd())

    # Bootstrap the nest directory if it doesn't exist.
    # ensure_nest walks up to .git so the nest always lands at the repo root.
    nest_dir = nest.ensure_nest(root)
    print(f"[init] Nest ensured at {nest_dir}")

    # Write the CLAUDE.md discovery file if it doesn't exist.
    # write_nest_claude_md resolves git root internally and skips if file exists.
    claude_md_path = nest.write_nest_claude_md(root)
    print(f"[init] CLAUDE.md at {claude_md_path}")
    nests = discovery.discover_nests(root)
    print(f"[init] Discovered {len(nests)} nested nest(s) under {root}")
    for n in nests:
        print(f"  - {n.namespace} → {n.nest_path}")
    if not nests:
        print("[init] No child nests found.")
        return 0
    if args.write_db:
        path = discovery.register_nests(root, nests)
        print(f"[init] Registry persisted at {path}")
    else:
        print("[init] Re-run with --write-db to persist the registry.")
    return 0
