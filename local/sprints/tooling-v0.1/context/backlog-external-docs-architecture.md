# Backlog: External Documentation Architecture

Depends on: tooling-v1 complete, section primitive validated.

## The Vision

Source files carry zero documentation. Comments, descriptions,
contracts, index entries — all live in an external store with precise
location references. Source is pristine. Documentation is queryable.
The section_get/section_put API stays identical — backend changes
from file I/O to database writes.

## Layer 1: SQLite Documentation Store

Every description, every index entry, every contract annotation
stored in a local SQLite database. Gitignored. Per-operator.

Schema sketch:
```sql
CREATE TABLE sections (
    file TEXT,
    tag TEXT,
    content TEXT,
    version INTEGER,
    updated TEXT,
    by TEXT,
    model TEXT,
    source_hash TEXT,
    git_ref TEXT,          -- commit hash at time of write
    PRIMARY KEY (file, tag)
);
```

section_put writes to this table instead of modifying files.
section_get reads from it. Same API. The XML tags in source files
become optional human-readable annotations, not source of truth.

Migration: section_put gains a --backend flag (file | db). Default
starts as file (current behavior). Flip to db when the store is
validated.

## Layer 2: Vector Search via ChromaDB

ChromaDB runs inside Marionette as a container service. Vector
files are bind-mounted from the project directory. Every function
body and every description gets a vector.

Two search modes:
- "Find the function that handles X" → vector query against
  function body embeddings → returns file, line range, description
- "Find functions similar to this one" → vector query against
  description embeddings → returns related functions

The sprint runner can perform vector queries without reading source
files. The coordinator never has raw code access — it works through
structured results from the vector store.

ChromaDB is a Rust binary. Package it. Turn it on. Bind-mount the
vector file. Same pattern as every other RF-Edge service.

## Layer 3: Cascading Trust Model

Exfiltration requires compromising multiple agents in sequence:
1. Mission coordinator (composes the request)
2. Task runner (executes the mission)
3. Task validator (reviews the output)
4. Sprint runner (receives and logs the result)

Each boundary: agent judgment + mechanical regex filter.
The sprint runner has no direct file access. Vector queries
return descriptions, not source. To exfiltrate actual source code,
every layer must be compromised in sequence. Architectural
incapacity at every boundary.

This is the RISC principle applied to data access. The vocabulary
at each tier does not contain the words for "return raw file
contents." The absence of the capability is more secure than
its restriction.

## Layer 4: Mechanical Audit Trail

Every write operation:
1. Capture current git status and HEAD
2. git commit pre-write: "pre-write: <file> by <agent>"
3. Perform the write
4. git commit post-write: "post-write: <file> by <agent>"

Complete rollback: git revert the post-write commit.

Every Marionette action writes a structured record to TimescaleDB
(already running in RF-Edge). The audit trail is queryable:

```sql
SELECT file, agent, action, git_ref_before, git_ref_after, timestamp
FROM marionette_actions
WHERE agent = 'technologic'
  AND timestamp BETWEEN '2026-04-24 14:00' AND '2026-04-24 16:00'
ORDER BY timestamp;
```

Not a log file. A time-series database you can query, aggregate,
and correlate with system metrics in the same TimescaleDB instance.

## The Bridge

The section primitive (tools/utils/sections.py) is the bridge
between current architecture and this vision. Today it reads and
writes tagged sections in files. Tomorrow the same API reads and
writes to SQLite. The callers — /technologic, /digest, /embed —
never change. The storage backend changes underneath them.

The XML tags in source files become optional. Leave them for human
readers. Remove them for pristine source. The database is the
source of truth either way.

## Fork Workflow

To work with any repo:
1. Fork it
2. Add a gitignored local/ directory
3. Run /technologic to populate the SQLite index
4. Run /embed to populate the vector store
5. Pull upstream updates freely — you never touched their code

The index and vectors are local artifacts. They travel with the
operator, not with the repo.

## Depends On

- tooling-v1: section primitive, /technologic, /embed
- ChromaDB packaging in Marionette
- TimescaleDB already exists in RF-Edge
- SQLite is stdlib Python — no new dependencies
