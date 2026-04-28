# pidgin/verbs/

CLI verb implementations for the `pidgin` command.
Each module exposes one public function: `run(args) -> int`.

PD2: All flags are per-subcommand (after the verb). Global flags before the verb are NOT supported.
PD3: `--sync` + `--batch` together → exit 2. Enforced in cli.py before dispatch.
PD6: `index` without `--write-db` → dry-run, zero API calls.

## Files

| File | Status | DOES |
|------|--------|------|
| `index.py` | Wired (M11/M12) | Walk path, extract public functions, optionally run MLD pipeline and upsert to per-repo .pidgin/nest/. |
| `update.py` | Wired (M12) | Rewrite function docstrings from MLD descriptions via --edits-file. |
| `new.py` | Wired (M12) | Generate a new documentation file from a template kind (origami/architecture/claude-md). |
| `query.py` | Wired (M12) | Search the per-repo .pidgin/nest/ by natural-language query. |
| `init.py` | Stub (M13) | Initialise a .pidgin/ directory in the target repo. |

## Verb Signatures

All verbs: `run(args) -> int`

`args` is the parsed argparse Namespace from cli.py. Common attributes:
- `args.write_db` (bool) — persist to ChromaDB
- `args.write_source` (bool) — allow source file writes
- `args.sync` (bool) — force sync dispatch
- `args.batch` (bool) — force batch dispatch

`index` additionally: `args.path` (str)
`update` additionally: `args.path` (str), `args.edits_file` (str|None)
`new` additionally: `args.kind` (str) — one of: origami, architecture, claude-md
`query` additionally: `args.text` (str)
`init` additionally: `args.path` (str)

## How to Navigate

Read `index.py` for the fully wired implementation pattern.
Stubs are one-liners raising NotImplementedError with a mission reference.
