# pidgin/verbs/new.py — wired in M12.

# MODULE: verbs.new
# DOES: Generate a new documentation file from a known template kind.
#       Requires --write-source. Kinds: origami, architecture, claude-md.
# EMITS: A single markdown file at <cwd>/<kind>.md via artifact_write.
# READS: args.kind, args.write_source.
# IMPLEMENTS: permission enforcement (--write-source required, exit 2);
#             template dispatch for v0.2 stub (not full MLD pipeline).
# DEPENDS: pidgin.write.artifact_write; sys, os.

import os
import sys


TEMPLATES: dict[str, str] = {
    "origami": "# Origami Principles\n\n...\n",
    "architecture": "# Architecture\n\n...\n",
    "claude-md": "# CLAUDE.md\n\n...\n",
}


def run(args) -> int:
    """Run the new verb.

    Requires --write-source. Creates a templated markdown file at
    <cwd>/<kind>.md using artifact_write (Mode 3).
    """
    if not args.write_source:
        print(
            "pidgin new: refusing to create files without --write-source."
            " Re-run with --write-source.",
            file=sys.stderr,
        )
        return 2

    kind = args.kind
    if kind not in TEMPLATES:
        print(
            f"pidgin new: unknown kind {kind!r}. Known: {list(TEMPLATES)}",
            file=sys.stderr,
        )
        return 2

    from pidgin.write import artifact_write

    outpath = os.path.join(os.getcwd(), f"{kind}.md")
    artifact_write(
        [(outpath, TEMPLATES[kind])],
        {"mission": "new", "kind": kind},
    )
    print(f"[new] Created {outpath}")
    return 0
