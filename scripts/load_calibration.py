#!/usr/bin/env python3
"""
Load calibration winners into a Pidgin nest.

Reads calibration-data.json + calibration-vectors.npz, applies the
empirically-derived convergence test (t=0.3, draft_1, sv < 0.10),
picks the centroid-nearest candidate as the MLD, and upserts directly
into ChromaDB. Zero API calls.

Run from the pidgin repo root:
    python3 scripts/load_calibration.py
"""

import json
import sys
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_FILE = REPO_ROOT / "calibration-data.json"
VECTORS_FILE = REPO_ROOT / "calibration-vectors.npz"
CONVERGENCE_THRESHOLD = 0.10
TEMP = 0.3
DRAFT = 1


def spherical_variance(vectors):
    arr = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    unit = arr / norms
    mean_vec = unit.mean(axis=0)
    return float(1.0 - np.linalg.norm(mean_vec))


def centroid_nearest(vectors, texts):
    arr = np.asarray(vectors, dtype=np.float64)
    cent = arr.mean(axis=0)
    cent_norm = np.linalg.norm(cent)
    if cent_norm == 0:
        return 0, texts[0], vectors[0]
    sims = arr @ cent / (np.linalg.norm(arr, axis=1) * cent_norm)
    best = int(np.argmax(sims))
    return best, texts[best], vectors[best]


def load_data():
    print("Loading calibration data...")
    with open(DATA_FILE) as f:
        data = json.load(f)

    npz = np.load(VECTORS_FILE)
    vectors = npz["vectors"]
    index = npz["index"]

    vec_lookup = {}
    for i, (fi, ci) in enumerate(index):
        vec_lookup[(int(fi), int(ci))] = vectors[i]

    for rec in data:
        fi = rec["fi"]
        for ci, cand in enumerate(rec["candidates"]):
            key = (fi, ci)
            if key in vec_lookup:
                cand["_vector"] = vec_lookup[key].tolist()
            else:
                cand["_vector"] = None

    return data


def select_winners(data):
    winners = []
    ambiguous = []
    divergent = []

    for rec in data:
        name = rec["name"]
        file_path = rec.get("file", "")
        body_len = rec.get("body_len", 0)

        candidates = [
            c for c in rec["candidates"]
            if c["temp"] == TEMP and c["draft"] == DRAFT and c["_vector"] is not None
        ]

        if len(candidates) < 3:
            print(f"  SKIP {name}: only {len(candidates)} candidates")
            continue

        vecs = [c["_vector"] for c in candidates]
        texts = [c["text"] for c in candidates]
        sv = spherical_variance(vecs)

        idx, mld_text, mld_vec = centroid_nearest(vecs, texts)
        entry = {
            "name": name,
            "file": file_path,
            "body_len": body_len,
            "description": mld_text,
            "vector": mld_vec,
            "sv": sv,
            "n_candidates": len(candidates),
        }

        if sv < CONVERGENCE_THRESHOLD:
            winners.append(entry)
        elif sv < 0.15:
            ambiguous.append(entry)
        else:
            divergent.append(entry)

    return winners, ambiguous, divergent


def upsert_to_nest(winners, ambiguous, divergent):
    import chromadb

    nest_dir = REPO_ROOT / ".pidgin" / "nest"
    nest_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(nest_dir))
    collection = client.get_or_create_collection(
        name="function_descriptions",
        metadata={"hnsw:space": "cosine"},
    )

    all_results = (
        [(w, "CONVERGED") for w in winners]
        + [(a, "AMBIGUOUS") for a in ambiguous]
        + [(d, "DIVERGENT") for d in divergent]
    )

    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for item, verdict in all_results:
        doc_id = f"{item['file']}::{item['name']}"
        ids.append(doc_id)
        embeddings.append(item["vector"])
        documents.append(item["description"])
        metadatas.append({
            "name": item["name"],
            "file": item["file"],
            "body_len": item["body_len"],
            "sv": round(item["sv"], 6),
            "n_candidates": item["n_candidates"],
            "convergence": verdict,
            "source": "calibration-v0.4.1",
            "temp": TEMP,
            "draft": DRAFT,
        })

    batch_size = 500
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i + batch_size],
            embeddings=embeddings[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )

    return len(ids)


def main():
    data = load_data()
    print(f"Loaded {len(data)} functions\n")

    winners, ambiguous, divergent = select_winners(data)

    print(f"\nResults (t={TEMP}, draft_{DRAFT}, threshold={CONVERGENCE_THRESHOLD}):")
    print(f"  CONVERGED:  {len(winners)}")
    print(f"  AMBIGUOUS:  {len(ambiguous)} (sv {CONVERGENCE_THRESHOLD}-0.15)")
    print(f"  DIVERGENT:  {len(divergent)} (sv > 0.15)")
    print(f"  Total:      {len(winners) + len(ambiguous) + len(divergent)}")

    print(f"\nConverged examples:")
    for w in winners[:10]:
        print(f"  {w['sv']:.4f} {w['name']:<45} {w['description'][:70]}")
    if len(winners) > 10:
        print(f"  ... and {len(winners) - 10} more")

    print(f"\nDivergent (likely complex/multi-purpose):")
    for d in divergent:
        print(f"  {d['sv']:.4f} {d['name']:<45} {d['description'][:70]}")

    print(f"\nUpserting all {len(winners) + len(ambiguous) + len(divergent)} into nest...")
    n = upsert_to_nest(winners, ambiguous, divergent)
    print(f"Done. {n} entries in .pidgin/nest/")
    print(f"\nTest with: pidgin query 'compute spherical variance'")


if __name__ == "__main__":
    main()
