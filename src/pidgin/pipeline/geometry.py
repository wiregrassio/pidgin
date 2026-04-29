#!/usr/bin/env python3
# MODULE: geometry
# DOES: Provide cosine similarity, centroid, spherical variance, and
#       draft-decay convergence verdict helpers for the MLD pipeline.
# EMITS: cosine_similarity, centroid, spherical_variance, convergence_verdict
# READS: nothing
# IMPLEMENTS: geometry math for 256-dim embedding space
# DEPENDS: numpy
# PROVENANCE: tools/mld/pipeline.py _cosine_sim_matrix

import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors. Returns float in [-1, 1]."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def centroid(vectors: list[list[float]]) -> list[float]:
    """Compute the element-wise mean of vectors. Returns list[float]."""
    arr = np.asarray(vectors, dtype=np.float64)
    return arr.mean(axis=0).tolist()


def spherical_variance(vectors: list[list[float]]) -> float:
    """1 - ||mean(unit_vectors)||. 0 = perfect consensus, 1 = scatter."""
    arr = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    unit = arr / norms
    mean_vec = unit.mean(axis=0)
    return float(1.0 - np.linalg.norm(mean_vec))


def convergence_verdict(
    draft_1_vecs: list[list[float]],
    draft_2_vecs: list[list[float]],
    draft_3_vecs: list[list[float]],
) -> tuple[str, dict[str, float]]:
    """Return (verdict, sv_dict) from per-draft spherical variances.

    Computes spherical variance for each draft tier and compares the
    sequence sv1 → sv2 → sv3. Strictly decreasing = CONVERGED (variance
    shrinks as drafts refine). Strictly increasing = DIVERGENT. Anything
    else = AMBIGUOUS. No threshold — the relationship between the three
    values is the test.

    Returns:
      verdict: "CONVERGED" | "DIVERGENT" | "AMBIGUOUS"
      sv_dict: {"sv1": float, "sv2": float, "sv3": float}
    """
    sv1 = spherical_variance(draft_1_vecs)
    sv2 = spherical_variance(draft_2_vecs)
    sv3 = spherical_variance(draft_3_vecs)
    svs = {"sv1": sv1, "sv2": sv2, "sv3": sv3}
    if sv1 > sv2 > sv3:
        return "CONVERGED", svs
    elif sv3 > sv2 > sv1:
        return "DIVERGENT", svs
    else:
        return "AMBIGUOUS", svs
