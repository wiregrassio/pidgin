#!/usr/bin/env python3
# pidgin v0.2 — extracted from tools/mld/pipeline.py (v0.1).
# Behaviour change vs v0.1: `dispatch` parameter added; auto-threshold
# selects sync (n<10) or batch (n>=10). The convergence math is
# unchanged — sync and batch paths produce identical downstream shape.

# MODULE: mld
# DOES: V2 minimum lossless description — soft budgets, three-draft generation,
#       LLM gate, Opus selection. Dispatch parameter routes to sync or batch path.
# EMITS: MLDResult (description, target_n, natural_length, confidence, gate_verdict,
#        selection_rationale, cost)
# READS: input text, prompt, target_n, n_calls, model selections, dispatch mode
# IMPLEMENTS: parallel three-draft generation → mechanical pre-filter →
#             degeneracy checks → spherical variance convergence → gate → selection
# DEPENDS: tools.utils.api, pidgin.pipeline.batch, numpy, asyncio

import asyncio
import json as _json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

import numpy as np

from pidgin.utils import api
from pidgin.utils.api import CostSummary, GenerateResult
from pidgin.pipeline.batch import (
    GenerationRequest,
    should_use_batch,
    run_batch_generation,
)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass
class MLDResult:
    """The chosen description for an input plus pipeline-stage metadata."""
    description: str            # the chosen description
    target_n: int               # the concision target it was generated against
    natural_length: int         # word-split length of the chosen description
    confidence: float           # 0.0–1.0
    converged: bool
    candidates_generated: int   # = num_calls * 3 (drafts)
    candidates_filtered: int    # rejected by mechanical pre-filter
    gate_verdict: str           # "valid" | "invalid" | "ambiguous"
    gate_reason: str
    selection_rationale: str    # from Opus if invoked, else gate reason
    targets_tried: list[int] = field(default_factory=list)
    degenerate_pre_check: bool = False  # True if avg_cosine_sim>0.999 fired
    deduped: bool = False                # True if textual dedup was applied
    cost: CostSummary = field(default_factory=CostSummary)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_THREE_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_1": {"type": "string"},
        "draft_2": {"type": "string"},
        "draft_3": {"type": "string"},
    },
    "required": ["draft_1", "draft_2", "draft_3"],
    "additionalProperties": False,
}

_GATE_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["valid", "reason"],
    "additionalProperties": False,
}

_SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_index": {"type": "integer"},
        "rationale": {"type": "string"},
    },
    "required": ["selected_index", "rationale"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Built-in prompts
# ---------------------------------------------------------------------------

_GATE_PROMPT = (
    "You are a description gate. Given a function (or text) and a "
    "candidate description, decide whether the description fully "
    "captures the function's behavior. A valid description: starts "
    "with an imperative verb, names what the function DOES, omits "
    "no critical side-effect, contains no truncation artifact "
    "(trailing comma, mid-word fragment, dangling conjunction). "
    "Respond as the schema specifies."
)

_SELECT_PROMPT = (
    "You are a description selector. Given a function and a list of "
    "candidate descriptions (each tagged with its draft tier and "
    "centroid distance), choose the index of the best one. Prefer "
    "shorter when meaning is preserved. Respond as the schema "
    "specifies."
)


# ---------------------------------------------------------------------------
# Mechanical pre-filter — non-empty, no control chars, imperative-start
# ---------------------------------------------------------------------------

_NON_IMPERATIVE_LEADS = {
    "the", "a", "an", "this", "that", "these", "those",
    "it", "they", "you", "we", "i",
    "is", "was", "are", "were", "be", "been", "being",
    "has", "have", "had",
    "may", "might", "could",
}


def _has_bad_control_chars(s: str) -> bool:
    """Return True if s contains a control character < 0x20 other than newline/tab."""
    for ch in s:
        if ord(ch) < 0x20 and ch not in ("\n", "\t"):
            return True
    return False


def _pre_filter(candidates: list[str]) -> tuple[list[str], list[str]]:
    """Return (passing, rejected) per the V2 mechanical pre-filter.

    Rules:
      - non-empty after strip
      - no control characters < 0x20 except newline/tab
      - first whitespace-delimited token is not in _NON_IMPERATIVE_LEADS
    """
    passing: list[str] = []
    rejected: list[str] = []
    for raw in candidates:
        if raw is None:
            rejected.append("")
            continue
        text = raw.strip()
        if not text:
            rejected.append(raw)
            continue
        if _has_bad_control_chars(text):
            rejected.append(raw)
            continue
        first_token = text.split(None, 1)[0]
        first_clean = re.sub(r"[^A-Za-z']", "", first_token).lower()
        if not first_clean:
            rejected.append(raw)
            continue
        if first_clean in _NON_IMPERATIVE_LEADS:
            rejected.append(raw)
            continue
        passing.append(raw)
    return passing, rejected


# ---------------------------------------------------------------------------
# Generation helper — single call returning three drafts
# ---------------------------------------------------------------------------

async def _three_draft_call(
    prompt: str,
    content: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict | None:
    """Issue one generation call. Returns the structured dict or None on failure."""
    try:
        result = await api.generate(
            prompt=prompt,
            content=content,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            schema=_THREE_DRAFT_SCHEMA,
            n=1,
        )
    except Exception:
        return None
    if isinstance(result, list):
        result = result[0] if result else None
    if result is None:
        return None
    return result.structured


def _drafts_from_calls(
    call_results: list[dict | None],
) -> tuple[list[tuple[str, str, int]], int]:
    """Flatten call results into [(text, tier, call_idx), ...] and a failure count.

    Each successful call contributes three triples (d1, d2, d3). Failed calls
    contribute zero triples and increment the failure count.
    """
    triples: list[tuple[str, str, int]] = []
    failures = 0
    for call_idx, result in enumerate(call_results):
        if not isinstance(result, dict):
            failures += 1
            continue
        for tier_label in ("d1", "d2", "d3"):
            key = "draft_" + tier_label[1]
            value = result.get(key)
            if isinstance(value, str):
                triples.append((value, tier_label, call_idx))
            else:
                failures += 1
    return triples, failures


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def _cosine_sim_matrix(cloud: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity for an (N, D) matrix; safe against zero vectors."""
    norms = np.linalg.norm(cloud, axis=1)
    safe = np.where(norms == 0, 1.0, norms)
    unit = cloud / safe[:, None]
    return unit @ unit.T


def _avg_offdiag(sim: np.ndarray) -> float:
    """Average of off-diagonal entries in a square similarity matrix."""
    n = sim.shape[0]
    if n < 2:
        return 0.0
    total = sim.sum() - np.trace(sim)
    return float(total / (n * (n - 1)))


def _pick_alternatives(
    cloud: np.ndarray,
    triples: list[tuple[str, str, int]],
    nearest_idx: int,
    target_n: int,
) -> list[int]:
    """Pick up to 4 alternative indices on distinct axes.

    Axes:
      - median word-length (excluding nearest)
      - shortest candidate with length > target_n/2
      - highest mean cosine similarity to neighbors
      - closest-to-centroid from a draft tier different from nearest's
    """
    n = len(triples)
    if n <= 1:
        return []
    seen: set[int] = {nearest_idx}
    picks: list[int] = []

    # Median word-length axis.
    lengths = [
        (i, len(triples[i][0].split()))
        for i in range(n)
        if i not in seen
    ]
    if lengths:
        lengths_sorted = sorted(lengths, key=lambda t: t[1])
        median_idx = lengths_sorted[len(lengths_sorted) // 2][0]
        picks.append(median_idx)
        seen.add(median_idx)

    # Shortest above target_n / 2 axis.
    half = max(1, target_n // 2)
    shorts = [
        (i, len(triples[i][0].split()))
        for i in range(n)
        if i not in seen and len(triples[i][0].split()) > half
    ]
    if shorts:
        short_idx = min(shorts, key=lambda t: t[1])[0]
        picks.append(short_idx)
        seen.add(short_idx)

    # Highest mean cosine similarity axis.
    if cloud.shape[0] >= 2:
        sim = _cosine_sim_matrix(cloud)
        np.fill_diagonal(sim, 0.0)
        mean_sim = sim.mean(axis=1)
        masked = mean_sim.copy()
        for i in seen:
            masked[i] = -np.inf
        if np.any(np.isfinite(masked)):
            best = int(np.argmax(masked))
            if best not in seen and np.isfinite(masked[best]):
                picks.append(best)
                seen.add(best)

    # Closest-to-centroid from a different draft tier than nearest's.
    nearest_tier = triples[nearest_idx][1]
    centroid = cloud.mean(axis=0)
    distances = np.linalg.norm(cloud - centroid, axis=1)
    cross_tier = [
        (i, float(distances[i]))
        for i in range(n)
        if i not in seen and triples[i][1] != nearest_tier
    ]
    if cross_tier:
        cross_idx = min(cross_tier, key=lambda t: t[1])[0]
        picks.append(cross_idx)
        seen.add(cross_idx)

    return picks[:4]


# ---------------------------------------------------------------------------
# Gate helper
# ---------------------------------------------------------------------------

async def _gate_call(
    input_text: str,
    candidate_text: str,
    gate_model: str,
    gate_prompt: str = _GATE_PROMPT,
) -> tuple[str, str]:
    """Run the gate on one candidate. Returns (verdict, reason).

    verdict is "valid" | "invalid" | "ambiguous".

    gate_prompt defaults to the built-in _GATE_PROMPT. Pass a custom string
    (e.g. gate.xml assembled text) via the gate_prompt_text parameter on mld().
    """
    content = _json.dumps({
        "function_or_text": input_text,
        "candidate": candidate_text,
    })
    try:
        result = await api.generate(
            prompt=gate_prompt,
            content=content,
            model=gate_model,
            temperature=0.0,
            max_tokens=128,
            schema=_GATE_SCHEMA,
            n=1,
        )
    except Exception as exc:
        return "ambiguous", f"gate call failed: {exc!r}"
    if isinstance(result, list):
        result = result[0] if result else None
    structured = getattr(result, "structured", None) if result is not None else None
    if not isinstance(structured, dict):
        return "ambiguous", "gate returned no structured output"
    valid = structured.get("valid")
    reason = str(structured.get("reason", ""))
    if valid is True:
        return "valid", reason
    if valid is False:
        return "invalid", reason
    return "ambiguous", reason


# ---------------------------------------------------------------------------
# Batch path helper — build GenerationRequests from pipeline context
# ---------------------------------------------------------------------------

def _make_generation_requests(
    effective_prompt: str,
    user_content: str,
    model: str,
    max_tokens: int,
    n_calls: int,
) -> list[GenerationRequest]:
    """Build GenerationRequest objects for a batch run.

    custom_id format: "embed_for_store:call=N:draft=N/A"
    N/A for draft because three-draft mode is packed into one call.
    """
    requests = []
    for i in range(n_calls):
        requests.append(GenerationRequest(
            custom_id=f"embed_for_store:call={i}:draft=N/A",
            cached_preamble=effective_prompt,
            payload=user_content,
            model=model,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": _THREE_DRAFT_SCHEMA,
                    "strict": True,
                },
            },
        ))
    return requests


def _batch_results_to_call_results(
    batch_results,
    n_calls: int,
) -> list[dict | None]:
    """Convert GenerationResult list from batch into the call_results format.

    Each GenerationResult.drafts is already parsed from the four-shape fallback.
    Reconstruct a dict in the expected {"draft_1":..,"draft_2":..,"draft_3":..}
    shape for downstream _drafts_from_calls compatibility.
    """
    call_results: list[dict | None] = []
    for result in batch_results:
        if result.error or not result.drafts:
            call_results.append(None)
            continue
        drafts = result.drafts
        out = {}
        for idx, key in enumerate(("draft_1", "draft_2", "draft_3")):
            out[key] = drafts[idx] if idx < len(drafts) else ""
        call_results.append(out)
    return call_results


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

async def mld(
    input_text: str,
    prompt: str,
    target_n: int = 12,
    prompt_text: str | None = None,
    gate_prompt_text: str | None = None,
    n_calls: int = 5,
    temperature: float = 0.8,
    generation_model: str = "gpt-4.1-nano",
    gate_model: str = "gpt-4.1-nano",
    selection_model: str = "claude-opus-4-7",
    embed_dim: int = 256,
    embed_model: str = "text-embedding-3-small",
    max_tokens_ceiling: int = 500,
    dispatch: Literal["auto", "sync", "batch"] = "auto",
    repo_root: str | None = None,     # M18: gate-SFT emission; defaults to cwd
    function_id: str = "",            # M18: gate-SFT provenance
) -> MLDResult:
    """Find the V2 minimum lossless description for `input_text`.

    Pipeline phases:
      1. Generate — n_calls parallel three-draft calls (sync) or batch dispatch.
      2. Pre-filter — non-empty, no control chars, imperative start.
      3. Textual degeneracy — re-roll once if >50% byte-equal.
      4. Embed — single batch call.
      5. Geometric degeneracy — skip antipode if avg cosine > 0.999.
      6. Antipode convergence — pick centroid-nearest + up to 4 alternatives.
      7. Gate — Nano "valid?" call on centroid-nearest (with one retry).
      8. Selection — Opus selects when gate is ambiguous.
      9. Confidence — derived from convergence and degeneracy flags.

    The `dispatch` parameter routes generation:
      - "sync"  → always use the async parallel path (original v0.1 behaviour)
      - "batch" → always use OpenAI Batch API
      - "auto"  → batch when n_calls >= 10 (DP4), else sync
    """
    api.reset_cost_totals()

    # KE1: prompt_text overrides the prompt parameter when provided.
    effective_prompt = prompt_text if prompt_text is not None else prompt

    # A1-Task2: gate_prompt_text overrides the built-in _GATE_PROMPT when provided.
    effective_gate_prompt = gate_prompt_text if gate_prompt_text is not None else _GATE_PROMPT

    # -----------------------------------------------------------------------
    # Phase 1 — Generate
    # -----------------------------------------------------------------------
    user_content = f"target_n={target_n}\n\n{input_text}"

    use_batch = should_use_batch(n_calls, dispatch)

    if use_batch:
        # Batch path: submit all n_calls as one batch job and convert results.
        gen_requests = _make_generation_requests(
            effective_prompt, user_content, generation_model,
            max_tokens_ceiling, n_calls,
        )
        batch_results = run_batch_generation(gen_requests)
        first_pass = _batch_results_to_call_results(batch_results, n_calls)
    else:
        # Sync path: async parallel generation (original v0.1 behaviour).
        first_pass = await asyncio.gather(*[
            _three_draft_call(
                prompt=effective_prompt,
                content=user_content,
                model=generation_model,
                temperature=temperature,
                max_tokens=max_tokens_ceiling,
            )
            for _ in range(n_calls)
        ])

    triples, structured_failures = _drafts_from_calls(first_pass)

    deduped = False

    # -----------------------------------------------------------------------
    # Phase 2 — Pre-filter
    # -----------------------------------------------------------------------
    raw_texts = [t[0] for t in triples]
    passing_texts, rejected_texts = _pre_filter(raw_texts)
    passing_set = set(id(s) for s in passing_texts)
    # Rebuild (text, tier, call_idx) triples for passers, in original order.
    rejected_count = len(rejected_texts) + structured_failures
    passing_triples: list[tuple[str, str, int]] = []
    # Use a multiset-aware match: build counter of passing texts and consume.
    pass_counter: Counter = Counter(passing_texts)
    for text, tier, call_idx in triples:
        if pass_counter.get(text, 0) > 0:
            passing_triples.append((text, tier, call_idx))
            pass_counter[text] -= 1

    # -----------------------------------------------------------------------
    # Phase 3 — Textual degeneracy pre-check (>50% byte-equal)
    # -----------------------------------------------------------------------
    if passing_triples:
        text_counter = Counter(t[0] for t in passing_triples)
        most_common_text, most_common_count = text_counter.most_common(1)[0]
        if most_common_count / len(passing_triples) > 0.5:
            # Re-roll once — always use sync path for re-roll.
            deduped = True
            second_pass = await asyncio.gather(*[
                _three_draft_call(
                    prompt=effective_prompt,
                    content=user_content,
                    model=generation_model,
                    temperature=temperature,
                    max_tokens=max_tokens_ceiling,
                )
                for _ in range(n_calls)
            ])
            extra_triples, extra_failures = _drafts_from_calls(second_pass)
            extra_raw = [t[0] for t in extra_triples]
            extra_pass, extra_rej = _pre_filter(extra_raw)
            rejected_count += len(extra_rej) + extra_failures
            extra_pass_counter: Counter = Counter(extra_pass)
            for text, tier, call_idx in extra_triples:
                if extra_pass_counter.get(text, 0) > 0:
                    # Tag with offset call_idx so it does not collide.
                    passing_triples.append((text, tier, call_idx + n_calls))
                    extra_pass_counter[text] -= 1
            triples.extend(extra_triples)

    # Track totals for the report.
    candidates_generated = len(triples)
    candidates_filtered = rejected_count

    # -----------------------------------------------------------------------
    # Early exit if nothing survived the pre-filter
    # -----------------------------------------------------------------------
    if not passing_triples:
        return MLDResult(
            description="",
            target_n=target_n,
            natural_length=0,
            confidence=0.0,
            converged=False,
            candidates_generated=candidates_generated,
            candidates_filtered=candidates_filtered,
            gate_verdict="ambiguous",
            gate_reason="no candidates passed the mechanical pre-filter",
            selection_rationale="no candidates available for gate or selection",
            targets_tried=[target_n],
            degenerate_pre_check=False,
            deduped=deduped,
            cost=api.cost_totals(),
        )

    # -----------------------------------------------------------------------
    # Phase 4 — Embed (single batch)
    # -----------------------------------------------------------------------
    passing_text_list = [t[0] for t in passing_triples]
    raw_embeddings = await api.embed_text(
        passing_text_list, dim=embed_dim, model=embed_model,
    )
    cloud = np.asarray(raw_embeddings, dtype=np.float64)

    # -----------------------------------------------------------------------
    # Phase 5 — Geometric degeneracy (avg off-diagonal cosine > 0.999)
    # -----------------------------------------------------------------------
    degenerate_pre_check = False
    converged = False
    nearest_idx = 0
    alt_indices: list[int] = []

    if cloud.shape[0] >= 2:
        sim = _cosine_sim_matrix(cloud)
        avg_sim = _avg_offdiag(sim)
        if avg_sim > 0.999:
            degenerate_pre_check = True
            # Pick centroid-nearest only; skip antipode.
            centroid = cloud.mean(axis=0)
            distances = np.linalg.norm(cloud - centroid, axis=1)
            nearest_idx = int(distances.argmin())
            converged = False
            alt_indices = []

    # -----------------------------------------------------------------------
    # Phase 6 — Convergence verdict via per-draft spherical variance
    # -----------------------------------------------------------------------
    if not degenerate_pre_check and cloud.shape[0] >= 3:
        from pidgin.pipeline.geometry import convergence_verdict as _convergence_verdict
        _d1_vecs = [cloud[i].tolist() for i, t in enumerate(passing_triples) if t[1] == "d1"]
        _d2_vecs = [cloud[i].tolist() for i, t in enumerate(passing_triples) if t[1] == "d2"]
        _d3_vecs = [cloud[i].tolist() for i, t in enumerate(passing_triples) if t[1] == "d3"]
        if _d1_vecs and _d2_vecs and _d3_vecs:
            _cverd, _ = _convergence_verdict(_d1_vecs, _d2_vecs, _d3_vecs)
            converged = _cverd == "CONVERGED"
        else:
            converged = False
        # Pick centroid-nearest for gate and alternatives.
        _centroid_vec = cloud.mean(axis=0)
        _distances = np.linalg.norm(cloud - _centroid_vec, axis=1)
        nearest_idx = int(_distances.argmin())
        alt_indices = _pick_alternatives(cloud, passing_triples, nearest_idx, target_n)
    elif not degenerate_pre_check and cloud.shape[0] < 3:
        # Sparse cloud: cannot run a meaningful antipode test. Pick the
        # centroid-nearest (or the lone candidate) and proceed to gate.
        if cloud.shape[0] >= 1:
            centroid = cloud.mean(axis=0)
            distances = np.linalg.norm(cloud - centroid, axis=1)
            nearest_idx = int(distances.argmin())
        converged = False
        alt_indices = []

    centroid_nearest_text = passing_triples[nearest_idx][0]

    # -----------------------------------------------------------------------
    # Phase 7 — Gate
    # -----------------------------------------------------------------------
    # M18: resolve repo_root for gate-SFT emission.
    import os as _os
    _sft_root = repo_root if repo_root is not None else _os.getcwd()

    gate_verdict, gate_reason = await _gate_call(
        input_text, centroid_nearest_text, gate_model,
        gate_prompt=effective_gate_prompt,
    )

    # M18: emit gate-SFT record for primary gate call.
    try:
        from pidgin.store import sft as _sft
        _sft.append(_sft_root, [_sft.SFTRecord(
            type="gate",
            prompt=centroid_nearest_text,
            label="valid" if gate_verdict == "valid" else "invalid",
            reason=gate_reason,
            function_id=function_id,
        )])
    except Exception:
        pass  # gate-SFT emission is non-fatal

    description = centroid_nearest_text
    selection_rationale = gate_reason

    if gate_verdict == "valid":
        # Accept centroid-nearest. Skip selection.
        pass
    elif gate_verdict == "invalid":
        # Try one alternative — shortest-above-target_n/2 in a different tier.
        nearest_tier = passing_triples[nearest_idx][1]
        half = max(1, target_n // 2)
        retry_pool = [
            i for i in alt_indices
            if (
                passing_triples[i][1] != nearest_tier
                and len(passing_triples[i][0].split()) > half
            )
        ]
        if retry_pool:
            # Shortest among that pool (above target_n/2, by word count).
            retry_idx = min(
                retry_pool,
                key=lambda i: len(passing_triples[i][0].split()),
            )
            retry_text = passing_triples[retry_idx][0]
            retry_verdict, retry_reason = await _gate_call(
                input_text, retry_text, gate_model,
                gate_prompt=effective_gate_prompt,
            )
            # M18: emit gate-SFT record for retry gate call.
            try:
                _sft.append(_sft_root, [_sft.SFTRecord(
                    type="gate",
                    prompt=retry_text,
                    label="valid" if retry_verdict == "valid" else "invalid",
                    reason=retry_reason,
                    function_id=function_id,
                )])
            except Exception:
                pass  # gate-SFT emission is non-fatal
            if retry_verdict == "valid":
                description = retry_text
                gate_verdict = "valid"
                gate_reason = retry_reason
                selection_rationale = retry_reason
            else:
                # Retry did not pass — gate verdict is ambiguous overall.
                gate_verdict = "ambiguous"
                gate_reason = (
                    f"primary invalid: {gate_reason}; "
                    f"retry {retry_verdict}: {retry_reason}"
                )
                selection_rationale = gate_reason
        else:
            # No suitable alternative — escalate to ambiguous so Opus picks.
            gate_verdict = "ambiguous"
            selection_rationale = gate_reason
    # gate_verdict == "ambiguous" — fall through to selection.

    # -----------------------------------------------------------------------
    # Phase 8 — Selection (Opus) when gate is ambiguous
    # -----------------------------------------------------------------------
    if gate_verdict == "ambiguous":
        centroid = cloud.mean(axis=0)
        distances = np.linalg.norm(cloud - centroid, axis=1)
        candidate_indices = [nearest_idx] + [
            i for i in alt_indices if i != nearest_idx
        ]
        # Cap to nearest + 4 alternatives.
        candidate_indices = candidate_indices[:5]

        candidates_payload = []
        for slot, i in enumerate(candidate_indices):
            text, tier, _ = passing_triples[i]
            candidates_payload.append({
                "index": slot,
                "text": text,
                "tier": tier,
                "dist_to_centroid": float(distances[i]),
                "length": len(text.split()),
            })

        selection_content = _json.dumps({
            "function_or_text": input_text,
            "candidates": candidates_payload,
        })

        try:
            sel_result = await api.generate(
                prompt=_SELECT_PROMPT,
                content=selection_content,
                model=selection_model,
                temperature=0.0,
                max_tokens=512,
                schema=_SELECT_SCHEMA,
                n=1,
            )
            if isinstance(sel_result, list):
                sel_result = sel_result[0] if sel_result else None
            structured = getattr(sel_result, "structured", None)
            if isinstance(structured, dict):
                selected_index = structured.get("selected_index", 0)
                try:
                    selected_index = int(selected_index)
                except Exception:
                    selected_index = 0
                if selected_index < 0 or selected_index >= len(candidate_indices):
                    selected_index = 0
                description = passing_triples[candidate_indices[selected_index]][0]
                selection_rationale = str(structured.get("rationale", "")) or selection_rationale
            else:
                # Selection produced no structured output; keep centroid-nearest.
                selection_rationale = (
                    f"{gate_reason}; selection returned no structured output"
                )
        except Exception as exc:
            selection_rationale = (
                f"{gate_reason}; selection call failed: {exc!r}"
            )

    # -----------------------------------------------------------------------
    # Phase 9 — Confidence
    # -----------------------------------------------------------------------
    confidence = 1.0 if converged else 0.5
    if degenerate_pre_check:
        confidence -= 0.1
    if deduped:
        confidence -= 0.1
    if gate_verdict == "ambiguous":
        confidence -= 0.2
    confidence = max(0.0, min(1.0, confidence))

    cost_snapshot = api.cost_totals()

    return MLDResult(
        description=description,
        target_n=target_n,
        natural_length=len(description.split()),
        confidence=confidence,
        converged=converged,
        candidates_generated=candidates_generated,
        candidates_filtered=candidates_filtered,
        gate_verdict=gate_verdict,
        gate_reason=gate_reason,
        selection_rationale=selection_rationale,
        targets_tried=[target_n],
        degenerate_pre_check=degenerate_pre_check,
        deduped=deduped,
        cost=cost_snapshot,
    )
