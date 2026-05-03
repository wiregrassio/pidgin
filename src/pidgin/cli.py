"""pidgin.cli — argparse entry point.

Nine verb subparsers. Each verb dispatches to its module's main().
"""

import argparse
import sys

VERBS = {
    "index":  "pidgin.index",
    "search": "pidgin.search",
    "graph":  "pidgin.graph",
    "egg":    "pidgin.egg",
    "get":    "pidgin.get",
    "put":    "pidgin.put",
    "assert": "pidgin.assert_",
    "score":  "pidgin.score",
    "rank":   "pidgin.rank",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: pidgin {" + ",".join(VERBS) + "} ...")
        return 0
    verb = sys.argv[1]
    if verb not in VERBS:
        print(f"unknown verb: {verb}", file=sys.stderr)
        return 2
    sys.argv = [f"pidgin {verb}", *sys.argv[2:]]
    import importlib
    mod = importlib.import_module(VERBS[verb])
    return mod.main()
