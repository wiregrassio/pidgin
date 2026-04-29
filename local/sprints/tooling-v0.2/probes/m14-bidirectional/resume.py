#!/usr/bin/env python3
"""M15 resume runner: executes only missing (probe, budget, run_idx) cells.

Reads existing results.json, determines which cells are not yet present,
runs only those, and appends the results. This avoids re-running completed
cells on a partial results.json.

Load order: dotenv override must be called BEFORE importing harness.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv('/Users/elliotwillis/Desktop/fe-toolkit/local/.env', override=True)

_PROJECT_ROOT = Path("/Users/elliotwillis/Desktop/fe-toolkit")
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Import harness via spec (directory name has hyphens, not importable by package path)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "harness",
    str(_PROJECT_ROOT / "local/sprints/tooling-v0.2/probes/m14-bidirectional/harness.py"),
)
harness = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(harness)

RESULTS_JSON = harness.RESULTS_JSON
BUDGETS = harness.BUDGETS
STABILITY_RUNS = harness.STABILITY_RUNS


def main() -> int:
    probes = harness.load_probes()
    if len(probes) != 5:
        raise ValueError(f"Expected 5 probes, got {len(probes)}")

    # Load existing records
    records: list[dict] = []
    if RESULTS_JSON.exists():
        with open(RESULTS_JSON, "r", encoding="utf-8") as f:
            records = json.load(f)

    done: set[tuple] = {
        (r["probe_id"], r["budget"], r["run_idx"]) for r in records
    }
    print(f"[resume] {len(done)} cells already done, {30 - len(done)} remaining",
          file=sys.stderr)

    t0 = time.time()
    for probe in probes:
        for budget in BUDGETS:
            for run_idx in range(STABILITY_RUNS):
                key = (probe["probe_id"], budget, run_idx)
                if key in done:
                    continue
                t_cell = time.time()
                rec = harness.run_one_probe(probe, budget, run_idx)
                rec["wall_seconds"] = round(time.time() - t_cell, 2)
                records.append(rec)
                done.add(key)
                # Incremental flush
                with open(RESULTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                print(
                    f"[m14] {rec['probe_id']} budget={budget} run={run_idx} "
                    f"converged={rec['converged']} cluster={rec['cluster_size']}/{harness.N_CANDIDATES} "
                    f"syn_valid={rec['syntactically_valid_count']}/{harness.N_CANDIDATES} "
                    f"({rec['wall_seconds']}s)",
                    file=sys.stderr,
                )

    elapsed = round(time.time() - t0, 2)
    print(f"[resume] {len(records)} total records in {RESULTS_JSON} ({elapsed}s)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
