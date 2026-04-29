#!/usr/bin/env python3
# MODULE: harness (M14 bidirectional MLD probe)
# DOES: Drive the description -> code expansion pipeline for 5 probes,
#       N=10 candidates, budgets=(50,200), 3 stability runs each.
#       Importable without API calls; main() executes the live pipeline.
# EMITS: results.json (30 records: 5 probes x 2 budgets x 3 stability runs)
# READS: probes.json, /project/pidgin/prompts/expand.xml
# IMPLEMENTS: run_one_probe (description -> 10 implementation candidates ->
#             embedding -> antipode_test cluster), syntactic validity check
# DEPENDS: pidgin.pipeline.batch (run_batch_generation, run_batch_embedding,
#          GenerationRequest, EmbeddingRequest), pidgin.pipeline.geometry
#          (antipode_test), pidgin.prompts.templates (assemble_xml_prompt)

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path
from typing import Any

# Path so this script can be run directly OR imported for tests.
_PROJECT_ROOT = Path("/Users/elliotwillis/Desktop/fe-toolkit")
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Locations
HARNESS_DIR = Path(__file__).resolve().parent
PROBES_JSON = HARNESS_DIR / "probes.json"
EXPAND_XML = _PROJECT_ROOT / "pidgin" / "prompts" / "expand.xml"
RESULTS_JSON = HARNESS_DIR / "results.json"

# Pipeline constants for M14
N_CANDIDATES = 10           # PD: candidates per probe per run
BUDGETS = (50, 200)         # max_tokens budget extremes
STABILITY_RUNS = 3          # repeat each (probe, budget) cell 3x
CONVERGENCE_THRESHOLD = 6   # cluster_size >= 6 of 10 == converged
GEN_MODEL = "gpt-4.1-nano"  # same as M3/M9 generation path


# ---------------------------------------------------------------------------
# Pure helpers (no API calls)
# ---------------------------------------------------------------------------

def load_probes() -> list[dict]:
    """Load probes.json. No API calls. Used at import-time-safe entry points."""
    with open(PROBES_JSON, "r", encoding="utf-8") as f:
        probes = json.load(f)
    if not isinstance(probes, list):
        raise ValueError(f"probes.json must be a list, got {type(probes)}")
    return probes


def build_expand_template() -> str:
    """Return the absolute path to expand.xml. No I/O at import."""
    return str(EXPAND_XML)


def is_syntactically_valid_python(source: str) -> bool:
    """Return True if source parses with ast.parse. False on any SyntaxError."""
    if not source or not source.strip():
        return False
    text = source.strip()
    # Strip ```python fences if the model emitted them despite rule 5.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# One-probe driver (live API call path; only invoked from main())
# ---------------------------------------------------------------------------

def run_one_probe(probe: dict, budget: int, run_idx: int) -> dict:
    """Run one (probe, budget, run_idx) cell.

    Generates N_CANDIDATES implementations via batch generation against
    expand.xml, embeds the candidates with the store-config embedder, runs
    antipode_test, and returns a record dict.

    NETWORK CALLS: this function dispatches OpenAI Batch API jobs and is
    only safe to invoke from main() or M15.
    """
    # Imports kept inside the function body so `import harness` does no work.
    from pidgin.prompts.templates import assemble_xml_prompt
    from pidgin.pipeline.batch import (
        GenerationRequest,
        EmbeddingRequest,
        run_batch_generation,
        run_batch_embedding,
    )
    from pidgin.pipeline.geometry import antipode_test

    probe_id = probe["probe_id"]
    description = probe["description"]
    function_signature = probe["function_signature"]

    # ---- 1. Assemble expand.xml prompt --------------------------------------
    assembled = assemble_xml_prompt(
        build_expand_template(),
        {
            "description": description,
            "function_signature": function_signature,
        },
    )
    preamble = assembled.cached_preamble
    payload = assembled.payload

    # ---- 2. Build N_CANDIDATES generation requests --------------------------
    gen_requests: list[GenerationRequest] = []
    for ci in range(N_CANDIDATES):
        cid = f"expand:{probe_id}:b={budget}:run={run_idx}:c={ci}"
        gen_requests.append(GenerationRequest(
            custom_id=cid,
            cached_preamble=preamble,
            payload=payload,
            model=GEN_MODEL,
            max_tokens=budget,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "expansion",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "implementation": {"type": "string"},
                        },
                        "required": ["implementation"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        ))

    # ---- 3. Dispatch generation via batch ----------------------------------
    gen_results = run_batch_generation(gen_requests)

    # parse_batch_results uses the four-shape draft fallback; for the expand
    # schema the structured object is {"implementation": "..."} so the draft
    # extraction lands the implementation in drafts[0]. Take it directly.
    candidates: list[str] = []
    for r in gen_results:
        impl = ""
        if r.error is None and r.drafts:
            impl = r.drafts[0]
        # Also try raw_response.parsed in case batch.py emits it that way.
        if not impl:
            try:
                content = r.raw_response.get("response", {}).get("body", {})
                msg = content.get("choices", [{}])[0].get("message", {})
                txt = msg.get("content") or ""
                if txt:
                    parsed = json.loads(txt)
                    if isinstance(parsed, dict) and "implementation" in parsed:
                        impl = parsed["implementation"]
            except Exception:
                pass
        candidates.append(impl or "")

    # Pad/truncate to exactly N_CANDIDATES (defensive).
    while len(candidates) < N_CANDIDATES:
        candidates.append("")
    candidates = candidates[:N_CANDIDATES]

    # ---- 4. Syntactic validity count ---------------------------------------
    syntactically_valid = [is_syntactically_valid_python(c) for c in candidates]
    syn_valid_count = sum(1 for v in syntactically_valid if v)

    # ---- 5. Embed candidates (skip empties — antipode_test ignores them) ---
    emb_requests: list[EmbeddingRequest] = []
    emb_index_map: list[int] = []  # parallel index into candidates
    for ci, c in enumerate(candidates):
        if not c.strip():
            continue
        emb_requests.append(EmbeddingRequest(
            custom_id=f"emb:{probe_id}:b={budget}:run={run_idx}:c={ci}",
            text=c,
        ))
        emb_index_map.append(ci)

    vectors: list[list[float] | None] = [None] * N_CANDIDATES
    if emb_requests:
        emb_results = run_batch_embedding(emb_requests)
        for emb_res, ci in zip(emb_results, emb_index_map):
            if emb_res.error is None and emb_res.vector is not None:
                vectors[ci] = emb_res.vector

    valid_vectors: list[list[float]] = [v for v in vectors if v is not None]
    if valid_vectors:
        cluster_size, cluster_indices = antipode_test(valid_vectors)
    else:
        cluster_size, cluster_indices = 0, []

    converged = cluster_size >= CONVERGENCE_THRESHOLD

    # ---- 6. Pick winning candidate (largest cluster centroid neighbor) -----
    winning_candidate = ""
    if cluster_indices:
        # Map cluster_indices (in valid_vectors space) back to original
        # candidate index, then pick the first one.
        valid_cand_indices = [i for i, v in enumerate(vectors) if v is not None]
        first_cluster = valid_cand_indices[cluster_indices[0]]
        winning_candidate = candidates[first_cluster]

    return {
        "probe_id": probe_id,
        "budget": budget,
        "run_idx": run_idx,
        "candidates": candidates,
        "vectors": vectors,
        "cluster_size": cluster_size,
        "converged": converged,
        "syntactically_valid_count": syn_valid_count,
        "winning_candidate": winning_candidate,
    }


# ---------------------------------------------------------------------------
# Top-level main (M15 will call this; M14 does NOT execute it)
# ---------------------------------------------------------------------------

def main() -> int:
    """Loop 5 probes x 2 budgets x 3 stability runs = 30 records.

    Writes results to results.json.  Network-bound: only run from M15.
    """
    probes = load_probes()
    if len(probes) != 5:
        raise ValueError(f"Expected 5 probes, got {len(probes)}")

    records: list[dict] = []
    t0 = time.time()
    for probe in probes:
        for budget in BUDGETS:
            for run_idx in range(STABILITY_RUNS):
                t_cell = time.time()
                rec = run_one_probe(probe, budget, run_idx)
                rec["wall_seconds"] = round(time.time() - t_cell, 2)
                records.append(rec)
                # Incremental flush so a mid-run crash preserves progress.
                with open(RESULTS_JSON, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2)
                print(
                    f"[m14] {rec['probe_id']} budget={budget} run={run_idx} "
                    f"converged={rec['converged']} cluster={rec['cluster_size']}/{N_CANDIDATES} "
                    f"syn_valid={rec['syntactically_valid_count']}/{N_CANDIDATES} "
                    f"({rec['wall_seconds']}s)",
                    file=sys.stderr,
                )

    elapsed = round(time.time() - t0, 2)
    print(f"[m14] {len(records)} records written to {RESULTS_JSON} in {elapsed}s",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
