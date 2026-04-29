# pidgin/verbs/query.py — wired in M12; extended in M13 for registry-aware multi-nest;
#                         extended in M7 for query normalisation via gpt-4.1-nano.

# MODULE: verbs.query
# DOES: Search one or more per-repo .pidgin/nest/ ChromaDB stores by
#       natural-language query. If a registry.json exists in cwd, searches all
#       registered nests and merges results by similarity. Falls back to a
#       single cwd-local nest when no registry is found.
#       Normalises the human query to an imperative form before embedding
#       unless --raw is passed.
# EMITS: Merged top-10 similarity hits to stdout; warnings for failed nests.
# READS: args.text; <cwd>/.pidgin/registry.json (optional);
#        <cwd>/.pidgin/nest/ (fallback); per-nest ChromaDB via query_by_path.
# IMPLEMENTS: registry-aware multi-nest search; query normalisation (M7);
#             graceful error handling per nest.
# DEPENDS: pidgin.store.nest, pidgin.store.discovery; pidgin.utils.api; os, sys.

import os
import sys

# ---------------------------------------------------------------------------
# Query normalisation (M7)
# ---------------------------------------------------------------------------

NORMALISE_PROMPT = """Rewrite the user's query as a single imperative
function description in present tense, matching the style of a docstring
summary. One sentence, ending with a period. No leading verbs like
"function that" or "returns". Just the imperative.

Examples:
  "how do I parse a CSV?" -> "Parse a CSV file and return rows as dictionaries."
  "what reads the config" -> "Read the configuration file and return its contents."

Query: {query}
Output: only the rewritten sentence, no preamble."""


def _normalise_query(text: str) -> str:
    """Pass the query through gpt-4.1-nano and return the rewritten imperative text.

    Falls back to the original text on any API failure — never raises.
    """
    from pidgin.utils.api import ensure_api_key, openai_client
    ensure_api_key("OPENAI_API_KEY")
    try:
        client = openai_client()
        resp = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": NORMALISE_PROMPT.format(query=text)}],
            max_tokens=80,
            temperature=0.0,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[query] WARNING: normalisation failed ({e}); using raw query.",
              file=sys.stderr)
        return text


# ---------------------------------------------------------------------------
# Argparse additions (consumed by cli.py build_parser)
# ---------------------------------------------------------------------------

def add_arguments(parser) -> None:
    """Add query-specific arguments to the subparser.

    Called from cli.py after the shared parent is attached.
    --verbose is already provided by _shared_flags(); only --raw is added here.
    """
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip query normalisation (use the input text verbatim).",
    )


# ---------------------------------------------------------------------------
# Verb implementation
# ---------------------------------------------------------------------------

def run(args) -> int:
    """Run the query verb.

    Normalises the query through gpt-4.1-nano unless --raw is set.
    Loads the registry from cwd/.pidgin/registry.json when present and searches
    all registered nests. Falls back to a single local nest search when no
    registry exists. Merges all hits by similarity and prints the top 10.
    """
    from pidgin.store import nest as nest_mod, discovery

    text = args.text
    if not getattr(args, "raw", False):
        normalised = _normalise_query(text)
        if getattr(args, "verbose", False):
            print(f"[query] raw=       {text}", file=sys.stderr)
            print(f"[query] normalised={normalised}", file=sys.stderr)
        text = normalised

    cwd = os.getcwd()
    registry = discovery.load_registry(cwd)
    targets = []
    if registry:
        targets = [(p.namespace, p.nest_path) for p in registry]
        print(f"[query] Searching {len(targets)} registered nest(s).")
    else:
        # Resolve nest path via git root so query finds the correct nest
        # regardless of which subdirectory the user is in.
        local = nest_mod.nest_path(cwd)
        if not os.path.isdir(local):
            print(f"(no nest found at {local} and no registry found)")
            return 0
        targets = [("local", local)]

    all_results = []
    for ns, nest_path in targets:
        try:
            hits = nest_mod.query_by_path(nest_path, text, n_results=5)
            for hit in hits:
                all_results.append((ns, hit))
        except Exception as e:
            print(f"  [query] Warning: failed to query {ns}: {e}")

    all_results.sort(key=lambda r: -r[1].get("similarity", 0))
    for ns, hit in all_results[:10]:
        print(
            f"  [{ns}] {hit.get('similarity', 0):.3f}  "
            f"{hit.get('function_name', '?')} — {hit.get('description', '')}"
        )
    if not all_results:
        print("(no results)")
    return 0
