#!/usr/bin/env python3
"""
Convergence calibration experiment.

Run 25 calls × 4 temperatures × 120 functions = 12,000 API calls.
Each call produces 3 drafts = 36,000 candidates.
Embed all 36,000. Save everything.

From 100 candidates per function, simulate any smaller N by subsampling.
You can simulate down. You cannot simulate up. Start at 11.

Estimated cost: ~$15-20 at gpt-4.1-nano rates.
"""

import json
import os
import sys
import time
import asyncio
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field, asdict

# Load API key
from dotenv import load_dotenv
load_dotenv()
load_dotenv(os.path.expanduser("~/Desktop/fe-toolkit/.env"))

from openai import OpenAI

TEMPERATURES = [0.3, 0.7, 1.0, 1.5]
CALLS_PER_TEMP = 25
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 256
GEN_MODEL = "gpt-4.1-nano"
OUTPUT_FILE = "calibration-data.json"

# Load converge.xml preamble
CONVERGE_PATH = Path(__file__).parent.parent / "src" / "pidgin" / "prompts" / "converge.xml"


def load_converge_template():
    from pidgin.prompts.templates import assemble_xml_prompt
    return CONVERGE_PATH


def build_prompt(fn: dict) -> tuple[str, str]:
    """Assemble preamble + payload for a function."""
    from pidgin.prompts.templates import assemble_xml_prompt
    try:
        assembled = assemble_xml_prompt(
            str(CONVERGE_PATH),
            {
                "file": fn.get("file", ""),
                "name": fn.get("name", ""),
                "line_start": str(fn.get("line_start", "")),
                "function_body": fn.get("body", ""),
            },
        )
        return assembled.cached_preamble, assembled.payload
    except Exception as e:
        print(f"  WARNING: prompt assembly failed for {fn.get('name', '?')}: {e}")
        return "", fn.get("body", "")


def generate_one(client, preamble, payload, temperature):
    """One sync generation call. Returns list of draft strings."""
    try:
        resp = client.chat.completions.create(
            model=GEN_MODEL,
            messages=[
                {"role": "system", "content": preamble},
                {"role": "user", "content": payload},
            ],
            max_tokens=500,
            temperature=temperature,
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
        content = resp.choices[0].message.content
        parsed = json.loads(content)
        return [parsed.get("draft_1", ""), parsed.get("draft_2", ""), parsed.get("draft_3", "")]
    except Exception as e:
        print(f"  gen error (temp={temperature}): {e}")
        return []


def embed_batch(client, texts, batch_size=100):
    """Embed a list of texts in batches. Returns list of vectors."""
    vectors = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        try:
            resp = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=chunk,
                dimensions=EMBEDDING_DIM,
                encoding_format="float",
            )
            for item in resp.data:
                vectors.append(item.embedding)
        except Exception as e:
            print(f"  embed error at batch {i}: {e}")
            vectors.extend([None] * len(chunk))
    return vectors


def spherical_variance(vectors):
    """1 - ||mean(unit_vectors)||"""
    arr = np.asarray(vectors, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    unit = arr / norms
    mean_vec = unit.mean(axis=0)
    return float(1.0 - np.linalg.norm(mean_vec))


def main():
    from pidgin.utils.parser import extract_public_functions

    client = OpenAI()

    # Discover functions
    funcs = extract_public_functions(".")
    print(f"Discovered {len(funcs)} functions")
    print(f"Plan: {len(funcs)} × {len(TEMPERATURES)} temps × {CALLS_PER_TEMP} calls = {len(funcs) * len(TEMPERATURES) * CALLS_PER_TEMP} API calls")
    print(f"Candidates: {len(funcs) * len(TEMPERATURES) * CALLS_PER_TEMP * 3}")
    print()

    all_data = []
    total_calls = 0
    total_start = time.monotonic()

    for fi, fn in enumerate(funcs):
        fn_name = fn.get("name", "?")
        preamble, payload = build_prompt(fn)
        if not preamble:
            print(f"[{fi+1}/{len(funcs)}] {fn_name} — SKIP (no preamble)")
            continue

        fn_record = {
            "fi": fi,
            "name": fn_name,
            "file": fn.get("file", ""),
            "body_len": len(fn.get("body", "")),
            "candidates": [],  # list of {temp, call, draft, text, vector}
        }

        print(f"[{fi+1}/{len(funcs)}] {fn_name}", end="", flush=True)

        for temp in TEMPERATURES:
            for call_idx in range(CALLS_PER_TEMP):
                drafts = generate_one(client, preamble, payload, temp)
                total_calls += 1
                for draft_idx, text in enumerate(drafts, start=1):
                    if text:
                        fn_record["candidates"].append({
                            "temp": temp,
                            "call": call_idx,
                            "draft": draft_idx,
                            "text": text,
                            "vector": None,  # filled after embedding
                        })

            print(f" t={temp}:{len([c for c in fn_record['candidates'] if c['temp']==temp])}",
                  end="", flush=True)

        # Embed all candidates for this function
        texts = [c["text"] for c in fn_record["candidates"]]
        if texts:
            vectors = embed_batch(client, texts)
            for c, v in zip(fn_record["candidates"], vectors):
                c["vector"] = v

        # Quick analysis per function
        for temp in TEMPERATURES:
            for draft_num in [1, 2, 3]:
                vecs = [c["vector"] for c in fn_record["candidates"]
                        if c["temp"] == temp and c["draft"] == draft_num and c["vector"]]
                if len(vecs) >= 3:
                    sv = spherical_variance(vecs)
                    fn_record.setdefault("sv_by_temp_draft", {})[f"t{temp}_d{draft_num}"] = round(sv, 6)

        all_data.append(fn_record)

        elapsed = time.monotonic() - total_start
        rate = total_calls / elapsed if elapsed > 0 else 0
        remaining_calls = (len(funcs) - fi - 1) * len(TEMPERATURES) * CALLS_PER_TEMP
        eta = remaining_calls / rate if rate > 0 else 0
        print(f" | {total_calls} calls | {rate:.1f}/s | ~{int(eta//60)}m left")

    # Save everything
    print(f"\nSaving {len(all_data)} functions to {OUTPUT_FILE}...")

    # Strip vectors for JSON (save separately as numpy)
    vectors_flat = []
    vector_index = []  # (fi, candidate_idx)
    for rec in all_data:
        for ci, c in enumerate(rec["candidates"]):
            if c["vector"]:
                vectors_flat.append(c["vector"])
                vector_index.append((rec["fi"], ci))
            c["vector"] = c["vector"] is not None  # replace with bool

    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_data, f, indent=2)

    np.savez_compressed(
        "calibration-vectors.npz",
        vectors=np.array(vectors_flat, dtype=np.float32),
        index=np.array(vector_index, dtype=np.int32),
    )

    # Summary
    print(f"\nDone. {total_calls} calls, {len(vectors_flat)} vectors.")
    print(f"Saved: {OUTPUT_FILE} (metadata) + calibration-vectors.npz (embeddings)")
    print(f"\nQuick sv summary (temp × draft):")
    print(f"{'func':<30} {'t0.3_d1':>8} {'t0.3_d3':>8} {'t0.7_d1':>8} {'t0.7_d3':>8} {'t1.0_d1':>8} {'t1.0_d3':>8} {'t1.5_d1':>8} {'t1.5_d3':>8}")
    for rec in all_data[:20]:  # first 20
        svs = rec.get("sv_by_temp_draft", {})
        cols = []
        for temp in TEMPERATURES:
            for d in [1, 3]:
                v = svs.get(f"t{temp}_d{d}", None)
                cols.append(f"{v:.4f}" if v is not None else "   n/a")
        print(f"{rec['name']:<30} {'  '.join(cols)}")


if __name__ == "__main__":
    main()
