#!/usr/bin/env python3
# MODULE: geometry
# DOES: Provide cosine similarity, centroid, spherical variance, and
#       single-number convergence test helpers for the MLD pipeline.
# EMITS: cosine_similarity, centroid, spherical_variance, is_converged
# READS: nothing
# IMPLEMENTS: geometry math for 256-dim embedding space
# DEPENDS: numpy
# PROVENANCE: tools/mld/pipeline.py _cosine_sim_matrix

import numpy as np

CONVERGENCE_THRESHOLD = 0.10


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


def is_converged(
    vectors: list[list[float]],
    threshold: float = CONVERGENCE_THRESHOLD,
) -> tuple[bool, float]:
    """Single-number convergence test. Returns (converged, sv)."""
    sv = spherical_variance(vectors)
    return sv < threshold, sv
