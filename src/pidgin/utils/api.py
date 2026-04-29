#!/usr/bin/env python3
# MODULE: api
# DOES: Provide pidgin-layer embedding constants, a lazy OpenAI client factory,
#       and re-exported LLM types (CostSummary, GenerateResult) with self-contained
#       implementations of generate, cost_totals, and reset_cost_totals.
# EMITS: EMBEDDING_MODEL, EMBEDDING_DIM, openai.OpenAI client instance,
#        CostSummary, GenerateResult, generate, embed_for_store
# READS: OPENAI_API_KEY from environment (env var first, then .env discovery)
# IMPLEMENTS: Decision 6 — text-embedding-3-small at 256 dimensions
# DEPENDS: openai, python-dotenv

import asyncio
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from dotenv import load_dotenv

_DOTENV_LOADED = False


def ensure_api_key(name: str) -> str:
    """Resolve an API key. Order:
       1. os.environ[name].
       2. load_dotenv() (no path; finds .env in cwd or parents) once
          per process, then os.environ[name].
       3. Print an error and sys.exit(1).
    """
    global _DOTENV_LOADED
    val = os.environ.get(name)
    if val:
        return val
    if not _DOTENV_LOADED:
        load_dotenv()  # walks up from cwd
        _DOTENV_LOADED = True
        val = os.environ.get(name)
        if val:
            return val
    print(f"[pidgin] FATAL: {name} not set. Export it in your shell or "
          f"place a .env file in this directory or any parent.",
          file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Canonical embedding constants (Decision 6)
# One provider, one model, one dimension.
# Matches STORE_EMBED_MODEL and STORE_EMBED_DIM — do not fork or parameterize.
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIM: int = 256


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_openai_client():
    """Create and return a synchronous openai.OpenAI client using OPENAI_API_KEY.

    Lazy construction — client is not created at import time.
    """
    import os
    import openai
    return openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# Alias for callers that import openai_client() by that name (M7+).
openai_client = get_openai_client


# ---------------------------------------------------------------------------
# Canonical store embedding constants
# One provider, one model, one dimension. Do not parameterize or fork.
# ---------------------------------------------------------------------------

STORE_EMBED_MODEL: str = "text-embedding-3-small"
STORE_EMBED_DIM: int = 256


async def embed_text(
    text: "str | list[str]",
    dim: int = 1536,
    model: str = "text-embedding-3-small",
) -> "list[list[float]]":
    """Embed one or more strings. Always returns a list of float vectors."""
    import openai

    client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    inputs = [text] if isinstance(text, str) else list(text)

    for attempt in range(3):
        try:
            resp = await client.embeddings.create(model=model, input=inputs, dimensions=dim)
            break
        except Exception as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(1.0 * (2 ** attempt))

    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]


async def embed_for_store(text: "str | list[str]") -> "list[list[float]]":
    """Embed one or more strings using the canonical store configuration (text-embedding-3-small, 256 dimensions)."""
    return await embed_text(text, dim=STORE_EMBED_DIM, model=STORE_EMBED_MODEL)


# --- IV patch v0.3: generate, cost_totals, reset_cost_totals lifted in-place; dependency eliminated ---

# Rate tables: $ per million tokens
RATES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_write": 1.25,
    },
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_write": 3.75,
    },
    "claude-opus-4-7": {
        "input": 5.00,
        "output": 25.00,
        "cache_read": 0.50,
        "cache_write": 6.25,
    },
    "gpt-5-nano": {
        "input": 0.05,
        "output": 0.40,
        "cache_read": 0.005,
        "cache_write": 0.0,
    },
    "gpt-4.1-nano": {
        "input": 0.10,
        "output": 0.40,
        "cache_read": 0.025,
        "cache_write": 0.0,
    },
    "text-embedding-3-small": {
        "input": 0.02,
        "output": 0.0,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
}


@dataclass
class CostSummary:
    """Accumulated cost and token usage across all calls in this session."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    embedding_tokens: int = 0
    dollars: float = 0.0
    model_breakdown: dict = field(default_factory=dict)


@dataclass
class GenerateResult:
    """Result of a single generate() call."""
    text: "str | None"
    structured: "dict | None"
    usage: dict
    model: str


# Module-level cost accumulator (protected by threading.Lock for sync access)

_cost_lock = threading.Lock()
_cost_totals = CostSummary()


def _dollars_for(model: str, input_tok: int, output_tok: int,
                 cache_read: int = 0, cache_creation: int = 0) -> float:
    """Compute dollar cost for a call using the RATES table."""
    r = RATES.get(model, {})
    m = 1_000_000
    return (
        input_tok * r.get("input", 0.0) / m
        + output_tok * r.get("output", 0.0) / m
        + cache_read * r.get("cache_read", 0.0) / m
        + cache_creation * r.get("cache_write", 0.0) / m
    )


def _record_cost(model: str, input_tok: int, output_tok: int,
                 cache_read: int = 0, cache_creation: int = 0,
                 embedding_tok: int = 0) -> None:
    """Thread-safe update of module-level _cost_totals."""
    dollars = _dollars_for(model, input_tok, output_tok, cache_read, cache_creation)
    if embedding_tok:
        r = RATES.get(model, {})
        dollars += embedding_tok * r.get("input", 0.0) / 1_000_000

    with _cost_lock:
        _cost_totals.input_tokens += input_tok
        _cost_totals.output_tokens += output_tok
        _cost_totals.cache_read_tokens += cache_read
        _cost_totals.cache_creation_tokens += cache_creation
        _cost_totals.embedding_tokens += embedding_tok
        _cost_totals.dollars += dollars

        mb = _cost_totals.model_breakdown.setdefault(model, {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "embedding_tokens": 0,
            "dollars": 0.0,
            "cache_hit_rate": 0.0,
        })
        mb["input_tokens"] += input_tok
        mb["output_tokens"] += output_tok
        mb["cache_read_tokens"] += cache_read
        mb["cache_creation_tokens"] += cache_creation
        mb["embedding_tokens"] += embedding_tok
        mb["dollars"] += dollars

        total_prompt = mb["input_tokens"] + mb["cache_read_tokens"] + mb["cache_creation_tokens"]
        if total_prompt > 0:
            mb["cache_hit_rate"] = mb["cache_read_tokens"] / total_prompt


def _is_retryable(exc: Exception) -> bool:
    # Return True if the exception warrants a retry attempt.
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    msg = str(exc).lower()
    return (
        status == 429
        or (status is not None and 500 <= int(status) < 600)
        or "rate limit" in msg
        or "overloaded" in msg
    )


def _token_limit_kwarg(model: str, n: int) -> dict[str, int]:
# Map model family to the correct token-limit parameter name.
#
# Legacy GPT-3.5 and GPT-4 (non-o) predate max_completion_tokens (introduced
# with the o1 series, Sep 2024). All current-gen models (o-series, gpt-4o,
# gpt-5+) prefer max_completion_tokens; o-series rejects max_tokens outright.
# Unknown future models default to max_completion_tokens (the safe forward path).
    if model.startswith(("gpt-3.5", "gpt-4-", "gpt-4.")):
        return {"max_tokens": n}
    return {"max_completion_tokens": n}


def cost_totals() -> CostSummary:
    # Deeply copy and return the accumulated session cost totals under lock.
    import copy
    with _cost_lock:
        return copy.deepcopy(_cost_totals)


def reset_cost_totals() -> None:
    # Reset all cost totals to zero.
    global _cost_totals
    with _cost_lock:
        _cost_totals = CostSummary()


async def generate(
    prompt: str,
    content: str,
    model: str = "claude-haiku-4-5",
    temperature: float = 0.8,
    max_tokens: int = 512,
    schema: "dict | None" = None,
    cache: bool = True,
    n: int = 1,
) -> "GenerateResult | list[GenerateResult]":
    """Generate text or structured output from an LLM. Returns list when n > 1."""
    from typing import Any

    if model.startswith("claude-"):
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        system = (
            [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]
            if cache
            else [{"type": "text", "text": prompt}]
        )
        messages = [{"role": "user", "content": content}]
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": messages,
        }
        if schema is not None:
            kwargs["tools"] = [
                {
                    "name": "answer",
                    "description": "Produce a structured answer conforming to the provided schema.",
                    "input_schema": schema,
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": "answer"}

        async def _one_anthropic_call() -> GenerateResult:
            for attempt in range(3):
                try:
                    resp = await client.messages.create(**kwargs)
                    break
                except Exception as exc:
                    if not _is_retryable(exc) or attempt == 2:
                        raise
                    await asyncio.sleep(1.0 * (2 ** attempt))

            u = resp.usage
            input_tok = getattr(u, "input_tokens", 0)
            output_tok = getattr(u, "output_tokens", 0)
            cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(u, "cache_creation_input_tokens", 0) or 0
            _record_cost(model, input_tok, output_tok, cache_read, cache_creation)

            usage = {
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cache_read": cache_read,
                "cache_creation": cache_creation,
            }
            structured = None
            text = None
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use" and block.name == "answer":
                    structured = block.input
                    break
                if getattr(block, "type", None) == "text":
                    text = block.text
            return GenerateResult(text=text, structured=structured, usage=usage, model=model)

        if n == 1:
            return await _one_anthropic_call()

        # n > 1: warm cache with first request, then dispatch remaining concurrently
        first = await _one_anthropic_call()
        remaining = list(await asyncio.gather(*[_one_anthropic_call() for _ in range(n - 1)]))
        return [first] + remaining

    elif model.startswith("gpt-"):
        import openai
        import json as _json

        client = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ]
        kwargs = {
            "model": model,
            **_token_limit_kwarg(model, max_tokens),
            "messages": messages,
            "n": n,
        }
        # gpt-5-nano is an o-series-style reasoning model that handles its own
        # temperature internally and rejects any explicit temperature kwarg
        # (returns 400 BadRequest for any value other than the default).
        # Operator pre-authorized this fix: omit temperature for gpt-5* models.
        if not model.startswith("gpt-5"):
            kwargs["temperature"] = temperature
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": schema, "strict": True},
            }

        for attempt in range(3):
            try:
                resp = await client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if not _is_retryable(exc) or attempt == 2:
                    raise
                await asyncio.sleep(1.0 * (2 ** attempt))

        u = resp.usage
        input_tok = getattr(u, "prompt_tokens", 0) or 0
        output_tok = getattr(u, "completion_tokens", 0) or 0
        cached_tok = 0
        if hasattr(u, "prompt_tokens_details") and u.prompt_tokens_details:
            cached_tok = getattr(u.prompt_tokens_details, "cached_tokens", 0) or 0
        _record_cost(model, input_tok, output_tok, cache_read=cached_tok)

        base_usage = {
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "cache_read": cached_tok,
            "cache_creation": 0,
        }

        def _parse(choice) -> GenerateResult:
            msg = choice.message
            if schema is not None:
                try:
                    structured = _json.loads(msg.content)
                except Exception:
                    structured = None
                return GenerateResult(text=None, structured=structured, usage=base_usage, model=model)
            return GenerateResult(text=msg.content, structured=None, usage=base_usage, model=model)

        if n == 1:
            return _parse(resp.choices[0])
        return [_parse(c) for c in resp.choices]

    else:
        raise ValueError(f"Unknown model prefix — cannot route: {model!r}")
