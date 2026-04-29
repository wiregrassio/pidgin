# pidgin v0.2 — extracted from tools/store/audit.py (v0.1).
# Provenance: `crispr_write`, `crispr_edit`, hash-verification helpers.
# Behaviour change vs v0.1: bracket wraps the FILE, not each operation
# (write-model.md, Mode 2). Operations accumulate in memory and apply
# atomically on context exit.
#
# MODULE: pidgin.write.update
# DOES: Mode 2 transaction context manager — accumulates edit operations in
#       memory, applies them atomically on exit, and brackets the file with
#       pre/post git commits plus one JSONL audit entry.
# EMITS: file write (atomic); up to two git commits; one JSONL line
# READS: file content (pre_hash); git status (dirty-file detection)
# IMPLEMENTS: enter→pre_hash→maybe-pre-commit → queue ops → exit→overlap-
#             check→apply→atomic-write→post-commit→audit-append
# DEPENDS: dataclasses, hashlib, json, os, subprocess, uuid, datetime, pathlib

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class OverlappingEdit(Exception):
    """Raised when two queued operations have overlapping line ranges."""


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EditOp:
    kind: Literal["replace", "insert_tag", "strip_comment", "replace_lines"]
    line_start: int       # 1-indexed inclusive
    line_end: int         # 1-indexed inclusive; == line_start for single-line ops
    payload: str          # new content; empty string means deletion
    metadata: dict        # e.g. {"tag": "mld:extract_ast"} for insert_tag


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _audit_dir(project_root: str) -> Path:
    """Return <project_root>/.pidgin/audit/, creating it if absent."""
    d = Path(project_root) / ".pidgin" / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _git_is_dirty(project_root: str, path: str) -> bool:
    """Return True if `path` appears in `git status --porcelain` output.

    Uses `git -C project_root status --porcelain -- <path>`.
    Any non-empty output means the file is dirty vs HEAD.
    """
    result = subprocess.run(
        ["git", "-C", project_root, "status", "--porcelain", "--", path],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _git_add_commit(project_root: str, path: str, message: str) -> str:
    """Stage `path` and commit with `message` in `project_root`.

    Returns the full commit SHA of the resulting commit.
    Raises RuntimeError on git add or commit failure.
    """
    add_result = subprocess.run(
        ["git", "-C", project_root, "add", "--", path],
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        raise RuntimeError(f"git add failed: {add_result.stderr.strip()}")

    commit_result = subprocess.run(
        ["git", "-C", project_root, "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if commit_result.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit_result.stderr.strip()}")

    sha_result = subprocess.run(
        ["git", "-C", project_root, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sha_result.stdout.strip()


def _detect_overlap(ops: list[EditOp]) -> None:
    """Raise OverlappingEdit if any two ops have overlapping original ranges.

    Overlap condition: s1 <= e2 AND s2 <= e1 (inclusive endpoint sharing
    counts as overlap — e.g. [1,2] and [2,3] overlap at 2).
    """
    for i in range(len(ops)):
        for j in range(i + 1, len(ops)):
            a, b = ops[i], ops[j]
            if a.line_start <= b.line_end and b.line_start <= a.line_end:
                raise OverlappingEdit(
                    f"Ops {i} ({a.kind} lines {a.line_start}-{a.line_end}) "
                    f"and {j} ({b.kind} lines {b.line_start}-{b.line_end}) "
                    f"overlap."
                )


def _apply_ops(lines: list[str], ops: list[EditOp], file_ext: str) -> list[str]:
    """Apply `ops` (in queue order) to `lines` using a running delta offset.

    `lines` is a list of raw line strings (with newlines preserved).
    `file_ext` is used by insert_tag to determine comment syntax.

    Running delta: each op targets ORIGINAL line numbers. As ops are applied
    the actual positions shift. `delta` tracks the cumulative line count
    change so original indices can be translated to current positions.

    Returns the modified list of lines.
    """
    delta = 0  # cumulative offset from ops applied so far

    for op in ops:
        # Translate original 1-indexed line numbers to 0-indexed current positions.
        start_0 = (op.line_start - 1) + delta
        end_0 = (op.line_end - 1) + delta  # inclusive

        if op.kind in ("replace", "replace_lines"):
            replacement = op.payload
            if replacement and not replacement.endswith("\n"):
                replacement += "\n"
            replacement_lines = replacement.splitlines(keepends=True) if replacement else []
            old_count = end_0 - start_0 + 1
            lines = lines[:start_0] + replacement_lines + lines[end_0 + 1:]
            delta += len(replacement_lines) - old_count

        elif op.kind == "insert_tag":
            if file_ext != ".py":
                raise NotImplementedError(
                    f"insert_tag is only implemented for .py files; got {file_ext!r}"
                )
            tag = op.metadata.get("tag", "")
            content = op.payload
            # Build comment block: # <tag>, # <content lines>, # </tag>
            comment_lines = [f"# <{tag}>\n"]
            for content_line in content.splitlines():
                comment_lines.append(f"# {content_line}\n")
            comment_lines.append(f"# </{tag}>\n")
            # Insert IMMEDIATELY BEFORE start_0 (the current position of op.line)
            lines = lines[:start_0] + comment_lines + lines[start_0:]
            delta += len(comment_lines)

        elif op.kind == "strip_comment":
            # No-op path: metadata={"noop": True} means we already recorded it.
            if op.metadata.get("noop"):
                pass  # no-op: line was not a comment; recorded in queue only
            else:
                # Delete the single physical line.
                lines = lines[:start_0] + lines[start_0 + 1:]
                delta -= 1

        else:
            raise ValueError(f"Unknown op kind: {op.kind!r}")

    return lines


# ---------------------------------------------------------------------------
# Public context manager — Transaction
# ---------------------------------------------------------------------------

class Transaction:
    """Context manager that batches edit operations and applies them atomically.

    Usage::

        with update("parser.py", project_root="/my/repo") as f:
            f.replace(line_start=5, line_end=5, content="# new line")
            f.insert_tag(line=8, tag="mld:foo", content="description")
        # exits: one write, one git commit, one audit entry

    On exception inside the block: queued ops are discarded; no write, no commit.
    On clean exit with no ops: no-op.
    """

    def __init__(self, path: str, *, project_root: str = "/project") -> None:
        self._path = str(Path(path).resolve())
        self._project_root = str(Path(project_root).resolve())
        self._ops: list[EditOp] = []
        self._pre_hash: str = ""
        self._pre_commit_sha: str | None = None
        self._file_content_bytes: bytes = b""

    # ------------------------------------------------------------------
    # Context protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "Transaction":
        p = Path(self._path)
        self._file_content_bytes = p.read_bytes()
        self._pre_hash = _sha256_bytes(self._file_content_bytes)

        # Dirty-file pre-commit: if file is dirty vs HEAD, commit it now.
        if _git_is_dirty(self._project_root, self._path):
            relpath = str(Path(self._path).relative_to(self._project_root))
            msg = f"pidgin/update: pre-bracket snapshot of {relpath}"
            self._pre_commit_sha = _git_add_commit(
                self._project_root, self._path, msg
            )
        # else: file is clean — skip pre-commit; pre_commit_sha stays None.

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            # Exception in block: discard ops, do not write.
            self._ops.clear()
            return False  # re-raise the exception

        if not self._ops:
            # No ops queued: no-op.
            return False

        # --- Overlap check ---
        _detect_overlap(self._ops)

        # --- Apply ops in memory ---
        original_lines = self._file_content_bytes.decode("utf-8").splitlines(keepends=True)
        file_ext = Path(self._path).suffix
        new_lines = _apply_ops(list(original_lines), self._ops, file_ext)
        new_content = "".join(new_lines)

        # --- Atomic write ---
        encoded = new_content.encode("utf-8")
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "wb") as fh:
            fh.write(encoded)
        os.replace(tmp_path, self._path)

        # --- Post-hash ---
        post_hash = _sha256_bytes(encoded)

        # --- Git add + commit ---
        relpath = str(Path(self._path).relative_to(self._project_root))
        n = len(self._ops)
        msg = f"pidgin/update: {relpath} ({n} ops)"
        post_commit_sha = _git_add_commit(self._project_root, self._path, msg)

        # --- Audit append ---
        audit_dir = _audit_dir(self._project_root)
        audit_id = uuid.uuid4().hex
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "audit_id": audit_id,
            "path": self._path,
            "pre_hash": self._pre_hash,
            "post_hash": post_hash,
            "pre_commit_sha": self._pre_commit_sha,
            "post_commit_sha": post_commit_sha,
            "ops": [
                {
                    "kind": op.kind,
                    "line_start": op.line_start,
                    "line_end": op.line_end,
                    "payload": op.payload,
                    "metadata": op.metadata,
                }
                for op in self._ops
            ],
            "bytes_before": len(self._file_content_bytes),
            "bytes_after": len(encoded),
        }
        log_path = audit_dir / "update.jsonl"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

        return False

    # ------------------------------------------------------------------
    # Operation queue API (all return self for chaining)
    # ------------------------------------------------------------------

    def replace(self, *, line_start: int, line_end: int, content: str) -> "Transaction":
        """Queue a replace of lines [line_start..line_end] with `content`."""
        if line_start > line_end:
            raise ValueError(
                f"replace: line_start ({line_start}) must be <= line_end ({line_end})"
            )
        self._ops.append(EditOp(
            kind="replace",
            line_start=line_start,
            line_end=line_end,
            payload=content,
            metadata={},
        ))
        return self

    def insert_tag(self, *, line: int, tag: str, content: str) -> "Transaction":
        """Queue an insert_tag comment block immediately before `line`."""
        self._ops.append(EditOp(
            kind="insert_tag",
            line_start=line,
            line_end=line,
            payload=content,
            metadata={"tag": tag},
        ))
        return self

    def strip_comment(self, *, line: int) -> "Transaction":
        """Queue a strip_comment on `line`.

        If the line is not a `#` comment, records a no-op with metadata={"noop": True}.
        The no-op is assessed at queue time by reading the in-memory file content.
        """
        # Peek at the line content to determine if it's a comment.
        raw_lines = self._file_content_bytes.decode("utf-8").splitlines()
        if 1 <= line <= len(raw_lines):
            stripped = raw_lines[line - 1].lstrip()
            is_comment = stripped.startswith("#")
        else:
            is_comment = False

        metadata: dict = {} if is_comment else {"noop": True}
        self._ops.append(EditOp(
            kind="strip_comment",
            line_start=line,
            line_end=line,
            payload="",
            metadata=metadata,
        ))
        return self

    def replace_lines(self, *, line_start: int, line_end: int, content: str) -> "Transaction":
        """Alias of replace."""
        return self.replace(line_start=line_start, line_end=line_end, content=content)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def queued(self) -> list[EditOp]:
        """Return a copy of the current op queue."""
        return list(self._ops)


# ---------------------------------------------------------------------------
# Module-level entrypoint
# ---------------------------------------------------------------------------

def update(path: str, *, project_root: str = "/project") -> Transaction:
    """Return a Transaction context manager for `path` inside `project_root`.

    Usage::

        with update("parser.py", project_root="/my/repo") as f:
            f.replace(line_start=1, line_end=1, content="# new")
    """
    return Transaction(path, project_root=project_root)
