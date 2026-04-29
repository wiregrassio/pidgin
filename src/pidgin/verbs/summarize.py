"""pidgin summarize <path|->: emit a single-file MLD summary to stdout.

DP4 (v0.3): chunked-summary path is experimental. Multi-file and
directory summarize are deferred to v0.4.
"""

# MODULE: verbs.summarize
# DOES: Summarise a single source file to stdout in markdown (default) or XML.
#       Single-pass for files under CONTEXT_BUDGET_TOKENS; chunked (experimental,
#       DP4) for larger files — splits by AST top-level units, summarises each
#       chunk, then summarises the summaries (one level of recursion).
# EMITS: Markdown or XML summary to stdout; never writes to the nest.
# READS: args.path (str) or stdin when path == '-'.
# IMPLEMENTS: single-pass and chunked summarise modes; AST-based chunking for .py.
# DEPENDS: pidgin.utils.api; ast, sys, pathlib.

import sys
import ast
from pathlib import Path

CONTEXT_BUDGET_TOKENS = 80_000   # safe single-pass cutoff for gpt-4.1-nano

PROMPT_HEADER_MD = """You are summarising a source file for a developer.
Output: a markdown document with these sections:

# <filename>
## Role
<one-paragraph: what the file does and why it exists>
## Public Surface
<bulleted list of public functions/classes with one-sentence descriptions>
## Notes
<anything notable: unusual patterns, dependencies, side effects>

Do not include code blocks. Do not invent. Source follows.
"""

PROMPT_HEADER_XML = """Output XML matching this shape:

<file path="...">
  <role>...</role>
  <surface>
    <symbol kind="function|class" name="..."><desc>...</desc></symbol>
  </surface>
  <notes>...</notes>
</file>

Do not include the file's source verbatim in your response. Source follows.
"""


def _read_input(path: str) -> tuple[str, str]:
    """Return (display_name, contents). path == '-' reads stdin."""
    if path == "-":
        return ("<stdin>", sys.stdin.read())
    p = Path(path)
    return (p.name, p.read_text())


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)  # rough; tiktoken not required


def _summarise_single(name: str, text: str, *, mode: str) -> str:
    """Call gpt-4.1-nano with a one-shot summary prompt and return the response."""
    from pidgin.utils.api import ensure_api_key, openai_client
    ensure_api_key("OPENAI_API_KEY")
    header = PROMPT_HEADER_XML if mode == "xml" else PROMPT_HEADER_MD
    prompt = f"{header}\n--- {name} ---\n{text}\n"
    client = openai_client()
    resp = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.0,
    )
    return resp.choices[0].message.content


def _split_by_ast(name: str, text: str) -> list[tuple[str, str]]:
    """Return [(chunk_label, chunk_text)] for top-level AST units in a
    Python file. For non-Python or parse-failure, fall back to
    fixed-size character chunks."""
    if not name.endswith(".py"):
        return _fixed_chunks(name, text)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _fixed_chunks(name, text)
    lines = text.splitlines(keepends=True)
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = node.end_lineno
            label = f"{node.__class__.__name__}:{node.name}"
            out.append((label, "".join(lines[start:end])))
    if not out:
        return [(name, text)]
    return out


def _fixed_chunks(name: str, text: str, *, size: int = 60_000) -> list[tuple[str, str]]:
    """Split text into fixed-size character chunks for non-Python or unparseable files."""
    out = []
    for i, j in enumerate(range(0, len(text), size)):
        out.append((f"{name}:chunk{i}", text[j:j+size]))
    return out


def _summarise_chunked(name: str, text: str, *, mode: str) -> str:
    """Experimental (DP4). Summarise each chunk, then summarise the
    chunk summaries. Recursion is capped at one level — the combined
    chunk summaries are always passed as a single final summarise call."""
    parts = _split_by_ast(name, text)
    chunk_summaries: list[str] = []
    for label, chunk_text in parts:
        chunk_summaries.append(_summarise_single(label, chunk_text, mode="markdown"))
    combined = "\n\n".join(f"### {p[0]}\n{s}" for p, s in zip(parts, chunk_summaries))
    return _summarise_single(name + " (combined)", combined, mode=mode)


def run(args) -> int:
    """Run the summarize verb.

    Reads the target file (or stdin), selects single-pass or chunked strategy
    based on estimated token count, calls gpt-4.1-nano, and writes the summary
    to stdout. Never writes to the nest.
    """
    name, text = _read_input(args.path)
    mode = "xml" if args.xml else "markdown"
    if _estimate_tokens(text) <= CONTEXT_BUDGET_TOKENS:
        out = _summarise_single(name, text, mode=mode)
    else:
        out = _summarise_chunked(name, text, mode=mode)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0
