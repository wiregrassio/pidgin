#!/usr/bin/env python3
# pidgin v0.2 — NEW. Implements adaptive-candidates.md expansion policy.
# Tracks convergence ratios (not just converged/not) for empirical M14/M15 data.
#
# MODULE: candidates
# DOES: Adaptive candidate generation with expansion policy — generate an initial
#       batch, evaluate cluster convergence, optionally expand, and audit ratios.
# EMITS: ExpansionConfig, CandidateEvaluation, evaluate_with_expansion
# READS: nothing
# IMPLEMENTS: adaptive-candidates.md expansion policy with JSONL convergence audit
# DEPENDS: dataclasses, datetime, json, os, pathlib, typing

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class ExpansionConfig:
    """Thresholds and call counts for the adaptive expansion policy.

    Invariants enforced at construction:
      - expand_ratio must be in (0, accept_ratio]
      - expanded_accept_ratio must be in (0, 1]
      - initial_n_calls and expansion_n_calls must each be >= 1
    """
    accept_ratio: float = 0.8
    expand_ratio: float = 0.6
    expanded_accept_ratio: float = 0.7
    initial_n_calls: int = 5
    expansion_n_calls: int = 5
    drafts_per_call: int = 3

    def __post_init__(self):
        if not (0.0 < self.expand_ratio <= self.accept_ratio <= 1.0):
            raise ValueError("expand_ratio must be in (0, accept_ratio]")
        if not (0.0 < self.expanded_accept_ratio <= 1.0):
            raise ValueError("expanded_accept_ratio must be in (0, 1]")
        if self.initial_n_calls < 1 or self.expansion_n_calls < 1:
            raise ValueError("call counts must be >= 1")


@dataclass(frozen=True)
class CandidateEvaluation:
    """Result of one adaptive-expansion evaluation for a function.

    Fields:
      function_name      -- identifier passed to evaluate_with_expansion
      initial_ratio      -- cluster_size / n_initial (first generation pass)
      expanded           -- True if expansion generation was triggered
      expanded_ratio     -- cluster_size / n_total after expansion, or None
      converged          -- True if the evaluation passed an acceptance threshold
      n_candidates_total -- total number of candidate strings generated
      cluster_size       -- dominant-cluster size at decision point
      candidates         -- all candidate strings (initial, or combined if expanded)
      vectors            -- all embedding vectors (initial, or combined if expanded)
    """
    function_name: str
    initial_ratio: float
    expanded: bool
    expanded_ratio: float | None
    converged: bool
    n_candidates_total: int
    cluster_size: int
    candidates: list[str]
    vectors: list


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def evaluate_with_expansion(
    function_name: str,
    *,
    generate_fn: Callable[[int], tuple[list[str], list]],
    cluster_fn: Callable[[list], int],
    config: "ExpansionConfig | None" = None,
    audit_path: str = "/Users/elliotwillis/Desktop/fe-toolkit/.pidgin/audit/convergence.jsonl",
) -> CandidateEvaluation:
    """Run adaptive candidate generation with optional expansion for one function.

    Behaviour:
      1. Generate an initial batch via generate_fn(config.initial_n_calls).
      2. Compute initial_ratio = cluster_fn(vecs) / len(cands).
      3. Branch on initial_ratio:
           >= accept_ratio          → converged immediately, no expansion
           >= expand_ratio          → expand: generate a second batch and re-cluster
           < expand_ratio           → non-convergent, no expansion
      4. Append a JSONL audit entry to audit_path (creating directories as needed).
      5. Return a CandidateEvaluation.

    The n argument to generate_fn is the n_calls count (not the total candidates).
    cluster_fn receives ALL vectors (initial, or combined after expansion) and
    must return an integer cluster_size.
    """
    if config is None:
        config = ExpansionConfig()

    # -- Phase 1: initial generation -----------------------------------------
    cands_initial, vecs_initial = generate_fn(config.initial_n_calls)
    n_initial = len(cands_initial)
    cluster_initial = cluster_fn(vecs_initial)
    ratio_initial = cluster_initial / n_initial

    # -- Phase 2: branch on ratio --------------------------------------------
    if ratio_initial >= config.accept_ratio:
        # Accept immediately — no expansion needed
        result = CandidateEvaluation(
            function_name=function_name,
            initial_ratio=ratio_initial,
            expanded=False,
            expanded_ratio=None,
            converged=True,
            n_candidates_total=n_initial,
            cluster_size=cluster_initial,
            candidates=cands_initial,
            vectors=vecs_initial,
        )

    elif ratio_initial >= config.expand_ratio:
        # Borderline — expand with a second generation pass
        cands_extra, vecs_extra = generate_fn(config.expansion_n_calls)
        cands_combined = cands_initial + cands_extra
        vecs_combined = vecs_initial + vecs_extra
        n_total = len(cands_combined)
        cluster_expanded = cluster_fn(vecs_combined)
        ratio_expanded = cluster_expanded / n_total
        converged = ratio_expanded >= config.expanded_accept_ratio

        result = CandidateEvaluation(
            function_name=function_name,
            initial_ratio=ratio_initial,
            expanded=True,
            expanded_ratio=ratio_expanded,
            converged=converged,
            n_candidates_total=n_total,
            cluster_size=cluster_expanded,
            candidates=cands_combined,
            vectors=vecs_combined,
        )

    else:
        # Below expand threshold — non-convergent, do not expand
        result = CandidateEvaluation(
            function_name=function_name,
            initial_ratio=ratio_initial,
            expanded=False,
            expanded_ratio=None,
            converged=False,
            n_candidates_total=n_initial,
            cluster_size=cluster_initial,
            candidates=cands_initial,
            vectors=vecs_initial,
        )

    # -- Phase 3: audit log --------------------------------------------------
    _append_audit(result, audit_path)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _append_audit(result: CandidateEvaluation, audit_path: str) -> None:
    """Append one JSONL convergence entry to audit_path, creating dirs as needed."""
    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "function": result.function_name,
        "initial_ratio": round(result.initial_ratio, 4),
        "expanded": result.expanded,
        "expanded_ratio": round(result.expanded_ratio, 4) if result.expanded_ratio is not None else None,
        "converged": result.converged,
        "cluster_size": result.cluster_size,
        "n_candidates_total": result.n_candidates_total,
    }

    with open(audit_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
