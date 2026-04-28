# MODULE: pidgin.write.new
# DOES: Mode 3 artifact write — batch file writes with one git commit and one
#       JSONL audit entry per batch. No hash pre-verification; no pre-write commit.
# EMITS: file writes; one git commit per batch; one JSONL line per batch
# READS: nothing prior to writing (Mode 3 semantics)
# IMPLEMENTS: mkdir-p → atomic write → git add+commit → audit append
# DEPENDS: hashlib, json, os, subprocess, uuid, datetime, pathlib
#
# pidgin v0.2 — extracted from tools/store/audit.py (v0.1)
# Provenance: function `crispr_write` (legacy Mode-2 only). This module
# implements Modes 3 (artifact_write) and 4 (compress_write) which were
# missing in v0.1.

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pidgin.utils.git import find_project_root, git_commit_files, is_git_repo

# ---------------------------------------------------------------------------
# Shared dataclass (imported by compress.py)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactWriteResult:
    files_written: list[str]   # absolute paths
    commit_sha: str            # post-write commit SHA, "" if no git
    audit_id: str              # audit-entry uuid (one per batch)
    bytes_total: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: str, content: str) -> tuple[bytes, int]:
    """Write content to path atomically via a .tmp sibling.

    Returns (encoded_bytes, byte_count).

    NOTE: os.replace is atomic on POSIX when src and dst share a filesystem.
    Cross-mount writes will raise OSError(EXDEV). Document in anomalies.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    encoded = content.encode("utf-8")
    tmp_path = str(p) + ".tmp"
    with open(tmp_path, "wb") as fh:
        fh.write(encoded)
    os.replace(tmp_path, str(p))
    return encoded, len(encoded)


def _audit_dir(project_root: str) -> Path:
    """Return <project_root>/.pidgin/audit/, creating it if absent."""
    d = Path(project_root) / ".pidgin" / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _append_audit(
    project_root: str,
    audit_id: str,
    mode: str,
    file_entries: list[dict],
    commit_sha: str,
    audit_metadata: dict,
) -> None:
    """Append one JSONL line to <project_root>/.pidgin/audit/artifact_write.jsonl."""
    audit_dir = _audit_dir(project_root)
    log_path = audit_dir / "artifact_write.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "audit_id": audit_id,
        "mode": mode,
        "files": file_entries,
        "commit_sha": commit_sha,
        "audit_metadata": audit_metadata,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Public API — artifact_write (Mode 3)
# ---------------------------------------------------------------------------

def artifact_write(
    files: list[tuple[str, str]],       # [(absolute_path, content), ...]
    audit_metadata: dict,               # caller-supplied tags (mission, verb, etc.)
    *,
    project_root: Path | None = None,   # PD1: auto-derive from .git if None
    commit_message: str | None = None,  # default: derived from audit_metadata
    skip_git: bool = False,             # for tests; default False
) -> ArtifactWriteResult:
    """Write a batch of files, then produce one git commit and one audit entry.

    Modes 3 semantics:
    - No hash pre-verification.
    - No pre-write commit.
    - All files written first, then one `git add` + `git commit`.
    - One JSONL audit line covering the entire batch.

    PD1: If project_root is None, auto-derive by walking up from the first
    file's directory to the nearest .git boundary.
    """
    if not files:
        raise ValueError("artifact_write: files list must not be empty")

    # PD1: auto-derive project_root
    if project_root is None:
        first_path = files[0][0]
        derived = find_project_root(str(Path(first_path).parent))
        if derived is None and not skip_git:
            raise RuntimeError(
                f"artifact_write: could not find a .git directory above "
                f"{Path(first_path).parent}. Pass project_root= explicitly "
                f"or use skip_git=True."
            )
        project_root_str = derived or str(Path(first_path).parent)
    else:
        project_root_str = str(Path(project_root).resolve())

    # Write all files atomically.
    file_entries: list[dict] = []
    files_written: list[str] = []
    bytes_total = 0

    for path, content in files:
        abs_path = str(Path(path).resolve())
        encoded, byte_count = _atomic_write(abs_path, content)
        sha = _sha256_bytes(encoded)
        file_entries.append({
            "path": abs_path,
            "sha256": sha,
            "bytes": byte_count,
        })
        files_written.append(abs_path)
        bytes_total += byte_count

    # Single git add + commit for the whole batch.
    commit_sha = ""
    if not skip_git:
        if commit_message is None:
            mission = audit_metadata.get("mission", "batch")
            commit_message = f"pidgin/artifact_write: {mission}"
        commit_sha = git_commit_files(
            project_root_str,
            files_written,
            commit_message,
        )

    # One JSONL audit entry for the batch.
    audit_id = uuid.uuid4().hex
    _append_audit(
        project_root_str,
        audit_id,
        mode="new",
        file_entries=file_entries,
        commit_sha=commit_sha,
        audit_metadata=audit_metadata,
    )

    return ArtifactWriteResult(
        files_written=files_written,
        commit_sha=commit_sha,
        audit_id=audit_id,
        bytes_total=bytes_total,
    )
