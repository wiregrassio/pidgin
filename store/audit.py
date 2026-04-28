#!/usr/bin/env python3
# pidgin v0.2 — extracted from tools/store/audit.py (v0.1).
# Provenance: tools/store/audit.py — JSONL helpers only (file_hash, audit_log_path,
#   audit_log). The transaction code (crispr_write, crispr_edit, CrisprResult) is
#   NOT included here — it is superseded by pidgin/write/update.py (Mode 2) and
#   pidgin/write/new.py (Mode 3/4) which implement the same semantics with a
#   file-bracketed commit instead of a per-operation bracket.

# MODULE: audit
# DOES: JSONL audit helpers — file hash, audit log path, and atomic JSONL append.
# EMITS: JSONL lines to local/audit/marionette_actions.jsonl
# READS: file content (for hashing)
# IMPLEMENTS: sha256 file hash, ISO-UTC timestamped audit records, pid annotation
# DEPENDS: hashlib, json, os, uuid, datetime, pathlib

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Canonical repo root — three levels up from pidgin/store/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Hash helpers
# ---------------------------------------------------------------------------

def file_hash(path: str | Path) -> str:
    """Return sha256 hex of file content. Empty string if file missing."""
    p = Path(path)
    if not p.exists():
        return ""
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Audit log path
# ---------------------------------------------------------------------------

def audit_log_path() -> Path:
    """Return /project/local/audit/marionette_actions.jsonl."""
    return _REPO_ROOT / "local" / "audit" / "marionette_actions.jsonl"


# ---------------------------------------------------------------------------
# Audit log append
# ---------------------------------------------------------------------------

def audit_log(record: dict) -> str:
    """Append a JSON line to the audit log. Return the audit record id (uuid4 hex).

    Enriches the caller's record with: id (uuid4 hex), timestamp (ISO UTC),
    pid (os.getpid()). The caller supplies all domain fields (agent, action,
    file, reason, etc.).
    """
    rid = uuid.uuid4().hex
    enriched = {
        "id": rid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        **record,
    }
    log_path = audit_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(enriched) + "\n")
    return rid
