# pidgin/store/

ChromaDB-backed knowledge store — sections store and function vector store merged
into one module (nest.py). JSONL audit helpers in audit.py.

Provenance: merged from tools/store/sections_chroma.py (M6) + tools/store/vectors.py
(M8) into pidgin/store/nest.py in M10. audit.py extracted from tools/store/audit.py
(JSONL helpers only — crispr_write/edit superseded by pidgin/write/).

## Files

### nest.py
Merged ChromaDB backend. Three collections in one persistent store at
`local/store/nest/`: sections (`descriptions`), function bodies (`function_bodies`),
function descriptions (`function_descriptions`).

**Sections store (from sections_chroma.py):**

| Symbol | Kind | DOES |
|--------|------|------|
| `store_path` | fn | Return the canonical local/store/nest/ directory. |
| `nest_path` | fn | Return per-repo .pidgin/nest/ path given repo_root (M12). |
| `ensure_nest` | fn | Create <repo_root>/.pidgin/nest/ if absent; return path (M12). |
| `write_nest_claude_md` | fn | Write .pidgin/CLAUDE.md at repo_root unless it already exists (M12). |
| `query` | fn | Embed text and search <repo_root>/.pidgin/nest/ by similarity (M12). |
| `section_put_chroma` | fn | Write a section to ChromaDB with hash idempotency and version bump. |
| `section_get_chroma` | fn | Read a section by (file, tag); return (content, metadata) or None. |
| `section_query_chroma` | fn | Filter sections by metadata where-clause; return (doc_id, content, metadata) list. |

**Vector store (from vectors.py):**

| Symbol | Kind | DOES |
|--------|------|------|
| `function_id` | fn | Stable 16-char ID from sha256(file:name:line_start). |
| `upsert_function` | fn | Embed body + description in one call, upsert into both function collections. |
| `find_by_body` | fn | "Find functions that handle X" — search function_bodies by query. |
| `find_similar_to_description` | fn | "Find functions similar to this one" — search function_descriptions. |
| `delete_function` | fn | Remove an entry from both function collections by id. |
| `reset_all` | fn | Drop and recreate both function collections. Test/dev only. |
| `query_by_path` | fn | Search function_descriptions by direct nest_path (not repo_root). Returns [] on ChromaDB open error. Added M13. |

### discovery.py
Nested nest discovery and registry persistence. Wired in M13.

| Symbol | Kind | DOES |
|--------|------|------|
| `NestPointer` | dataclass | Frozen dataclass: repo_root, nest_path, namespace. One per discovered child nest. |
| `discover_nests` | fn | Walk root up to max_depth=4; return NestPointer list for child dirs with .pidgin/nest/. Root itself excluded. Noise dirs skipped. |
| `register_nests` | fn | Write JSON registry to <root>/.pidgin/registry.json; return path. |
| `load_registry` | fn | Read <root>/.pidgin/registry.json; return list[NestPointer] or None if absent. |

### audit.py
JSONL helpers only. Transaction/write code lives in pidgin/write/.

| Symbol | Kind | DOES |
|--------|------|------|
| `file_hash` | fn | Return sha256 hex of file content; empty string if file missing. |
| `audit_log_path` | fn | Return path to local/audit/marionette_actions.jsonl. |
| `audit_log` | fn | Append a timestamped + pid-annotated JSON line to the audit log. |

## Collections

Three collections in the same ChromaDB instance at `local/store/nest/`:

| Collection | Owner fn | Vector | Document |
|------------|----------|--------|----------|
| `descriptions` | section_put_chroma | description text vector | section content |
| `function_bodies` | upsert_function | function source vector | raw function source |
| `function_descriptions` | upsert_function | description text vector | MLD description |

## Merge Notes (M10)

Name conflicts resolved:
- `_client()` → `_sec_client()` (sections) and `_vec_client()` (vectors, cached)
- `_git_ref()` → `_sec_git_ref()` (returns str|None) and `_vec_git_ref()` (returns str)

Both path functions (`store_path` from sections_chroma, `nest_path` from vectors)
are retained as public functions pointing to the same directory.

## How to Navigate

1. Find the symbol in the tables above.
2. Find its start line:
   `awk '/^def section_put_chroma/{ print NR; exit }' pidgin/store/nest.py`
3. Find where the next symbol starts.
4. Read the range: lines START..END-1.

Never read an entire file. Use the index then awk then ranged read.
