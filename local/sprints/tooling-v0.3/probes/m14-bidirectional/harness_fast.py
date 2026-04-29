#!/usr/bin/env python3
"""v0.3 M16 harness: 5 probes × 6 runs = 30 records.

Uses the M15 tool-use generation approach (no JSON-envelope truncation).
One body per run; records parses_as_python, matches_reference, and truncated
per run. Budget fixed at BIDIRECTIONAL_MAX_TOKENS for all probes.

Results written to results.json alongside this file.
"""
import ast, json, os, sys, time
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

RUNS_PER_PROBE = 6
GEN_MODEL = "gpt-4.1-nano"

# Import token budget constant; define fallback in case import fails.
try:
    from pidgin.pipeline.batch import BIDIRECTIONAL_MAX_TOKENS
except ImportError:
    BIDIRECTIONAL_MAX_TOKENS = 1000

# Tool-use definition for emit_code.
# Tool-use does not require a closing JSON brace, so the model can stream
# the full function body without running out of budget mid-envelope.
EMIT_CODE_TOOLS = [{
    "type": "function",
    "function": {
        "name": "emit_code",
        "description": "Emit the function body for the described function.",
        "parameters": {
            "type": "object",
            "properties": {
                "body": {
                    "type": "string",
                    "description": "Complete function body.",
                },
            },
            "required": ["body"],
        },
    },
}]
EMIT_CODE_TOOL_CHOICE = {"type": "function", "function": {"name": "emit_code"}}


# ---------------------------------------------------------------------------
# Reference bodies (loaded once at startup)
# ---------------------------------------------------------------------------

def _load_reference_bodies() -> dict[str, str]:
    """Load the reference function body for each probe.

    Returns a dict mapping probe_id to the reference body string.
    Prefers an inline `reference_body` field on the probe entry in
    probes.json when present (allows per-probe canonicalisation —
    e.g. stripping a docstring rule 5 forbids, or adding the local
    import rule 8 mandates). Falls back to extracting from source:
    P1: embed_for_store from pidgin/utils/api.py
    P2: MAIN_SRC literal from tools/mld/probe.py (toy argparse-and-print)
    P3: APPLY_SRC from tools/mld/probe.py
    P4: MERGE_SRC from tools/mld/probe.py
    P5: antipode_test from pidgin/pipeline/geometry.py
    """
    refs: dict[str, str] = {}

    # First pass — honor inline reference_body fields from probes.json.
    probes = json.loads(PROBES_JSON.read_text())
    inline_overrides: dict[str, str] = {
        p["probe_id"]: p["reference_body"]
        for p in probes
        if isinstance(p.get("reference_body"), str) and p["reference_body"].strip()
    }

    # P1: embed_for_store — extract from pidgin/utils/api.py
    api_src = (_PROJECT_ROOT / "pidgin" / "utils" / "api.py").read_text()
    refs["P1_embed_for_store"] = _extract_function(api_src, "embed_for_store")

    # P2: MAIN_SRC literal from tools/mld/probe.py
    # The toy is a 5-line argparse-and-print function stored as a string
    # constant.  We extract the literal rather than the probe.main function
    # so the reference matches what M3 actually probed.
    probe_src = (_PROJECT_ROOT / "tools" / "mld" / "probe.py").read_text()
    refs["P2_main"] = _extract_probe_literal(probe_src, "MAIN_SRC")

    # P3: apply from tools/mld/probe.py APPLY_SRC literal
    refs["P3_apply"] = _extract_probe_literal(probe_src, "APPLY_SRC")

    # P4: merge from tools/mld/probe.py MERGE_SRC literal
    refs["P4_merge"] = _extract_probe_literal(probe_src, "MERGE_SRC")

    # P5: antipode_test from pidgin/pipeline/geometry.py
    geo_src = (_PROJECT_ROOT / "pidgin" / "pipeline" / "geometry.py").read_text()
    refs["P5_antipode_test"] = _extract_function(geo_src, "antipode_test")

    # Apply inline overrides last so probes.json wins over source extraction.
    refs.update(inline_overrides)

    return refs


def _extract_function(source: str, name: str) -> str:
    """Extract a top-level function definition by name from source text.

    Returns everything from 'def <name>' (or 'async def <name>') through
    the last line of the function body, identified by indentation.
    Returns empty string if not found.
    """
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"def {name}(") or line.startswith(f"async def {name}("):
            start = i
            break
    if start is None:
        return ""
    result = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line[0].isspace():
            break
        result.append(line)
    # Strip trailing blank lines
    while result and not result[-1].strip():
        result.pop()
    return "\n".join(result)


def _extract_probe_literal(source: str, var_name: str) -> str:
    """Extract a triple-quoted string literal assigned to var_name.

    Finds the assignment line, then collects lines until the closing triple
    quote.  Returns the stripped inner content (the function definition).
    """
    lines = source.splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{var_name} = '''") or stripped.startswith(f'{var_name} = """'):
            start = i
            break
    if start is None:
        return ""

    # Determine which triple-quote delimiter is used
    delim = "'''" if "'''" in lines[start] else '"""'

    # Collect the literal content
    collected: list[str] = []
    # Check if opening and closing are on the same line
    after_open = lines[start].split(delim, 1)[1]
    if delim in after_open:
        return after_open.split(delim)[0].strip()

    collected.append(after_open)
    for line in lines[start + 1:]:
        if delim in line:
            collected.append(line.split(delim)[0])
            break
        collected.append(line)

    # The literal includes a leading newline; strip it
    text = "\n".join(collected)
    text = text.strip()
    return text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _looks_complete(body: str) -> bool:
    """Return True if the body appears syntactically complete.

    Uses ast.parse as the completeness check — if it parses, it is complete.
    """
    if not body or not body.strip():
        return False
    try:
        ast.parse(body.strip())
        return True
    except SyntaxError:
        return False


def _normalize_body(body: str) -> str:
    """Strip whitespace normalization for comparison.

    Strips leading/trailing whitespace and normalizes internal blank lines
    to a single blank line.
    """
    lines = body.strip().splitlines()
    result: list[str] = []
    prev_blank = False
    for line in lines:
        if not line.strip():
            if not prev_blank:
                result.append("")
            prev_blank = True
        else:
            result.append(line.rstrip())
            prev_blank = False
    return "\n".join(result)


def _matches_reference(body: str, reference: str) -> bool:
    """Return True if body is semantically equivalent to reference.

    For parseable bodies: compare AST dumps (ignoring line numbers).
    This catches trivially equivalent rewrites — different whitespace,
    equivalent expressions.

    Falls back to normalized-string comparison if either body fails to
    parse.
    """
    if not body or not reference:
        return False
    try:
        body_ast = ast.dump(ast.parse(body.strip()), include_attributes=False)
        ref_ast = ast.dump(ast.parse(reference.strip()), include_attributes=False)
        return body_ast == ref_ast
    except SyntaxError:
        pass
    return _normalize_body(body) == _normalize_body(reference)


def generate_one(client, prompt: str, budget: int) -> str:
    """Issue one tool-use generation call and return the function body.

    Sends prompt as a user message; forces emit_code tool call; parses
    the tool_calls[0].function.arguments JSON and returns the body field.
    Returns empty string on any error.
    """
    try:
        resp = client.chat.completions.create(
            model=GEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            tools=EMIT_CODE_TOOLS,
            tool_choice=EMIT_CODE_TOOL_CHOICE,
            max_tokens=budget,
            temperature=0.7,
        )
        call = resp.choices[0].message.tool_calls[0]
        body = json.loads(call.function.arguments)["body"]
        return body
    except Exception:
        return ""


def main():
    import argparse
    from openai import OpenAI
    from pidgin.prompts.templates import assemble_xml_prompt

    parser = argparse.ArgumentParser(description="v0.3 M16 bidirectional probe harness")
    args = parser.parse_args()

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    probes = json.loads(PROBES_JSON.read_text())
    refs = _load_reference_bodies()

    print(f"[harness_fast] {len(probes)} probes × {RUNS_PER_PROBE} runs = "
          f"{len(probes) * RUNS_PER_PROBE} records")
    print(f"[harness_fast] budget={BIDIRECTIONAL_MAX_TOKENS}, model={GEN_MODEL}")

    # Assemble prompts per probe
    probe_prompts: dict[str, str] = {}
    for probe in probes:
        asm = assemble_xml_prompt(str(EXPAND_XML), {
            "description": probe["description"],
            "function_signature": probe["function_signature"],
        })
        probe_prompts[probe["probe_id"]] = asm.cached_preamble + "\n" + asm.payload

    t0 = time.time()
    results: list[dict] = []
    total_calls = len(probes) * RUNS_PER_PROBE
    done = 0

    print(f"[harness_fast] Dispatching {total_calls} generation calls...")
    for probe in probes:
        pid = probe["probe_id"]
        prompt = probe_prompts[pid]
        ref = refs.get(pid, "")

        for run_idx in range(RUNS_PER_PROBE):
            body = generate_one(client, prompt, BIDIRECTIONAL_MAX_TOKENS)
            truncated = not _looks_complete(body)
            try:
                ast.parse(body.strip())
                parses = True
            except SyntaxError:
                parses = False
            except Exception:
                parses = False
            matches = _matches_reference(body, ref)
            results.append({
                "probe_id": pid,
                "run": run_idx,
                "generated_body": body,
                "parses_as_python": parses,
                "matches_reference": matches,
                "truncated": truncated,
            })
            done += 1
            status = ("MATCH" if matches else ("PARSE" if parses else "FAIL"))
            print(f"  [{done:02d}/{total_calls}] {pid} r={run_idx}: {status}")

    RESULTS_JSON.write_text(json.dumps({"runs": results}, indent=2))
    total = round(time.time() - t0, 2)
    print(f"\n[harness_fast] {len(results)} records written to {RESULTS_JSON} in {total:.1f}s")

    # Per-probe summary
    print("\n--- Per-probe summary ---")
    for probe in probes:
        pid = probe["probe_id"]
        probe_runs = [r for r in results if r["probe_id"] == pid]
        parses_count = sum(1 for r in probe_runs if r["parses_as_python"])
        matches_count = sum(1 for r in probe_runs if r["matches_reference"])
        truncated_count = sum(1 for r in probe_runs if r["truncated"])
        print(f"  {pid}: parses={parses_count}/{RUNS_PER_PROBE} "
              f"matches={matches_count}/{RUNS_PER_PROBE} "
              f"truncated={truncated_count}/{RUNS_PER_PROBE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
