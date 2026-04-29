# Write Model

V2 routed all file operations through `crispr_write` and `crispr_edit` in `tools/store/audit.py`. This was correct for surgical edits to existing source files. It was wrong for everything else. The write model needs four modes, each with distinct commit semantics and permission requirements.

## The Problem

M14 (Origami reprocessing) exposed the failure. `origami_reprocess.py` is 660 lines of Python that builds ORIGAMI.md by appending lines to a list, then writes the list through `crispr_write`. This is a document generation task forced through a surgical editing channel.

Consequences:
- `crispr_write` assumes the target file exists (pre-write `git add -- <file>` fails on non-existent paths). A `_seed_new_file` workaround was required — creates an empty file and makes a "seed-empty" commit before entering the CRISPR bracket. Each new file gets 3 commits instead of 2.
- Every future skill that creates new files hits the same wall and needs the same workaround.
- Comment stripping and rewriting on a single file requires 10-20 slice operations. Each operation gets its own git bracket (pre-commit + post-commit). A single file edit produces 20-40 commits. The git history becomes noise.

## The Four Modes

### Mode 1 — Index

Read source, generate descriptions, store in `.pidgin/nest/`. Source files are never touched. No file writes, no git commits. Only ChromaDB operations.

Permission: default (read-only against source, --write-db for the nest).
Audit: JSONL entry per indexing run. No git involvement.

### Mode 2 — Update

Surgical edits to existing files. The only mode that modifies source files that have content worth preserving. Hash verification before and after. Git commit bracket at the FILE level, not the operation level.

The sequence:
1. Capture `pre_hash` of the file
2. `git commit` pre-write (only if file is dirty — otherwise skip)
3. Accumulate all edit operations in memory
4. Apply all operations to a copy of the file content
5. Write the final result once
6. Capture `post_hash`
7. `git commit` post-write
8. One audit entry listing all operations

The transaction context manager pattern:

```python
with pidgin.update("parser.py") as f:
    f.strip_comment(line=5)
    f.insert_tag(line=5, tag="mld:extract_ast", content=description)
    f.replace(line_start=10, line_end=12, content=new_block)
# exit: writes file, one pre/post bracket, one audit entry
```

Permission: --write-source.
Audit: one JSONL entry per file with a list of operations. Two git commits per file (pre-write + post-write).

### Mode 3 — New

Create complete files from generated content. No hash verification — nothing to verify against. No pre-write commit — no prior state.

The sequence:
1. Generate content in memory
2. Write file(s) to disk
3. One `git commit` after all files in the batch are written
4. One audit entry listing all files created

Used for: ORIGAMI.md, ARCHITECTURE.md, CLAUDE.md indexes, behavioral contracts, any file where the entire content is generated.

Permission: --write-source (creating files is still a source modification).
Audit: one JSONL entry per batch. One git commit per batch.

### Mode 4 — Compress

Read input text, MLD-compress it, produce a new artifact. Input is read-only. Output is a new file. Write side is identical to Mode 3.

The distinction from Mode 3 is semantic, not mechanical. Compress reads existing content and produces a derived artifact. New produces content from instructions or structured data. The write path is the same. The distinction matters for the audit trail — compress records the input source_hash so the lineage from input to output is traceable.

Permission: --write-db (store the compressed result) + --write-source (if writing to a file).
Audit: one JSONL entry with input_source_hash and output file path.

## Implementation Notes

`audit.py` needs two write functions:
- `crispr_write` / `crispr_edit` — retained for Mode 2 (update). Gains transaction semantics: open a file context, queue operations, commit on exit.
- `artifact_write` — new function for Mode 3 and 4 (new/compress). Writes complete files, no hash verification, one git commit per batch, one audit entry.

The seed-empty workaround in `origami_reprocess.py` is removed when `artifact_write` ships. The entire `origami_reprocess.py` simplifies dramatically — it becomes: read manifesto, compress principles, `artifact_write(["ORIGAMI.md", "ARCHITECTURE.md", "CLAUDE.md"], contents)`.
