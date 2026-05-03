import asyncio
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RATES: dict[str, dict[str, float]] = {
    "gpt-5.5": {
        "input": 5.00,
        "output": 30.00,
        "cache_read": 0.50,
        "cache_write": 0.0,
    },
    "gpt-5.4": {
        "input": 2.50,
        "output": 15.00,
        "cache_read": 0.25,
        "cache_write": 0.0,
    },
    "gpt-5.4-mini": {
        "input": 0.75,
        "output": 4.50,
        "cache_read": 0.075,
        "cache_write": 0.0,
    },
    "gpt-5.4-nano": {
        "input": 0.20,
        "output": 1.25,
        "cache_read": 0.02,
        "cache_write": 0.0,
    },
    "gpt-4.1": {
        "input": 2.00,
        "output": 8.00,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
    "gpt-4.1-mini": {
        "input": 0.40,
        "output": 1.60,
        "cache_read": 0.0,
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

def _resolve_openai_key() -> str:
    """Resolve OPENAI_API_KEY from env or .env at the repo root.

    Order: os.environ first; then walk up from cwd to find a .git
    directory and read .env if present. Raises RuntimeError with a
    descriptive message if neither yields a key.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists():
            env_file = parent / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    # Tolerate `export OPENAI_API_KEY=...` (FLAW-12).
                    if line.startswith("export "):
                        line = line[7:]
                    if line.startswith("OPENAI_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    raise RuntimeError(
        "OPENAI_API_KEY not set in environment and no value found in "
        ".env at the repo root."
    )


@dataclass
class CostSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    embedding_tokens: int = 0
    dollars: float = 0.0
    model_breakdown: dict[str, dict] = field(default_factory=dict)
@dataclass
class GenerateResult:
    text: str | None
    structured: dict | None
    usage: dict
    model: str
_cost_lock = threading.Lock()
_cost_totals = CostSummary()

def cost_totals() -> CostSummary:
    import copy
    with _cost_lock:
        return copy.deepcopy(_cost_totals)
def reset_cost_totals() -> None:
    global _cost_totals
    with _cost_lock:
        _cost_totals = CostSummary()
def _token_limit_kwarg(model: str, n: int) -> dict[str, int]:
    if model.startswith(("gpt-3.5", "gpt-4-", "gpt-4.")):
        return {"max_tokens": n}
    return {"max_completion_tokens": n}
def _dollars_for(model: str, input_tok: int, output_tok: int,
                 cache_read: int = 0, cache_creation: int = 0) -> float:
    r = RATES.get(model, {})
    m = 1_000_000
    uncached_input = max(input_tok - cache_read, 0)
    return (
        uncached_input * r.get("input", 0.0) / m
        + output_tok * r.get("output", 0.0) / m
        + cache_read * r.get("cache_read", 0.0) / m
        + cache_creation * r.get("cache_write", 0.0) / m
    )
def _record_cost(model: str, input_tok: int, output_tok: int,
                 cache_read: int = 0, cache_creation: int = 0,
                 embedding_tok: int = 0) -> None:
    dollars = _dollars_for(model, input_tok, output_tok,
                           cache_read=cache_read, cache_creation=cache_creation)
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

        total_prompt = mb["input_tokens"] + mb["cache_creation_tokens"]
        if total_prompt > 0:
            mb["cache_hit_rate"] = mb["cache_read_tokens"] / total_prompt
def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    msg = str(exc).lower()
    return (
        status == 429
        or (status is not None and 500 <= int(status) < 600)
        or "rate limit" in msg
        or "overloaded" in msg
    )
async def generate(
    prompt: str,
    content: str,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.8,
    max_tokens: int = 4096,
    schema: dict | None = None,
    n: int = 1,
    reasoning_effort: str | None = None,
) -> "GenerateResult | list[GenerateResult]":
    if model.startswith("gpt-"):
        import openai
        import json as _json

        client = openai.AsyncOpenAI(api_key=_resolve_openai_key())
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
        if model.startswith("gpt-5"):
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
        else:
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
async def generate_batch(
    prompt: str,
    contents: list[str],
    concurrency: int = 10,
    **generate_kwargs,
) -> "list[GenerateResult | list[GenerateResult]]":
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(c: str):
        async with sem:
            return await generate(prompt, c, **generate_kwargs)
    return list(await asyncio.gather(*[_bounded(c) for c in contents]))
async def embed_text(
    text: "str | list[str]",
    dim: int = 1536,
    model: str = "text-embedding-3-small",
) -> "list[list[float]]":
    import openai

    client = openai.AsyncOpenAI(api_key=_resolve_openai_key())
    inputs = [text] if isinstance(text, str) else text

    for attempt in range(3):
        try:
            resp = await client.embeddings.create(model=model, input=inputs, dimensions=dim)
            break
        except Exception as exc:
            if not _is_retryable(exc) or attempt == 2:
                raise
            await asyncio.sleep(1.0 * (2 ** attempt))

    total_tokens = getattr(resp.usage, "total_tokens", 0) or 0
    _record_cost(model, input_tok=0, output_tok=0, embedding_tok=total_tokens)

    data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in data]
STORE_EMBED_MODEL = "text-embedding-3-small"
STORE_EMBED_DIM = 256

async def embed_for_store(text: "str | list[str]") -> "list[list[float]]":
    return await embed_text(text, dim=STORE_EMBED_DIM, model=STORE_EMBED_MODEL)

def generate_sync(
    prompt: str,
    content: str,
    **kwargs,
) -> "GenerateResult | list[GenerateResult]":
    return asyncio.run(generate(prompt, content, **kwargs))
def embed_text_sync(
    text: "str | list[str]",
    **kwargs,
) -> "list[list[float]]":
    return asyncio.run(embed_text(text, **kwargs))


def embed_for_store_sync(text: "str | list[str]") -> "list[list[float]]":
    return asyncio.run(embed_for_store(text))


