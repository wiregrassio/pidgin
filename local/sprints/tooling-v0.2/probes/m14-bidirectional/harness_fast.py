#!/usr/bin/env python3
"""Optimized M15 harness: one generation batch + one embedding batch for all 30 cells."""
import ast, json, sys, time
from pathlib import Path

_PROJECT_ROOT = Path("/Users/elliotwillis/Desktop/fe-toolkit")
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(str(_PROJECT_ROOT / "local" / ".env"), override=True)

HARNESS_DIR = Path(__file__).resolve().parent
PROBES_JSON = HARNESS_DIR / "probes.json"
EXPAND_XML = _PROJECT_ROOT / "pidgin" / "prompts" / "expand.xml"
RESULTS_JSON = HARNESS_DIR / "results.json"

N_CANDIDATES = 10
BUDGETS = (50, 200)
STABILITY_RUNS = 3
CONVERGENCE_THRESHOLD = 6
GEN_MODEL = "gpt-4.1-nano"


def is_syntactically_valid(source: str) -> bool:
    if not source or not source.strip():
        return False
    text = source.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
        text = "\n".join(lines)
    try:
        ast.parse(text)
        return True
    except Exception:
        return False


def main():
    from pidgin.prompts.templates import assemble_xml_prompt
    from pidgin.pipeline.batch import (
        GenerationRequest, EmbeddingRequest,
        run_batch_generation, run_batch_embedding,
    )
    from pidgin.pipeline.geometry import antipode_test

    probes = json.loads(PROBES_JSON.read_text())
    print(f"[harness_fast] {len(probes)} probes, {len(BUDGETS)} budgets, "
          f"{STABILITY_RUNS} runs = {len(probes)*len(BUDGETS)*STABILITY_RUNS} cells")

    # Build cell manifest
    cells = [(p, b, r) for p in probes for b in BUDGETS for r in range(STABILITY_RUNS)]

    # Assemble all prompts
    assembled = assemble_xml_prompt(str(EXPAND_XML), {
        "description": "PLACEHOLDER_DESC",
        "function_signature": "PLACEHOLDER_SIG",
    })
    # We'll assemble per-probe since description/signature differ per probe
    probe_assembled = {}
    for probe in probes:
        asm = assemble_xml_prompt(str(EXPAND_XML), {
            "description": probe["description"],
            "function_signature": probe["function_signature"],
        })
        probe_assembled[probe["probe_id"]] = asm

    # --- ROUND 1: All generation requests in one batch ---
    t0 = time.time()
    all_gen_requests = []
    cell_to_req_ids = {}  # (probe_id, budget, run_idx) -> [custom_id, ...]
    for probe, budget, run_idx in cells:
        pid = probe["probe_id"]
        asm = probe_assembled[pid]
        req_ids = []
        for ci in range(N_CANDIDATES):
            cid = f"gen:{pid}:b{budget}:r{run_idx}:c{ci}"
            all_gen_requests.append(GenerationRequest(
                custom_id=cid,
                cached_preamble=asm.cached_preamble,
                payload=asm.payload,
                model=GEN_MODEL,
                max_tokens=budget,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "expansion",
                        "schema": {
                            "type": "object",
                            "properties": {"implementation": {"type": "string"}},
                            "required": ["implementation"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                },
            ))
            req_ids.append(cid)
        cell_to_req_ids[(pid, budget, run_idx)] = req_ids

    print(f"[harness_fast] Dispatching {len(all_gen_requests)} generation requests via batch...")
    gen_results = run_batch_generation(all_gen_requests)
    gen_by_id = {r.custom_id: r for r in gen_results}
    t_gen = time.time() - t0
    print(f"[harness_fast] Generation batch done in {t_gen:.1f}s")

    # Extract candidates per cell
    def extract_impl(gen_result) -> str:
        if gen_result is None or gen_result.error:
            return ""
        if gen_result.drafts:
            d = gen_result.drafts[0]
            if isinstance(d, dict) and "implementation" in d:
                return d["implementation"]
            if isinstance(d, str):
                return d
        try:
            content = gen_result.raw_response.get("response", {}).get("body", {})
            msg = content.get("choices", [{}])[0].get("message", {})
            txt = msg.get("content") or ""
            if txt:
                parsed = json.loads(txt)
                if isinstance(parsed, dict) and "implementation" in parsed:
                    return parsed["implementation"]
        except Exception:
            pass
        return ""

    cell_candidates = {}
    for (pid, budget, run_idx), req_ids in cell_to_req_ids.items():
        candidates = [extract_impl(gen_by_id.get(rid)) for rid in req_ids]
        while len(candidates) < N_CANDIDATES:
            candidates.append("")
        cell_candidates[(pid, budget, run_idx)] = candidates[:N_CANDIDATES]

    # --- ROUND 2: All embedding requests in one batch ---
    t1 = time.time()
    all_emb_requests = []
    cell_emb_map = {}  # (pid, budget, run_idx) -> [(cand_idx, custom_id), ...]
    for (pid, budget, run_idx), candidates in cell_candidates.items():
        emb_pairs = []
        for ci, c in enumerate(candidates):
            if c.strip():
                eid = f"emb:{pid}:b{budget}:r{run_idx}:c{ci}"
                all_emb_requests.append(EmbeddingRequest(custom_id=eid, text=c))
                emb_pairs.append((ci, eid))
        cell_emb_map[(pid, budget, run_idx)] = emb_pairs

    print(f"[harness_fast] Dispatching {len(all_emb_requests)} embedding requests via batch...")
    emb_results = run_batch_embedding(all_emb_requests)
    emb_by_id = {r.custom_id: r for r in emb_results}
    t_emb = time.time() - t1
    print(f"[harness_fast] Embedding batch done in {t_emb:.1f}s")

    # --- Compute clusters and build records ---
    records = []
    for probe, budget, run_idx in cells:
        pid = probe["probe_id"]
        candidates = cell_candidates[(pid, budget, run_idx)]
        emb_pairs = cell_emb_map[(pid, budget, run_idx)]

        vectors = [None] * N_CANDIDATES
        for ci, eid in emb_pairs:
            er = emb_by_id.get(eid)
            if er and er.error is None and er.vector is not None:
                vectors[ci] = er.vector

        syntactically_valid = [is_syntactically_valid(c) for c in candidates]
        syn_valid_count = sum(syntactically_valid)

        valid_vectors = [v for v in vectors if v is not None]
        if valid_vectors:
            cluster_size, cluster_indices = antipode_test(valid_vectors)
        else:
            cluster_size, cluster_indices = 0, []

        converged = cluster_size >= CONVERGENCE_THRESHOLD

        winning_candidate = ""
        if cluster_indices:
            valid_cand_indices = [i for i, v in enumerate(vectors) if v is not None]
            if cluster_indices[0] < len(valid_cand_indices):
                winning_candidate = candidates[valid_cand_indices[cluster_indices[0]]]

        rec = {
            "probe_id": pid,
            "budget": budget,
            "run_idx": run_idx,
            "candidates": candidates,
            "vectors": vectors,
            "cluster_size": cluster_size,
            "converged": converged,
            "syntactically_valid_count": syn_valid_count,
            "winning_candidate": winning_candidate,
            "semantic_eq_to_reference": None,
            "wall_seconds": round(t_gen + t_emb, 2),
        }
        records.append(rec)
        print(f"  {pid} b={budget} r={run_idx}: cluster={cluster_size}/{N_CANDIDATES} "
              f"syn={syn_valid_count}/{N_CANDIDATES} converged={converged}")

    RESULTS_JSON.write_text(json.dumps(records, indent=2))
    total = round(time.time() - t0, 2)
    print(f"\n[harness_fast] {len(records)} records written to {RESULTS_JSON} in {total:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
