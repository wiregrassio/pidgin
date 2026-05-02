#!/usr/bin/env python3
# MODULE: batch
# DOES: OpenAI and Anthropic Batch API dispatch for generation and embedding
#       requests — build JSONL, submit, poll, and parse results with four-shape
#       fallback; Anthropic path uses tool-use structured output with cache control.
# EMITS: list[GenerationResult], list[EmbeddingResult], list[FunctionMldResult],
#        list[AnthropicBatchResult]
# READS: OPENAI_API_KEY and ANTHROPIC_API_KEY from environment (via local/.env)
# IMPLEMENTS: GenerationRequest, GenerationResult, EmbeddingRequest, EmbeddingResult,
#             FunctionMldResult, AnthropicBatchRequest, AnthropicBatchResult,
#             build_jsonl, build_embedding_jsonl, should_use_batch,
#             run_batch_generation, run_batch_embedding, parse_batch_results,
#             parse_embedding_results, run_embedding_mld_pipeline_for_functions,
#             run_anthropic_batch, ADAPTIVE_CONVERGENCE_THRESHOLD,
#             ADAPTIVE_MAX_BATCHES, ADAPTIVE_INITIAL_BATCHES
# DEPENDS: openai, anthropic, python-dotenv, io, json, time, numpy

import io
import json
import time
from dataclasses import dataclass, field
from typing import Literal

from pidgin.utils.api import ensure_api_key


# ---------------------------------------------------------------------------
# Chunked-batch constants (v0.3 M1)
# ---------------------------------------------------------------------------

BATCH_CHUNK_SIZE = 100              # requests per JSONL chunk
BATCH_MAX_CONCURRENT_CHUNKS = 2     # active chunks at once (token ceiling)
BATCH_FILE_SIZE_CEILING = 200 * 1024 * 1024  # 200MB OpenAI ceiling, defensive check


# ---------------------------------------------------------------------------
# Adaptive convergence-stop constants (v0.3 M14)
# ---------------------------------------------------------------------------
# A "batch" here is one API call that produces 3 drafts (the existing
# GenerationRequest unit). On the sync path we run one batch at a time per
# function and stop early once consecutive centroids cluster within
# ADAPTIVE_CONVERGENCE_THRESHOLD cosine similarity. On the batch path we
# always run ADAPTIVE_MAX_BATCHES per function — early-stop on a single
# batched dispatch would require submitting in waves; v0.3 accepts the full
# spend on batch path and reports the final delta for telemetry only.
#
# Threshold reasoning: v0.1 M3 empirics — converged candidate clusters had
# centroid-to-prior-centroid cosine similarity in the 0.97–0.999 range while
# divergent runs sat below 0.95. 0.99 is the inflection that catches stable
# clusters without forcing extra batches on borderline-tight ones.

ADAPTIVE_CONVERGENCE_THRESHOLD = 0.99
ADAPTIVE_MAX_BATCHES = 10
ADAPTIVE_INITIAL_BATCHES = 2  # always run at least 2 to compute a delta


# ---------------------------------------------------------------------------
# Bidirectional (expand) token budget (v0.3 M15)
# ---------------------------------------------------------------------------
# Raised from 200 to 1000 (5×) to cover 40-line function bodies. The v0.2
# truncations were caused by the JSON response envelope exhausting the budget
# before the function body completed; tool-use (no closing-brace requirement)
# and this budget should eliminate them.

BIDIRECTIONAL_MAX_TOKENS = 2000

# Module-level flag so the n_calls deprecation warning fires only once per
# process (logging.warning + filterwarnings dedupe is already noisy under
# test runners — a plain bool is enough here).
_N_CALLS_DEPRECATION_WARNED = False


# ---------------------------------------------------------------------------
# Batch result classifier
# ---------------------------------------------------------------------------

BatchVerdict = Literal["CLEAN", "PARTIAL", "ALL_ERRORED"]


def classify_batch_results(results: list) -> tuple[BatchVerdict, str | None]:
    """Inspect a list of batch results (GenerationResult or EmbeddingResult).
    Return (verdict, first_error_message_or_None).

    - ALL_ERRORED: every result has a non-None error field.
    - PARTIAL:    some have errors, some are clean.
    - CLEAN:      no errors.
    """
    if not results:
        return ("CLEAN", None)

    errors = [getattr(r, "error", None) for r in results]
    n_errored = sum(1 for e in errors if e is not None)
    first_error = next((e for e in errors if e is not None), None)

    if n_errored == len(results):
        return ("ALL_ERRORED", first_error)
    if n_errored > 0:
        return ("PARTIAL", first_error)
    return ("CLEAN", None)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenerationRequest:
    custom_id: str
    cached_preamble: str
    payload: str
    model: str
    max_tokens: int = 500
    response_format: dict | None = None
    temperature: float = 0.3


@dataclass(frozen=True)
class GenerationResult:
    custom_id: str
    drafts: list[str]
    raw_response: dict
    error: str | None


# ---------------------------------------------------------------------------
# JSONL builder
# ---------------------------------------------------------------------------

def build_jsonl(requests: list[GenerationRequest]) -> str:
    """Build a JSONL string where each line is one batch request object.

    Each line: custom_id, method=POST, url=/v1/chat/completions, body with
    model/messages/max_tokens (and optional response_format). System message
    carries cached_preamble; user message carries payload.
    """
    lines: list[str] = []
    for req in requests:
        body: dict = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.cached_preamble},
                {"role": "user", "content": req.payload},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.response_format is not None:
            body["response_format"] = req.response_format
        line_obj = {
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }
        lines.append(json.dumps(line_obj))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch mode decision
# ---------------------------------------------------------------------------

def should_use_batch(n_tasks: int, dispatch: Literal["auto", "sync", "batch"]) -> bool:
    """Return True if the batch API should be used for this run.

    DP4: auto mode selects batch when n_tasks >= 10.
    """
    if dispatch == "sync":
        return False
    if dispatch == "batch":
        return True
    return n_tasks >= 10  # DP4


# ---------------------------------------------------------------------------
# Draft extraction — four-shape fallback
# ---------------------------------------------------------------------------

def _extract_drafts(content: str) -> list[str]:
    """Extract description(s) from a completion content string using four-shape fallback.

    Shape 1: JSON object {"description": str}  — primary shape (single description)
    Shape 2: JSON object {"draft_1":..,"draft_2":..,"draft_3":..}  — legacy three-draft
    Shape 3: JSON object {"drafts":[..]}
    Shape 4: JSON array [...]
    Shape 5: Bare string split on \\n\\n
    """
    text = content.strip() if content else ""
    if not text:
        return []

    # Attempt JSON parse for shapes 1, 2, 3, 4.
    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        pass

    if isinstance(parsed, dict):
        # Shape 1: {"description": str}
        if "description" in parsed and isinstance(parsed["description"], str):
            desc = parsed["description"].strip()
            if desc:
                return [desc]

        # Shape 2: {"draft_1":..,"draft_2":..,"draft_3":..}
        if "draft_1" in parsed:
            drafts = []
            for key in ("draft_1", "draft_2", "draft_3"):
                val = parsed.get(key)
                if isinstance(val, str):
                    drafts.append(val)
            if drafts:
                return drafts

        # Shape 3: {"drafts":[..]}
        if "drafts" in parsed and isinstance(parsed["drafts"], list):
            return [str(d) for d in parsed["drafts"] if d is not None]

    # Shape 4: bare JSON array
    if isinstance(parsed, list):
        return [str(d) for d in parsed if d is not None]

    # Shape 5: bare string split on \n\n
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return parts if parts else [text]


# ---------------------------------------------------------------------------
# Batch result parser
# ---------------------------------------------------------------------------

def parse_batch_results(
    output_jsonl: str,
    error_jsonl: str | None,
    requested_ids: list[str],
) -> list[GenerationResult]:
    """Parse output and error JSONL from a completed batch into GenerationResults.

    For each requested_id:
      - If present in output with a successful response: extract drafts.
      - If present in error file or response has an error body: error field set.
      - If missing entirely: error field set to 'missing from batch output'.

    Returns results in the same order as requested_ids.
    """
    # Parse output JSONL into a dict keyed by custom_id.
    output_by_id: dict[str, dict] = {}
    if output_jsonl:
        for line in output_jsonl.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cid = obj.get("custom_id", "")
                if cid:
                    output_by_id[cid] = obj
            except Exception:
                pass

    # Parse error JSONL into a dict keyed by custom_id.
    error_by_id: dict[str, str] = {}
    if error_jsonl:
        for line in error_jsonl.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cid = obj.get("custom_id", "")
                if cid:
                    # Extract human-readable error message.
                    err_body = obj.get("error") or obj.get("response", {})
                    error_by_id[cid] = json.dumps(err_body)
            except Exception:
                error_by_id[line[:40]] = "unparseable error line"

    results: list[GenerationResult] = []
    for cid in requested_ids:
        if cid in error_by_id:
            results.append(GenerationResult(
                custom_id=cid,
                drafts=[],
                raw_response={},
                error=error_by_id[cid],
            ))
            continue

        if cid not in output_by_id:
            results.append(GenerationResult(
                custom_id=cid,
                drafts=[],
                raw_response={},
                error="missing from batch output",
            ))
            continue

        raw = output_by_id[cid]
        response = raw.get("response", {})
        status_code = response.get("status_code", 200)
        body = response.get("body", {})

        # Check for API-level error in the response body.
        if status_code != 200 or "error" in body:
            err_msg = json.dumps(body.get("error", f"status_code={status_code}"))
            results.append(GenerationResult(
                custom_id=cid,
                drafts=[],
                raw_response=raw,
                error=err_msg,
            ))
            continue

        # Extract the content from the first choice.
        choices = body.get("choices", [])
        if not choices:
            results.append(GenerationResult(
                custom_id=cid,
                drafts=[],
                raw_response=raw,
                error="no choices in response body",
            ))
            continue

        content = choices[0].get("message", {}).get("content", "") or ""
        drafts = _extract_drafts(content)

        results.append(GenerationResult(
            custom_id=cid,
            drafts=drafts,
            raw_response=raw,
            error=None,
        ))

    return results


# ---------------------------------------------------------------------------
# Chunked-pipelined batch submission (v0.3 M1)
# ---------------------------------------------------------------------------

def _chunk_requests(
    requests: list,
    chunk_size: int = BATCH_CHUNK_SIZE,
) -> list:
    """Split a flat list of batch requests into chunks of <= chunk_size."""
    return [requests[i:i + chunk_size] for i in range(0, len(requests), chunk_size)]


def _format_eta(seconds: float) -> str:
    """Format a seconds value as 'Xh Ym' or 'Ym Zs' for human-readable ETA."""
    if seconds <= 0:
        return "0s"
    total_s = int(seconds)
    hours = total_s // 3600
    minutes = (total_s % 3600) // 60
    secs = total_s % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"


def _default_progress_printer(info: dict) -> None:
    """Print batch progress to stderr."""
    import sys as _sys

    event = info["event"]
    ci = info["chunk_index"] + 1
    nc = info["n_chunks"]
    elapsed = info["elapsed_s"]

    if event == "submitted":
        print(f"[batch {ci}/{nc}] submitted, polling...", file=_sys.stderr)
    elif event == "completed":
        # Estimate remaining time from average chunk completion rate.
        avg_per_chunk = elapsed / ci if ci > 0 else 0
        remaining_chunks = nc - ci
        eta_s = avg_per_chunk * remaining_chunks
        eta_str = _format_eta(eta_s)
        print(
            f"[batch {ci}/{nc}] completed | ~{eta_str} remaining",
            file=_sys.stderr,
        )
    elif event == "failed":
        print(f"[batch {ci}/{nc}] FAILED", file=_sys.stderr)


def _submit_chunks_pipelined(
    client,
    chunks: list,
    *,
    endpoint: str,
    description: str,
    max_concurrent: int = BATCH_MAX_CONCURRENT_CHUNKS,
    poll_interval_s: float = 30.0,
    on_progress: "Callable[[dict], None] | None" = None,
) -> list:
    """Submit chunks two-at-a-time. Whenever one completes, submit the next.

    Block until all chunks reach a terminal state. Return the merged
    results list, preserving input order across chunks.

    Pre-flight: write each chunk to its own JSONL file in a tempdir; refuse
    to upload any chunk file > BATCH_FILE_SIZE_CEILING (defensive — chunk_size
    100 should never approach 200MB; raise ValueError if it does).

    on_progress is called with a dict on each submit and each terminal event:
      - event: "submitted" | "completed" | "failed"
      - chunk_index: int
      - n_chunks: int
      - elapsed_s: float (seconds since first submission)
    """
    import os
    import tempfile

    n_chunks = len(chunks)
    terminal_statuses = {"completed", "failed", "expired", "cancelled"}
    _start_time: list[float] = []  # filled on first submission

    # Pre-flight: materialise JSONL bytes for each chunk and size-check.
    chunk_bytes: list[bytes] = []
    for i, chunk in enumerate(chunks):
        data = ("\n".join(json.dumps(line) for line in chunk) + "\n").encode("utf-8")
        if len(data) > BATCH_FILE_SIZE_CEILING:
            raise ValueError(
                f"Chunk {i} JSONL size {len(data)} bytes exceeds "
                f"BATCH_FILE_SIZE_CEILING ({BATCH_FILE_SIZE_CEILING} bytes)"
            )
        chunk_bytes.append(data)

    # State tracking.
    # active: list of (chunk_index, batch_id, batch_obj)
    active: list[tuple[int, str, object]] = []
    next_to_submit = 0
    # results_by_chunk: filled as chunks complete; key = chunk_index
    results_by_chunk: dict[int, list[dict]] = {}

    def _submit_chunk(i: int) -> tuple[int, str, object]:
        """Upload JSONL for chunk i and submit a batch; return (i, batch_id, batch_obj)."""
        chunk_desc = description.replace("i/N", f"{i + 1}/{n_chunks}")
        file_obj = client.files.create(
            file=io.BytesIO(chunk_bytes[i]),
            purpose="batch",
        )
        batch_obj = client.batches.create(
            input_file_id=file_obj.id,
            endpoint=endpoint,
            completion_window="24h",
        )
        # Record first submission time.
        if not _start_time:
            _start_time.append(time.monotonic())
        elapsed = time.monotonic() - _start_time[0]
        if on_progress is not None:
            on_progress({
                "event": "submitted",
                "chunk_index": i,
                "n_chunks": n_chunks,
                "elapsed_s": elapsed,
            })
        return (i, batch_obj.id, batch_obj)

    def _harvest_chunk(chunk_idx: int, batch_obj: object) -> list[dict]:
        """Download and parse a terminal chunk's output JSONL into raw result dicts."""
        status = batch_obj.status
        output_lines: list[dict] = []

        if status == "completed" and batch_obj.output_file_id:
            raw_text = client.files.content(batch_obj.output_file_id).text
            if raw_text:
                for line in raw_text.strip().splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        output_lines.append(json.loads(line))
                    except Exception:
                        pass

        if status != "completed":
            # Represent all requests in the chunk as failed.
            for req in chunks[chunk_idx]:
                output_lines.append({
                    "custom_id": req.get("custom_id", ""),
                    "response": {
                        "status_code": 500,
                        "body": {
                            "error": {
                                "message": f"chunk terminal status: {status}",
                                "type": "chunk_failure",
                            }
                        },
                    },
                })

        return output_lines

    # Seed initial active slots.
    while next_to_submit < n_chunks and len(active) < max_concurrent:
        active.append(_submit_chunk(next_to_submit))
        next_to_submit += 1

    # Pipeline loop.
    while active:
        time.sleep(poll_interval_s)

        still_active: list[tuple[int, str, object]] = []
        for chunk_idx, batch_id, batch_obj in active:
            refreshed = client.batches.retrieve(batch_id)
            if refreshed.status in terminal_statuses:
                # Harvest this chunk and immediately submit the next pending one.
                results_by_chunk[chunk_idx] = _harvest_chunk(chunk_idx, refreshed)
                # Emit completed/failed progress callback.
                if on_progress is not None:
                    elapsed = time.monotonic() - (_start_time[0] if _start_time else 0.0)
                    prog_event = "completed" if refreshed.status == "completed" else "failed"
                    on_progress({
                        "event": prog_event,
                        "chunk_index": chunk_idx,
                        "n_chunks": n_chunks,
                        "elapsed_s": elapsed,
                    })
                if next_to_submit < n_chunks:
                    active.append(_submit_chunk(next_to_submit))
                    next_to_submit += 1
            else:
                still_active.append((chunk_idx, batch_id, refreshed))

        active = still_active

    # Merge results in original chunk order.
    merged: list[dict] = []
    for i in range(n_chunks):
        merged.extend(results_by_chunk.get(i, []))
    return merged


# ---------------------------------------------------------------------------
# Live batch runner
# ---------------------------------------------------------------------------

def run_batch_generation(
    requests: list[GenerationRequest],
    *,
    poll_interval_seconds: float = 30.0,
    timeout_seconds: float = 1800.0,
    api_client=None,
) -> list[GenerationResult]:
    """Submit requests to the OpenAI Batch API via chunked-pipelined upload, poll until done, and parse results.

    Steps:
      1. Build raw request dicts from GenerationRequests.
      2. Split into chunks of BATCH_CHUNK_SIZE via _chunk_requests.
      3. Submit and poll via _submit_chunks_pipelined (max BATCH_MAX_CONCURRENT_CHUNKS active).
      4. Merge raw result dicts across all chunks in input order.
      5. Parse merged output JSONL via parse_batch_results in requested_ids order.

    Returns results in the same order as the input requests list.
    Per-chunk failures surface as error fields on the affected requests;
    sibling chunks that have already completed are not aborted.
    """
    import openai
    import os

    ensure_api_key("OPENAI_API_KEY")
    client = api_client or openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    requested_ids = [r.custom_id for r in requests]

    # Step 1: Build raw request dicts (same shape as JSONL lines).
    raw_requests: list[dict] = []
    for req in requests:
        body: dict = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.cached_preamble},
                {"role": "user", "content": req.payload},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.response_format is not None:
            body["response_format"] = req.response_format
        raw_requests.append({
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        })

    # Step 2: Split into chunks.
    chunks = _chunk_requests(raw_requests)

    # Step 3 & 4: Submit pipelined and collect merged raw result dicts.
    merged_raw = _submit_chunks_pipelined(
        client,
        chunks,
        endpoint="/v1/chat/completions",
        description="generation chunk i/N",
        poll_interval_s=poll_interval_seconds,
        on_progress=_default_progress_printer,
    )

    # Step 5: Reconstruct output JSONL string from merged raw dicts and parse.
    output_jsonl = "\n".join(json.dumps(row) for row in merged_raw)
    return parse_batch_results(output_jsonl, None, requested_ids)


# ---------------------------------------------------------------------------
# Embedding batch dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EmbeddingRequest:
    custom_id: str   # e.g. "embed_for_store:call=2:cand=1"
    text: str


@dataclass(frozen=True)
class EmbeddingResult:
    custom_id: str
    vector: "list[float] | None"   # length EMBEDDING_DIM, or None on error
    error: "str | None"


# ---------------------------------------------------------------------------
# Embedding JSONL builder
# ---------------------------------------------------------------------------

def build_embedding_jsonl(requests: list[EmbeddingRequest]) -> str:
    """Build a JSONL string where each line is one embedding batch request.

    Each line: custom_id, method=POST, url=/v1/embeddings, body with
    model=text-embedding-3-small, dimensions=256, encoding_format=float.
    """
    from pidgin.utils.api import EMBEDDING_MODEL, EMBEDDING_DIM

    lines: list[str] = []
    for req in requests:
        line_obj = {
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/embeddings",
            "body": {
                "model": EMBEDDING_MODEL,
                "input": req.text,
                "dimensions": EMBEDDING_DIM,
                "encoding_format": "float",
            },
        }
        lines.append(json.dumps(line_obj))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Embedding result parser
# ---------------------------------------------------------------------------

def parse_embedding_results(
    output_jsonl: str,
    error_jsonl: "str | None",
    requested_ids: list[str],
) -> "list[EmbeddingResult]":
    """Parse output and error JSONL from a completed embedding batch.

    Four response shapes handled per body:
      1. {"data":[{"embedding":[...]}]} → use data[0].embedding
      2. {"embedding":[...]}            → use .embedding
      3. [...]                          → bare vector list used as-is
      4. {"vector": [...]}              → use .vector

    If the returned vector dimension != EMBEDDING_DIM: error="wrong_dim:<N>".
    Returns results in the same order as requested_ids.
    """
    from pidgin.utils.api import EMBEDDING_DIM

    output_by_id: dict[str, dict] = {}
    if output_jsonl:
        for line in output_jsonl.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cid = obj.get("custom_id", "")
                if cid:
                    output_by_id[cid] = obj
            except Exception:
                pass

    error_by_id: dict[str, str] = {}
    if error_jsonl:
        for line in error_jsonl.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                cid = obj.get("custom_id", "")
                if cid:
                    err_body = obj.get("error") or obj.get("response", {})
                    error_by_id[cid] = json.dumps(err_body)
            except Exception:
                error_by_id[line[:40]] = "unparseable error line"

    results: list[EmbeddingResult] = []
    for cid in requested_ids:
        if cid in error_by_id:
            results.append(EmbeddingResult(custom_id=cid, vector=None, error=error_by_id[cid]))
            continue

        if cid not in output_by_id:
            results.append(EmbeddingResult(custom_id=cid, vector=None, error="missing from batch output"))
            continue

        raw = output_by_id[cid]
        response = raw.get("response", {})
        status_code = response.get("status_code", 200)
        body = response.get("body", {})

        if status_code != 200 or "error" in body:
            err_msg = json.dumps(body.get("error", f"status_code={status_code}"))
            results.append(EmbeddingResult(custom_id=cid, vector=None, error=err_msg))
            continue

        # Four-shape fallback to extract the vector.
        vector = None

        # Shape 1: {"data":[{"embedding":[...]}]}
        if isinstance(body, dict) and "data" in body:
            data_list = body["data"]
            if isinstance(data_list, list) and data_list:
                first = data_list[0]
                if isinstance(first, dict) and "embedding" in first:
                    vector = first["embedding"]

        # Shape 2: {"embedding":[...]}
        if vector is None and isinstance(body, dict) and "embedding" in body:
            vector = body["embedding"]

        # Shape 3: bare vector list
        if vector is None and isinstance(body, list):
            vector = body

        # Shape 4: {"vector":[...]}
        if vector is None and isinstance(body, dict) and "vector" in body:
            vector = body["vector"]

        if vector is None:
            results.append(EmbeddingResult(custom_id=cid, vector=None, error="no embedding found in response body"))
            continue

        if not isinstance(vector, list):
            results.append(EmbeddingResult(custom_id=cid, vector=None, error="embedding is not a list"))
            continue

        if len(vector) != EMBEDDING_DIM:
            results.append(EmbeddingResult(custom_id=cid, vector=None, error=f"wrong_dim:{len(vector)}"))
            continue

        results.append(EmbeddingResult(custom_id=cid, vector=vector, error=None))

    return results


# ---------------------------------------------------------------------------
# Live embedding batch runner
# ---------------------------------------------------------------------------

def run_batch_embedding(
    requests: list[EmbeddingRequest],
    *,
    poll_interval_seconds: float = 30.0,
    timeout_seconds: float = 1800.0,
    api_client=None,
) -> "list[EmbeddingResult]":
    """Submit embedding requests to the OpenAI Batch API via chunked-pipelined upload, poll until done, and parse.

    Steps:
      1. Build raw request dicts from EmbeddingRequests.
      2. Split into chunks of BATCH_CHUNK_SIZE via _chunk_requests.
      3. Submit and poll via _submit_chunks_pipelined (max BATCH_MAX_CONCURRENT_CHUNKS active).
      4. Merge raw result dicts across all chunks in input order.
      5. Parse merged output JSONL via parse_embedding_results in requested_ids order.

    Returns results in the same order as the input requests list.
    Per-chunk failures surface as error fields on the affected requests;
    sibling chunks that have already completed are not aborted.
    """
    import openai
    import os

    from pidgin.utils.api import EMBEDDING_MODEL, EMBEDDING_DIM

    ensure_api_key("OPENAI_API_KEY")
    client = api_client or openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    requested_ids = [r.custom_id for r in requests]

    # Step 1: Build raw request dicts (same shape as JSONL lines).
    raw_requests: list[dict] = []
    for req in requests:
        raw_requests.append({
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/embeddings",
            "body": {
                "model": EMBEDDING_MODEL,
                "input": req.text,
                "dimensions": EMBEDDING_DIM,
                "encoding_format": "float",
            },
        })

    # Step 2: Split into chunks.
    chunks = _chunk_requests(raw_requests)

    # Step 3 & 4: Submit pipelined and collect merged raw result dicts.
    merged_raw = _submit_chunks_pipelined(
        client,
        chunks,
        endpoint="/v1/embeddings",
        description="embedding chunk i/N",
        poll_interval_s=poll_interval_seconds,
        on_progress=_default_progress_printer,
    )

    # Step 5: Reconstruct output JSONL string from merged raw dicts and parse.
    output_jsonl = "\n".join(json.dumps(row) for row in merged_raw)
    return parse_embedding_results(output_jsonl, None, requested_ids)


# ---------------------------------------------------------------------------
# End-to-end function MLD result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FunctionMldResult:
    name: str
    candidates: list[str]                   # up to ADAPTIVE_MAX_BATCHES candidate descriptions
    vectors: "list[list[float] | None]"     # parallel to candidates
    cluster_size: int
    converged: bool                          # True when spherical_variance(vectors) < CONVERGENCE_THRESHOLD
    sv: float = 0.0                          # spherical variance of all valid vectors
    first_error: "str | None" = None        # set when all gen results for this function errored
    # M14 — adaptive convergence-stop instrumentation.
    n_batches_run: int = 0
    final_convergence_delta: "float | None" = None
    # M18 — SFT provenance: the MLD prompt assembled for this function.
    prompt_used: str = ""


# ---------------------------------------------------------------------------
# End-to-end pipeline helper
# ---------------------------------------------------------------------------

def _stratify(
    texts: "list[str]",
    draft_indices: "list[int]",
    vectors: "list[list[float] | None]",
) -> "tuple[dict[int, list[float]], dict[int, float], dict[int, int]]":
    """Group candidates by draft_index. Return (centroid_per_draft,
    tightness_per_draft, count_per_draft).

    Accepts three parallel lists: candidate texts, their draft indices (1/2/3),
    and their embedding vectors (None entries are skipped). Candidates without
    a valid vector are excluded from the per-draft groups.
    """
    from collections import defaultdict
    from pidgin.pipeline.geometry import cosine_similarity

    groups: "dict[int, list[list[float]]]" = defaultdict(list)
    for di, vec in zip(draft_indices, vectors):
        if vec is not None:
            groups[di].append(vec)

    centroid: "dict[int, list[float]]" = {}
    tightness: "dict[int, float]" = {}
    n_per: "dict[int, int]" = {}

    for di, vecs in groups.items():
        if not vecs:
            continue
        # centroid (mean across dims).
        dim = len(vecs[0])
        cent = [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]
        # tightness = mean cosine_similarity to centroid.
        tight = sum(cosine_similarity(v, cent) for v in vecs) / len(vecs)
        centroid[di] = cent
        tightness[di] = tight
        n_per[di] = len(vecs)

    return centroid, tightness, n_per


def _build_converge_request(
    fn: dict,
    fi: int,
    ci: int,
    converge_template: str,
) -> GenerationRequest:
    """Assemble one GenerationRequest for function fi, call slot ci.

    Encapsulates template assembly + json_schema response_format so both
    the batch path (build all upfront) and the sync adaptive loop (build
    one at a time) emit identical request shapes.
    """
    from pidgin.prompts.templates import assemble_xml_prompt

    try:
        assembled = assemble_xml_prompt(
            converge_template,
            {
                "file": fn.get("file", ""),
                "name": fn.get("name", ""),
                "line_start": str(fn.get("line_start", "")),
                "function_body": fn.get("body", ""),
            },
        )
        preamble = assembled.cached_preamble
        payload = assembled.payload
    except Exception:
        preamble = ""
        payload = fn.get("body", "")

    return GenerationRequest(
        custom_id=f"gen:func={fi}:call={ci}",
        cached_preamble=preamble,
        payload=payload,
        model="gpt-4.1-nano",
        max_tokens=500,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "answer",
                "schema": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                    },
                    "required": ["description"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        },
    )


def _generate_one_sync(req: GenerationRequest) -> GenerationResult:
    """Issue one sync generation call and return the GenerationResult.

    Mirrors the inner body of the previous sync fallback; isolated here so
    the per-function adaptive loop can call it once per batch.
    """
    import asyncio

    from pidgin.utils.api import generate

    schema = None
    if req.response_format and req.response_format.get("type") == "json_schema":
        schema = req.response_format["json_schema"].get("schema")

    async def _call():
        return await generate(
            prompt=req.cached_preamble,
            content=req.payload,
            model=req.model,
            temperature=0.3,
            max_tokens=req.max_tokens,
            schema=schema,
        )

    try:
        r = asyncio.run(_call())
        if isinstance(r, list):
            r = r[0] if r else None
        structured = getattr(r, "structured", None) if r else None
        if structured and isinstance(structured, dict):
            # Primary shape: {"description": str}
            if "description" in structured and isinstance(structured["description"], str):
                desc = structured["description"].strip()
                drafts = [desc] if desc else []
            else:
                # Legacy fallback: {"draft_1":..,"draft_2":..,"draft_3":..}
                drafts = [structured.get(k, "") for k in ("draft_1", "draft_2", "draft_3")]
                drafts = [d for d in drafts if d]
        else:
            drafts = []
    except Exception:
        drafts = []

    return GenerationResult(
        custom_id=req.custom_id,
        drafts=drafts,
        raw_response={},
        error=None if drafts else "sync generation failed",
    )


def _embed_sync(texts: list[str]) -> list["list[float] | None"]:
    """Sync-embed a list of texts via pidgin.utils.api.embed_for_store.

    Returns a list parallel to `texts`; missing entries become None.
    """
    import asyncio

    if not texts:
        return []

    from pidgin.utils.api import embed_for_store

    raw = asyncio.run(embed_for_store(texts))
    out: list["list[float] | None"] = []
    for i in range(len(texts)):
        out.append(raw[i] if i < len(raw) else None)
    return out


def run_embedding_mld_pipeline_for_functions(
    functions: list[dict],
    *,
    converge_template: str = str(
        __import__("pathlib").Path(__file__).parent.parent / "prompts" / "converge.xml"
    ),
    max_batches: int = ADAPTIVE_MAX_BATCHES,
    convergence_threshold: float = ADAPTIVE_CONVERGENCE_THRESHOLD,
    dispatch: "Literal['auto','sync','batch']" = "auto",
    verbose: bool = False,
    n_calls: "int | None" = None,
    on_chunk_complete: "Callable[[list[FunctionMldResult], list[dict]], None] | None" = None,
) -> "list[FunctionMldResult]":
    """Adaptive generation + embedding MLD pipeline.

    Per-function loop runs at least ADAPTIVE_INITIAL_BATCHES batches, then
    stops early when consecutive centroids cluster within
    `convergence_threshold` cosine similarity. Caps at `max_batches`. Each
    "batch" is a single API call producing 3 drafts (the existing
    GenerationRequest unit).

    Dispatch paths:
      - sync: per-function adaptive loop. One API call at a time, embed
        the new drafts, recompute centroid, decide whether to stop. This is
        where convergence-stop saves token cost.
      - batch: delegates to run_incremental_mld_pipeline for per-chunk upsert
        resilience (M1). Processes one BATCH_CHUNK_SIZE chunk at a time,
        fires on_chunk_complete after each chunk completes.
      - auto: routes via should_use_batch (DP4: n_tasks >= 10 → batch).

    on_chunk_complete(chunk_results, chunk_functions) is called after each
    chunk completes (batch path) or after each function completes (sync path).
    Defaults to None for backward compatibility.

    Each function dict must have keys: name, file, body, line_start.

    Backward compatibility: the legacy `n_calls` keyword maps to
    `max_batches` and emits a one-time DeprecationWarning.
    """
    import sys
    import warnings

    from pidgin.pipeline.geometry import cosine_similarity, centroid as _centroid

    # -----------------------------------------------------------------------
    # Backwards-compat: n_calls → max_batches
    # -----------------------------------------------------------------------
    if n_calls is not None:
        global _N_CALLS_DEPRECATION_WARNED
        if not _N_CALLS_DEPRECATION_WARNED:
            warnings.warn(
                "run_embedding_mld_pipeline_for_functions(n_calls=...) is "
                "deprecated; use max_batches=... instead. Mapping n_calls "
                "to max_batches for this call.",
                DeprecationWarning,
                stacklevel=2,
            )
            _N_CALLS_DEPRECATION_WARNED = True
        max_batches = n_calls

    n_funcs = len(functions)
    n_total_gen_requests = n_funcs * max_batches
    use_batch_gen = should_use_batch(n_total_gen_requests, dispatch)

    # =======================================================================
    # SYNC PATH — per-function adaptive convergence loop with early stop.
    # =======================================================================
    if not use_batch_gen:
        return _run_pipeline_sync_adaptive(
            functions=functions,
            converge_template=converge_template,
            max_batches=max_batches,
            convergence_threshold=convergence_threshold,
            dispatch=dispatch,
            verbose=verbose,
            on_chunk_complete=on_chunk_complete,
        )

    # =======================================================================
    # BATCH PATH — delegate to run_incremental_mld_pipeline for per-chunk
    # upsert resilience (M1).
    # =======================================================================
    return run_incremental_mld_pipeline(
        functions,
        converge_template=converge_template,
        max_batches=max_batches,
        convergence_threshold=convergence_threshold,
        dispatch=dispatch,
        verbose=verbose,
        on_chunk_complete=on_chunk_complete,
    )


def _run_pipeline_sync_adaptive(
    *,
    functions: list[dict],
    converge_template: str,
    max_batches: int,
    convergence_threshold: float,
    dispatch: "Literal['auto','sync','batch']",
    verbose: bool,
    on_chunk_complete: "Callable[[list[FunctionMldResult], list[dict]], None] | None" = None,
) -> "list[FunctionMldResult]":
    """Sync-path implementation of the adaptive convergence pipeline.

    For each function: generate one batch (1 API call → 3 drafts), embed
    those drafts, recompute centroid over all candidates, compare to the
    previous centroid via cosine_similarity. Stop when delta >=
    convergence_threshold, but always run at least
    ADAPTIVE_INITIAL_BATCHES. Cap at max_batches.

    on_chunk_complete(chunk_results, chunk_funcs) is called after each
    function completes (chunk size of 1 on the sync path). This provides
    the same Ctrl+C resilience as the batch incremental path.
    """
    import sys

    ensure_api_key("OPENAI_API_KEY")

    from pidgin.pipeline.geometry import is_converged as _is_converged, cosine_similarity, centroid as _centroid

    output: list[FunctionMldResult] = []

    for fi, fn in enumerate(functions):
        cands: list[str] = []
        vectors: list["list[float] | None"] = []
        valid_vecs: list[list[float]] = []
        prev_centroid: "list[float] | None" = None
        final_delta: "float | None" = None
        n_batches = 0
        gen_errors: list["str | None"] = []
        func_prompt: str = ""  # M18 — SFT provenance (captured from first batch)

        for batch_idx in range(max_batches):
            req = _build_converge_request(fn, fi, batch_idx, converge_template)
            if batch_idx == 0:
                func_prompt = req.cached_preamble + "\n\n" + req.payload
            gr = _generate_one_sync(req)
            n_batches += 1
            gen_errors.append(gr.error)

            new_texts: list[str] = []
            if not gr.error and gr.drafts:
                for draft in gr.drafts[:1]:
                    if draft:
                        new_texts.append(draft)

            new_vecs = _embed_sync(new_texts) if new_texts else []
            for text, vec in zip(new_texts, new_vecs):
                cands.append(text)
                vectors.append(vec)
                if vec is not None:
                    valid_vecs.append(vec)

            if not valid_vecs:
                # No vectors yet — cannot compute centroid, keep going.
                continue

            cur_centroid = _centroid(valid_vecs)

            # Seed prev_centroid unconditionally on every non-empty batch.
            # This allows the FIRST comparison to fire on batch ADAPTIVE_INITIAL_BATCHES (idx 1).
            if prev_centroid is None:
                prev_centroid = cur_centroid
                continue  # need prev to compare against; skip comparison on this batch

            # Convergence check — only after warm-up.
            if batch_idx + 1 >= ADAPTIVE_INITIAL_BATCHES:
                delta = cosine_similarity(cur_centroid, prev_centroid)
                final_delta = delta
                if delta >= convergence_threshold:
                    prev_centroid = cur_centroid
                    break

            prev_centroid = cur_centroid

        cluster_size = len(valid_vecs)
        all_errored = bool(gen_errors) and all(e for e in gen_errors)
        func_first_error = gen_errors[0] if all_errored else None

        # Convergence via single-number spherical variance test.
        _converged, _sv = _is_converged(valid_vecs) if valid_vecs else (False, 0.0)

        output.append(FunctionMldResult(
            name=fn.get("name", ""),
            candidates=cands,
            vectors=vectors,
            cluster_size=cluster_size,
            converged=_converged,
            sv=_sv,
            first_error=func_first_error,
            n_batches_run=n_batches,
            final_convergence_delta=final_delta,
            prompt_used=func_prompt,  # M18 — SFT provenance
        ))

        if verbose:
            stop_note = (
                f" stop@{n_batches} delta={final_delta:.4f}"
                if final_delta is not None
                else f" stop@{n_batches} delta=n/a"
            )
            print(f"[mld] {fn.get('name', '')}: sv={_sv:.4f} converged={_converged}{stop_note}", file=sys.stderr)

        # M1: fire on_chunk_complete after each function (chunk size = 1).
        if on_chunk_complete is not None:
            on_chunk_complete([output[-1]], [fn])

    _emit_convergence_summary(output, verbose=verbose)
    return output


def _emit_convergence_summary(
    output: "list[FunctionMldResult]",
    *,
    verbose: bool,
) -> None:
    """Print median + range of n_batches_run across the pipeline run.

    Verbose-only; goes to stderr to match the per-function [mld] line.
    """
    import sys

    if not verbose:
        return
    counts = [r.n_batches_run for r in output if r.n_batches_run > 0]
    if not counts:
        return
    counts.sort()
    median = counts[len(counts) // 2]
    print(
        f"[mld] {len(counts)} functions: median {median} batches, "
        f"range {counts[0]}-{counts[-1]}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Anthropic Batch API — data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnthropicBatchRequest:
    custom_id: str
    cached_preamble: str    # placed in system block with cache_control: ephemeral
    payload: str            # placed in user message
    model: str              # "claude-haiku-4-5-20251001" for gate calls
    max_tokens: int = 256
    response_schema: dict | None = None  # if set, use tool-call structured output


@dataclass(frozen=True)
class AnthropicBatchResult:
    custom_id: str
    text: str | None        # model's response text (None when tool_use path)
    parsed: dict | None     # if response_schema set, the parsed JSON from tool input
    raw_response: dict
    error: str | None


# ---------------------------------------------------------------------------
# Anthropic Batch API — live runner
# ---------------------------------------------------------------------------

def run_anthropic_batch(
    requests: list[AnthropicBatchRequest],
    *,
    poll_interval_seconds: float = 5.0,
    timeout_seconds: float = 1800.0,
    api_client=None,  # default: anthropic.Anthropic() from env
) -> list[AnthropicBatchResult]:
    """Submit requests to the Anthropic Batches API, poll until ended, and parse results.

    Steps:
      1. Build the requests list for client.messages.batches.create().
         System block carries cache_control: ephemeral for preamble caching.
         If response_schema is set, inject a gate_verdict tool + tool_choice
         to enforce structured output via Anthropic tool use.
      2. Submit via client.messages.batches.create(requests=batch_requests).
      3. Poll client.messages.batches.retrieve(batch.id) until
         processing_status in {"ended", "canceling", "expired"}.
      4. Stream results via client.messages.batches.results(batch.id).
      5. For each result: extract text from the first content block, or parse
         the tool_use block input as `parsed` when response_schema was set.

    Returns results in the same order as the input requests list.
    """
    import anthropic
    import os

    ensure_api_key("ANTHROPIC_API_KEY")
    client = api_client or anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    ordered_ids = [r.custom_id for r in requests]

    # Step 1: Build the Anthropic batch requests list.
    batch_requests = []
    for req in requests:
        params: dict = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": req.cached_preamble,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": req.payload}],
        }
        if req.response_schema is not None:
            params["tools"] = [
                {
                    "name": "gate_verdict",
                    "description": "Return the gate verdict",
                    "input_schema": req.response_schema,
                }
            ]
            params["tool_choice"] = {"type": "tool", "name": "gate_verdict"}

        batch_requests.append({
            "custom_id": req.custom_id,
            "params": params,
        })

    # Step 2: Submit batch.
    batch = client.messages.batches.create(requests=batch_requests)
    batch_id = batch.id

    # Step 3: Poll until terminal status.
    terminal_statuses = {"ended", "canceling", "expired"}
    deadline = time.monotonic() + timeout_seconds
    status = batch.processing_status

    while status not in terminal_statuses:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Anthropic batch {batch_id} did not reach terminal status within "
                f"{timeout_seconds}s. Last status: {status}"
            )
        time.sleep(poll_interval_seconds)
        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status

    # Step 4 & 5: Stream results and parse.
    results_by_id: dict[str, AnthropicBatchResult] = {}

    for result_item in client.messages.batches.results(batch_id):
        cid = result_item.custom_id
        result = result_item.result

        # Check for error result types.
        result_type = getattr(result, "type", None)

        if result_type != "succeeded":
            error_msg = f"result type: {result_type}"
            if hasattr(result, "error"):
                err = result.error
                error_msg = getattr(err, "message", None) or str(err)
            results_by_id[cid] = AnthropicBatchResult(
                custom_id=cid,
                text=None,
                parsed=None,
                raw_response={},
                error=error_msg,
            )
            continue

        # Succeeded: extract message content.
        message = result.message
        content_blocks = getattr(message, "content", []) or []

        text = None
        parsed = None

        for block in content_blocks:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use" and getattr(block, "name", None) == "gate_verdict":
                # Structured output via tool_use — extract .input dict.
                parsed = block.input if isinstance(block.input, dict) else dict(block.input)
                break
            if block_type == "text" and text is None:
                text = block.text

        # Serialize raw_response as a dict for storage.
        raw_response = {
            "id": getattr(message, "id", None),
            "model": getattr(message, "model", None),
            "stop_reason": getattr(message, "stop_reason", None),
            "usage": {
                "input_tokens": getattr(getattr(message, "usage", None), "input_tokens", None),
                "output_tokens": getattr(getattr(message, "usage", None), "output_tokens", None),
            },
        }

        results_by_id[cid] = AnthropicBatchResult(
            custom_id=cid,
            text=text,
            parsed=parsed,
            raw_response=raw_response,
            error=None,
        )

    # Return in the same order as the input requests list.
    ordered_results: list[AnthropicBatchResult] = []
    for cid in ordered_ids:
        if cid in results_by_id:
            ordered_results.append(results_by_id[cid])
        else:
            ordered_results.append(AnthropicBatchResult(
                custom_id=cid,
                text=None,
                parsed=None,
                raw_response={},
                error="missing from batch results",
            ))

    return ordered_results


# ---------------------------------------------------------------------------
# Incremental MLD pipeline — per-chunk upsert (M1)
# ---------------------------------------------------------------------------

def _submit_one_chunk_generation(
    client,
    chunk_gen_requests: "list[GenerationRequest]",
    *,
    poll_interval_seconds: float = 30.0,
) -> "list[GenerationResult]":
    """Submit one generation chunk to the OpenAI Batch API and return parsed results.

    Uploads the chunk as a single JSONL file, creates the batch, polls until
    terminal, downloads output, and parses into GenerationResults. Mirrors the
    inner logic of run_batch_generation for a single chunk so that
    run_incremental_mld_pipeline can call the callback between chunks.
    """
    import io as _io

    requested_ids = [r.custom_id for r in chunk_gen_requests]

    # Build raw request dicts.
    raw_requests: list[dict] = []
    for req in chunk_gen_requests:
        body: dict = {
            "model": req.model,
            "messages": [
                {"role": "system", "content": req.cached_preamble},
                {"role": "user", "content": req.payload},
            ],
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }
        if req.response_format is not None:
            body["response_format"] = req.response_format
        raw_requests.append({
            "custom_id": req.custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        })

    # Serialise to JSONL bytes.
    data = ("\n".join(json.dumps(r) for r in raw_requests) + "\n").encode("utf-8")

    # Upload, submit, and poll.
    file_obj = client.files.create(file=_io.BytesIO(data), purpose="batch")
    batch_obj = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
    )
    batch_id = batch_obj.id
    terminal_statuses = {"completed", "failed", "expired", "cancelled"}

    while batch_obj.status not in terminal_statuses:
        time.sleep(poll_interval_seconds)
        batch_obj = client.batches.retrieve(batch_id)

    # Harvest output.
    output_lines: list[dict] = []
    if batch_obj.status == "completed" and batch_obj.output_file_id:
        raw_text = client.files.content(batch_obj.output_file_id).text
        if raw_text:
            for line in raw_text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    output_lines.append(json.loads(line))
                except Exception:
                    pass

    if batch_obj.status != "completed":
        # Represent all requests in chunk as failed.
        for req in chunk_gen_requests:
            output_lines.append({
                "custom_id": req.custom_id,
                "response": {
                    "status_code": 500,
                    "body": {
                        "error": {
                            "message": f"chunk terminal status: {batch_obj.status}",
                            "type": "chunk_failure",
                        }
                    },
                },
            })

    output_jsonl = "\n".join(json.dumps(row) for row in output_lines)
    return parse_batch_results(output_jsonl, None, requested_ids)


def _build_function_mld_results_from_gen(
    gen_results_for_chunk: "list[GenerationResult]",
    chunk_functions: "list[dict]",
    *,
    max_batches: int,
    func_prompt_used: "list[str]",
    func_base_fi: int,
    dispatch: "Literal['auto','sync','batch']",
) -> "list[FunctionMldResult]":
    """Embed candidates for a chunk's functions and build FunctionMldResult objects.

    Accepts the GenerationResults for one generation chunk (all calls for the
    functions in this chunk), the corresponding function dicts, and provenance
    metadata. Embeds all candidates (batch or sync depending on dispatch), then
    constructs one FunctionMldResult per function.

    func_base_fi: the fi index of the first function in this chunk; used to
    reconstruct custom_ids ("gen:func={fi}:call={ci}") for lookup.
    """
    import sys

    from pidgin.pipeline.geometry import is_converged as _is_converged, cosine_similarity, centroid as _centroid

    n_chunk_funcs = len(chunk_functions)
    cap = max_batches

    # Build gen_by_id for lookup.
    gen_by_id: dict[str, GenerationResult] = {r.custom_id: r for r in gen_results_for_chunk}

    # Flatten candidates per function in this chunk (1 draft per call).
    func_candidates: list[list[str]] = [[] for _ in range(n_chunk_funcs)]
    func_cand_call: list[list[int]] = [[] for _ in range(n_chunk_funcs)]

    for local_fi in range(n_chunk_funcs):
        fi = func_base_fi + local_fi
        for ci in range(max_batches):
            gr = gen_by_id.get(f"gen:func={fi}:call={ci}")
            if gr and not gr.error and gr.drafts:
                draft = gr.drafts[0] if gr.drafts else None
                if draft:
                    func_candidates[local_fi].append(draft)
                    func_cand_call[local_fi].append(ci)
        func_candidates[local_fi] = func_candidates[local_fi][:cap]
        func_cand_call[local_fi] = func_cand_call[local_fi][:cap]

    # Build EmbeddingRequests for all candidates in this chunk.
    embed_requests: list[EmbeddingRequest] = []
    for local_fi, cands in enumerate(func_candidates):
        for ci, text in enumerate(cands):
            embed_requests.append(EmbeddingRequest(
                custom_id=f"embed:func={func_base_fi + local_fi}:cand={ci}",
                text=text,
            ))

    # Embed (batch or sync).
    use_batch_embed = should_use_batch(len(embed_requests), dispatch)
    if use_batch_embed and embed_requests:
        embed_results = run_batch_embedding(embed_requests)
    elif embed_requests:
        texts = [r.text for r in embed_requests]
        raw = _embed_sync(texts)
        embed_results = [
            EmbeddingResult(
                custom_id=embed_requests[i].custom_id,
                vector=raw[i],
                error=None if raw[i] is not None else "sync embed failed",
            )
            for i in range(len(embed_requests))
        ]
    else:
        embed_results = []

    embed_by_id: dict[str, EmbeddingResult] = {r.custom_id: r for r in embed_results}

    # Build FunctionMldResult objects.
    output: list[FunctionMldResult] = []
    for local_fi, fn in enumerate(chunk_functions):
        fi = func_base_fi + local_fi
        cands = func_candidates[local_fi]
        vectors: list["list[float] | None"] = []
        valid_vecs: list[list[float]] = []
        for ci in range(len(cands)):
            er = embed_by_id.get(f"embed:func={fi}:cand={ci}")
            if er and er.vector is not None:
                vectors.append(er.vector)
                valid_vecs.append(er.vector)
            else:
                vectors.append(None)

        cluster_size = len(valid_vecs)

        # Compute final convergence delta from per-call cumulative centroids.
        final_delta: "float | None" = None
        cumulative: list[list[float]] = []
        prev_cent: "list[float] | None" = None
        last_observed_call = -1
        for cand_idx, call_idx in enumerate(func_cand_call[local_fi]):
            v = vectors[cand_idx]
            if v is None:
                continue
            cumulative.append(v)
            if call_idx != last_observed_call:
                cur_cent = _centroid(cumulative)
                if prev_cent is not None:
                    final_delta = cosine_similarity(cur_cent, prev_cent)
                prev_cent = cur_cent
                last_observed_call = call_idx
            else:
                prev_cent = _centroid(cumulative)

        # Determine first_error.
        func_gen_results = [
            gen_by_id[f"gen:func={fi}:call={ci}"]
            for ci in range(max_batches)
            if f"gen:func={fi}:call={ci}" in gen_by_id
        ]
        all_errored = bool(func_gen_results) and all(gr.error for gr in func_gen_results)
        func_first_error = func_gen_results[0].error if all_errored else None

        # Convergence via single-number spherical variance test.
        _converged, _sv = _is_converged(valid_vecs) if valid_vecs else (False, 0.0)

        output.append(FunctionMldResult(
            name=fn.get("name", ""),
            candidates=cands,
            vectors=vectors,
            cluster_size=cluster_size,
            converged=_converged,
            sv=_sv,
            first_error=func_first_error,
            n_batches_run=max_batches,
            final_convergence_delta=final_delta,
            prompt_used=func_prompt_used[func_base_fi + local_fi],
        ))

    return output


def run_incremental_mld_pipeline(
    functions: list[dict],
    *,
    converge_template: str,
    max_batches: int,
    convergence_threshold: float,
    dispatch: "Literal['auto','sync','batch']",
    verbose: bool,
    on_chunk_complete: "Callable[[list[FunctionMldResult], list[dict]], None] | None" = None,
) -> "list[FunctionMldResult]":
    """Incremental batch MLD pipeline: embed and upsert after each generation chunk.

    Replaces the all-at-once batch path in run_embedding_mld_pipeline_for_functions
    with a per-chunk loop that immediately embeds and builds FunctionMldResult
    objects for the functions covered by each chunk, then fires on_chunk_complete
    so the caller can upsert to ChromaDB and write SFT records before the next
    chunk begins.

    Chunk-to-function mapping: each generation chunk contains BATCH_CHUNK_SIZE
    requests (100 by default). With max_batches calls per function, each chunk
    of 100 requests covers 100 // max_batches functions. Functions whose fi
    indices fall in [chunk_start_fi, chunk_end_fi) are fully complete after
    their chunk finishes.

    on_chunk_complete(chunk_results, chunk_functions) is called with:
      - chunk_results: list[FunctionMldResult] for functions in this chunk
      - chunk_functions: list[dict] — the corresponding function dicts

    Returns the full accumulated results list in input order.
    """
    import openai
    import os
    import sys

    ensure_api_key("OPENAI_API_KEY")
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    n_funcs = len(functions)

    # Step 1 — Build all GenerationRequests upfront (same as existing batch path).
    gen_requests: list[GenerationRequest] = []
    func_prompt_used: list[str] = [""] * n_funcs
    for fi, fn in enumerate(functions):
        for ci in range(max_batches):
            req = _build_converge_request(fn, fi, ci, converge_template)
            gen_requests.append(req)
            if ci == 0:
                func_prompt_used[fi] = req.cached_preamble + "\n\n" + req.payload

    # Step 2 — Split generation requests into BATCH_CHUNK_SIZE chunks.
    # Each chunk covers (BATCH_CHUNK_SIZE // max_batches) functions.
    chunks = _chunk_requests(gen_requests)
    n_chunks = len(chunks)

    all_results: list[FunctionMldResult] = []
    processed_fi = 0  # running count of functions fully processed
    _incr_start = time.monotonic()

    for chunk_idx, chunk_requests in enumerate(chunks):
        if verbose:
            print(
                f"[mld] incremental chunk {chunk_idx + 1}/{n_chunks} "
                f"({len(chunk_requests)} requests)",
                file=sys.stderr,
            )

        # Emit submission progress.
        _default_progress_printer({
            "event": "submitted",
            "chunk_index": chunk_idx,
            "n_chunks": n_chunks,
            "elapsed_s": time.monotonic() - _incr_start,
        })

        # Step 3a — Submit this generation chunk and wait for it to complete.
        gen_results = _submit_one_chunk_generation(
            client,
            chunk_requests,
        )

        # Emit completion progress.
        _default_progress_printer({
            "event": "completed",
            "chunk_index": chunk_idx,
            "n_chunks": n_chunks,
            "elapsed_s": time.monotonic() - _incr_start,
        })

        # Determine which function indices this chunk covers.
        # Each request has custom_id "gen:func={fi}:call={ci}"; extract unique fi.
        chunk_fi_set: set[int] = set()
        for req in chunk_requests:
            # Parse fi from "gen:func={fi}:call={ci}"
            cid = req.custom_id
            try:
                fi_part = cid.split(":")[1]  # "func={fi}"
                fi_val = int(fi_part.split("=")[1])
                chunk_fi_set.add(fi_val)
            except (IndexError, ValueError):
                pass

        chunk_fi_list = sorted(chunk_fi_set)
        if not chunk_fi_list:
            continue

        chunk_base_fi = chunk_fi_list[0]
        chunk_function_dicts = [functions[fi] for fi in chunk_fi_list]

        # Step 3b-e — Embed + build FunctionMldResults for this chunk's functions.
        chunk_results = _build_function_mld_results_from_gen(
            gen_results,
            chunk_function_dicts,
            max_batches=max_batches,
            func_prompt_used=func_prompt_used,
            func_base_fi=chunk_base_fi,
            dispatch=dispatch,
        )

        all_results.extend(chunk_results)
        processed_fi += len(chunk_results)

        # Step 3e — Fire the callback so the caller can upsert + write SFT.
        if on_chunk_complete is not None:
            on_chunk_complete(chunk_results, chunk_function_dicts)

    _emit_convergence_summary(all_results, verbose=verbose)
    return all_results


# ---------------------------------------------------------------------------
# Self-test: chunking path end-to-end (v0.3 M1)
# ---------------------------------------------------------------------------

def _self_test_chunking() -> None:
    """Exercise the chunked-pipelined generation path with N=250 trivial requests.

    Generates 250 GenerationRequest objects (forces 3 chunks of 100/100/50),
    calls run_batch_generation with dispatch='batch', and asserts:
      - len(results) == 250
      - Each result's custom_id matches its positional index in the input list.

    Prints "PASS chunking N=250 chunks=3" on success.
    Raises AssertionError on failure.
    """
    n = 250
    expected_chunks = (n + BATCH_CHUNK_SIZE - 1) // BATCH_CHUNK_SIZE  # ceiling div = 3

    # Build trivial generation requests — all identical preamble/payload, unique custom_id.
    requests = [
        GenerationRequest(
            custom_id=f"selftest:{i}",
            cached_preamble="You are a test assistant. Reply with three short drafts.",
            payload=f"Test request number {i}. Describe what the number {i} is in one sentence.",
            model="gpt-4.1-nano",
            max_tokens=100,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "answer",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "draft_1": {"type": "string"},
                            "draft_2": {"type": "string"},
                            "draft_3": {"type": "string"},
                        },
                        "required": ["draft_1", "draft_2", "draft_3"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        )
        for i in range(n)
    ]

    # Verify _chunk_requests produces the expected chunk count.
    raw_reqs = [{"custom_id": r.custom_id} for r in requests]
    chunks = _chunk_requests(raw_reqs)
    assert len(chunks) == expected_chunks, (
        f"Expected {expected_chunks} chunks, got {len(chunks)}"
    )

    # Run the full batch path.
    results = run_batch_generation(requests)

    # Assertions.
    assert len(results) == n, f"Expected {n} results, got {len(results)}"
    for pos, result in enumerate(results):
        expected_id = f"selftest:{pos}"
        assert result.custom_id == expected_id, (
            f"Position {pos}: expected custom_id={expected_id!r}, got {result.custom_id!r}"
        )

    print(f"PASS chunking N={n} chunks={expected_chunks}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="batch.py utilities")
    parser.add_argument(
        "--self-test-chunking",
        action="store_true",
        help="Run end-to-end self-test of the chunked-pipelined generation path (N=250).",
    )
    args = parser.parse_args()

    if args.self_test_chunking:
        _self_test_chunking()
    else:
        parser.print_help()
