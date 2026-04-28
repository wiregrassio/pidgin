# pidgin/write/

Write-model sub-package. Implements artifact write Modes 2, 3, and 4.

## Modes

| Mode | Name | File | Summary |
|------|------|------|---------|
| 2 | Update | update.py | Transaction context manager. Accumulates edit ops in memory, applies atomically on exit. Bracket wraps the FILE, not each op. One git commit + one audit entry per transaction. |
| 3 | New | new.py | Batch write with no pre-hash check. One git commit + one audit entry per batch. |
| 4 | Compress | compress.py | Same write semantics as Mode 3 plus input_source_hash lineage per (input→output) pair. |

## Mode 2 — Update (update.py)

### Rule: bracket wraps the file

v0.1 (`crispr_edit`) committed once per operation. Mode 2 commits once per
FILE. All ops accumulate in memory inside the `with` block and apply atomically
on `__exit__`. On exception: ops discarded, no write, no commit.

### Function signatures

```python
def update(path: str, *, project_root: str = "/project") -> Transaction: ...
```

```python
class Transaction:
    def __init__(self, path: str, *, project_root: str = "/project") -> None: ...
    def __enter__(self) -> "Transaction": ...
    def __exit__(self, exc_type, exc, tb) -> bool: ...

    # Operation queue API — all return self for chaining
    def replace(self, *, line_start: int, line_end: int, content: str) -> "Transaction": ...
    def insert_tag(self, *, line: int, tag: str, content: str) -> "Transaction": ...
    def strip_comment(self, *, line: int) -> "Transaction": ...
    def replace_lines(self, *, line_start: int, line_end: int, content: str) -> "Transaction": ...

    @property
    def queued(self) -> list[EditOp]: ...
```

### EditOp dataclass

```python
@dataclass(frozen=True)
class EditOp:
    kind: Literal["replace", "insert_tag", "strip_comment", "replace_lines"]
    line_start: int       # 1-indexed inclusive
    line_end: int         # 1-indexed inclusive; == line_start for single-line ops
    payload: str          # new content; empty string means deletion
    metadata: dict        # e.g. {"tag": "mld:extract_ast"} or {"noop": True}
```

### EditOp kinds

| Kind | Semantics |
|------|-----------|
| `replace` | Replace lines [line_start..line_end] inclusive with `payload`. If payload has no trailing newline, one is appended. |
| `replace_lines` | Alias of `replace`. |
| `insert_tag` | Insert a `# <tag>` comment block immediately BEFORE `line`. Python files only; non-`.py` raises NotImplementedError. |
| `strip_comment` | Delete the line if it starts with `#`. If not a comment, record no-op with `metadata={"noop": True}`. |

### OverlappingEdit exception

```python
class OverlappingEdit(Exception):
    """Raised when two queued ops have overlapping original line ranges."""
```

Overlap condition: `s1 <= e2 AND s2 <= e1` (inclusive — shared endpoint counts).
Checked at `__exit__` before any write. Example: [1,2] and [2,3] overlap at line 2.

### Lifecycle

1. `__enter__`: read file, capture `pre_hash` (sha256). If file is dirty vs HEAD, commit a pre-bracket snapshot; if clean, skip (pre_commit_sha is None).
2. Ops queue in `self._ops`. Nothing on disk changes inside the block.
3. `__exit__` (no exception, ops queued): overlap check → apply ops with running delta → atomic write → post_hash → git add+commit → audit append.

### Running line offset

Ops target ORIGINAL line numbers. A `delta` counter tracks cumulative line count
changes as each op is applied in queue order. Original 1-indexed line N maps to
current position `(N - 1) + delta` (0-indexed).

### Audit JSONL

Appends to `<project_root>/.pidgin/audit/update.jsonl`.

```json
{
  "timestamp": "<ISO8601 UTC>",
  "audit_id": "<uuid4 hex>",
  "path": "<absolute path>",
  "pre_hash": "<sha256 hex>",
  "post_hash": "<sha256 hex>",
  "pre_commit_sha": null,
  "post_commit_sha": "<full sha>",
  "ops": [
    {"kind": "replace", "line_start": 1, "line_end": 1, "payload": "...", "metadata": {}}
  ],
  "bytes_before": 123,
  "bytes_after": 124
}
```

## Function Signatures

### Mode 3 — artifact_write (new.py)

```python
def artifact_write(
    files: list[tuple[str, str]],           # [(absolute_path, content), ...]
    audit_metadata: dict,                   # caller-supplied tags (mission, verb, etc.)
    *,
    project_root: Path | None = None,       # PD1: auto-derive from .git if None
    commit_message: str | None = None,      # default: "pidgin/artifact_write: {mission}"
    skip_git: bool = False,                 # for tests; default False
) -> ArtifactWriteResult: ...
```

### Shared dataclass — ArtifactWriteResult (new.py)

```python
@dataclass(frozen=True)
class ArtifactWriteResult:
    files_written: list[str]    # absolute paths
    commit_sha: str             # post-write commit SHA, "" if no git
    audit_id: str               # audit-entry uuid (one per batch)
    bytes_total: int
```

### Mode 4 — compress_write (compress.py)

```python
def compress_write(
    inputs: list[tuple[str, str, str]],     # [(input_path, output_path, output_content), ...]
    audit_metadata: dict,
    *,
    project_root: Path | None = None,       # PD1: auto-derive
    commit_message: str | None = None,
    skip_git: bool = False,
) -> ArtifactWriteResult: ...
```

## Provenance

| File | Provenance |
|------|-----------|
| update.py | M2. Extracted from `tools/store/audit.py:crispr_write` / `crispr_edit`. Key behaviour change: bracket wraps the FILE not each op. |
| new.py | M1. Modes 3/4 were absent in v0.1. Extracted git-bracket logic from `tools/store/audit.py:crispr_write`. |
| compress.py | M1. Same provenance as new.py. Adds lineage tracking (input_source_hash) absent in v0.1. |
| \_\_init\_\_.py | Re-export facade. |

## Audit JSONL

All batch operations append to `<project_root>/.pidgin/audit/artifact_write.jsonl`.

Mode 3 entry shape:
```json
{
  "timestamp": "<ISO8601 UTC>",
  "audit_id": "<uuid4 hex>",
  "mode": "new",
  "files": [{"path": "...", "sha256": "...", "bytes": 123}],
  "commit_sha": "<full sha>",
  "audit_metadata": {"mission": "...", ...}
}
```

Mode 4 entry shape:
```json
{
  "timestamp": "<ISO8601 UTC>",
  "audit_id": "<uuid4 hex>",
  "mode": "compress",
  "lineage": [
    {
      "input_path": "...",
      "input_source_hash": "...",
      "output_path": "...",
      "output_sha256": "...",
      "output_bytes": 123
    }
  ],
  "commit_sha": "<full sha>",
  "audit_metadata": {"mission": "...", ...}
}
```

## How to Navigate

1. Find the symbol in the tables above.
2. Find its start line:
   `awk '/^def artifact_write/{ print NR; exit }' pidgin/write/new.py`
3. Find where the next symbol starts:
   `awk 'NR>START && /^def |^class /{ print NR; exit }' pidgin/write/new.py`
4. Read the range: lines START..END-1.

Never read an entire file. Use the index then awk then ranged read.
