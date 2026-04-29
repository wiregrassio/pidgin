# pidgin/verbs/update.py — wired in M12.
# --write-source required; --edits-file required (interactive mode out of scope for v0.2).

# MODULE: verbs.update
# DOES: Rewrite function docstrings/comments from MLD descriptions using an edits file.
#       Requires --write-source and --edits-file.
# EMITS: Modified source files via pidgin.write.update (Mode 2 transaction).
# READS: args.path, args.write_source, args.edits_file; JSONL edits file.
# IMPLEMENTS: permission enforcement (--write-source + --edits-file required, exit 2);
#             JSONL edits dispatch (v0.2 stub — dispatch loop wired, kinds TBD in M13+).
# DEPENDS: pidgin.write.update; sys, os, json.

import sys


def run(args) -> int:
    """Run the update verb.

    Requires --write-source. Requires --edits-file (interactive mode is out of
    scope for v0.2). Reads JSONL from edits_file and dispatches each edit op
    into a Transaction on args.path.
    """
    if not args.write_source:
        print(
            "pidgin update: refusing to write without --write-source."
            " Re-run with --write-source.",
            file=sys.stderr,
        )
        return 2

    if not args.edits_file:
        print(
            "pidgin update: --edits-file required"
            " (interactive mode out of scope for v0.2).",
            file=sys.stderr,
        )
        return 2

    import json
    from pidgin.write import update

    with update(args.path) as txn:
        with open(args.edits_file) as ef:
            for line in ef:
                line = line.strip()
                if not line:
                    continue
                op = json.loads(line)
                kind = op.get("kind")
                if kind in ("replace", "replace_lines"):
                    txn.replace(
                        line_start=op["line_start"],
                        line_end=op["line_end"],
                        content=op["content"],
                    )
                elif kind == "insert_tag":
                    txn.insert_tag(
                        line=op["line"],
                        tag=op["tag"],
                        content=op.get("content", ""),
                    )
                elif kind == "strip_comment":
                    txn.strip_comment(line=op["line"])
                else:
                    print(
                        f"pidgin update: unknown edit kind {kind!r}, skipping.",
                        file=sys.stderr,
                    )

    print(f"[update] Applied {len(txn.queued)} ops to {args.path}")
    return 0
