# MODULE: pidgin.write.compress
# DOES: Mode 4 compress write — same batch write semantics as Mode 3, plus
#       input_source_hash lineage tracking for each (input→output) pair.
# EMITS: file writes; one git commit per batch; one JSONL line per batch
# READS: input_path files (to compute input_source_hash before writing)
# IMPLEMENTS: read inputs → mkdir-p → atomic write → git add+commit → audit append
# DEPENDS: hashlib, pathlib
#
# pidgin v0.2 — extracted from tools/store/audit.py (v0.1)
# Provenance: function `crispr_write` (legacy Mode-2 only). This module
# implements Modes 3 (artifact_write) and 4 (compress_write) which were
# missing in v0.1.

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pidgin.write.new import (
    ArtifactWriteResult,
    _append_audit,
    _atomic_write,
    _sha256_bytes,
)
from pidgin.utils.git import find_project_root, git_commit_files


# ---------------------------------------------------------------------------
# Public API — compress_write (Mode 4)
# ---------------------------------------------------------------------------

def compress_write(
    inputs: list[tuple[str, str, str]],  # [(input_path, output_path, output_content), ...]
    audit_metadata: dict,
    *,
    project_root: Path | None = None,    # PD1: auto-derive from .git if None
    commit_message: str | None = None,
    skip_git: bool = False,
) -> ArtifactWriteResult:
    """Write a batch of compressed artifacts with input lineage tracking.

    Mode 4 semantics:
    - For each (input_path, output_path, output_content):
      - Read input_path and sha256 it (HARD failure if unreadable).
      - Write output_path atomically.
      - Record input_source_hash in the audit lineage entry.
    - One git commit for the entire batch of output files.
    - One JSONL audit entry with mode="compress" and full lineage.

    HARD failure: if any input_path does not exist or is not readable,
    raises RuntimeError immediately — no silent skips.

    PD1: If project_root is None, auto-derive by walking up from the first
    output file's directory to the nearest .git boundary.
    """
    if not inputs:
        raise ValueError("compress_write: inputs list must not be empty")

    # PD1: auto-derive project_root from the first output path.
    if project_root is None:
        first_output = inputs[0][1]
        derived = find_project_root(str(Path(first_output).parent))
        if derived is None and not skip_git:
            raise RuntimeError(
                f"compress_write: could not find a .git directory above "
                f"{Path(first_output).parent}. Pass project_root= explicitly "
                f"or use skip_git=True."
            )
        project_root_str = derived or str(Path(first_output).parent)
    else:
        project_root_str = str(Path(project_root).resolve())

    # Phase 1: read all inputs first (HARD failure if any missing).
    input_hashes: list[str] = []
    for input_path, _output_path, _output_content in inputs:
        p = Path(input_path)
        if not p.exists():
            raise RuntimeError(
                f"compress_write: input_path does not exist: {input_path!r}"
            )
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"compress_write: cannot read input_path {input_path!r}: {exc}"
            ) from exc
        input_hashes.append(_sha256_bytes(data))

    # Phase 2: write all output files atomically.
    lineage: list[dict] = []
    files_written: list[str] = []
    bytes_total = 0

    for (input_path, output_path, output_content), input_source_hash in zip(
        inputs, input_hashes
    ):
        abs_output = str(Path(output_path).resolve())
        encoded, byte_count = _atomic_write(abs_output, output_content)
        output_sha256 = _sha256_bytes(encoded)
        lineage.append({
            "input_path": str(Path(input_path).resolve()),
            "input_source_hash": input_source_hash,
            "output_path": abs_output,
            "output_sha256": output_sha256,
            "output_bytes": byte_count,
        })
        files_written.append(abs_output)
        bytes_total += byte_count

    # Single git add + commit for the whole batch.
    commit_sha = ""
    if not skip_git:
        if commit_message is None:
            mission = audit_metadata.get("mission", "batch")
            commit_message = f"pidgin/compress_write: {mission}"
        commit_sha = git_commit_files(
            project_root_str,
            files_written,
            commit_message,
        )

    # One JSONL audit entry for the batch (mode="compress", lineage= instead of files=).
    audit_id = uuid.uuid4().hex
    _append_compress_audit(
        project_root_str,
        audit_id,
        lineage=lineage,
        commit_sha=commit_sha,
        audit_metadata=audit_metadata,
    )

    return ArtifactWriteResult(
        files_written=files_written,
        commit_sha=commit_sha,
        audit_id=audit_id,
        bytes_total=bytes_total,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _append_compress_audit(
    project_root: str,
    audit_id: str,
    lineage: list[dict],
    commit_sha: str,
    audit_metadata: dict,
) -> None:
    """Append one JSONL line to <project_root>/.pidgin/audit/artifact_write.jsonl
    using mode="compress" and a lineage list instead of a files list.
    """
    from pidgin.write.new import _audit_dir
    audit_dir = _audit_dir(project_root)
    log_path = audit_dir / "artifact_write.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "audit_id": audit_id,
        "mode": "compress",
        "lineage": lineage,
        "commit_sha": commit_sha,
        "audit_metadata": audit_metadata,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
