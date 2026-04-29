"""SFT / DPO / gate-SFT data emitter. Append-only JSONL."""

import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

SFT_FILENAME = "training-data.jsonl"


@dataclass
class SFTRecord:
    """Schema (versioned).
    type='sft':  {prompt, completion, label='positive|negative'}
    type='gate': {prompt, label='valid|invalid', reason}
    """
    version: int = 1
    type: str = "sft"           # "sft" | "gate"
    timestamp: str = ""         # ISO-8601 UTC
    prompt: str = ""
    completion: str = ""        # for sft only
    label: str = ""             # "positive"/"negative" or "valid"/"invalid"
    reason: str = ""            # for gate only
    function_id: str = ""       # provenance: which indexed function
    centroid_distance: float | None = None  # for sft-negative


def append(repo_root: str, records: list[SFTRecord]) -> str:
    out = Path(repo_root) / ".pidgin" / SFT_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        for r in records:
            r.timestamp = r.timestamp or datetime.now(timezone.utc).isoformat()
            f.write(json.dumps(asdict(r)))
            f.write("\n")
    return str(out)


def count(repo_root: str) -> int:
    p = Path(repo_root) / ".pidgin" / SFT_FILENAME
    if not p.exists():
        return 0
    return sum(1 for _ in p.open("r"))
