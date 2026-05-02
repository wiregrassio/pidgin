# pidgin/verbs/index.py — fully wired index verb.
# v0.2: default behaviour is WRITE (PD6 dry-run gate removed).
# --dry-run flag: walk files, count, estimate cost, check keys, exit 0.
# Post-MLD: synthesise a file-level summary from per-function descriptions
#            and store it via section_put_chroma with doc_type="file_summary".

# MODULE: verbs.index
# DOES: Walk a path, discover public functions, run MLD pipeline, write nest.
#       --dry-run: preview function count, estimated API calls and cost, key
#       availability — no API calls, no nest writes.
#       Post-MLD: synthesise a one-paragraph file-level summary from per-function
#       descriptions; stored in the sections store via section_put_chroma
#       (doc_type="file_summary", tag="file_summary").
# EMITS: stdout progress lines; ChromaDB writes (live mode).
# READS: source files under args.path; pidgin.utils.parser for extraction.
# IMPLEMENTS: M2 batch-failure detection (ALL_ERRORED → exit 1 without writing nest).
# IMPLEMENTS: M2 --verbose flag (per-function status lines after pipeline).
# IMPLEMENTS: M2 KeyboardInterrupt handler (clean one-line summary, exit 130).
# IMPLEMENTS: M6 --dry-run flag (preview mode, no API calls).
# IMPLEMENTS: M6 post-MLD file summary synthesis (section_put_chroma doc_type="file_summary").
# DEPENDS: pidgin.utils.parser, pidgin.pipeline, pidgin.store.nest

import os
import sys
import warnings

# M2: suppress cosmetic "Event loop is closed" RuntimeError from asyncio cleanup
# during KeyboardInterrupt. The event loop is already torn down at that point;
# this traceback is not actionable and alarms users without providing information.
warnings.filterwarnings("ignore", message=".*Event loop is closed.*")

# Cost coefficient: conservative constant for --dry-run cost estimate.
# Derived from v0.2 sprint: ~$0.10 across 16 missions with ~500 functions total.
# Using $0.0002 per function (~$0.20 per 1000 functions) as the upper-bound estimate
# that accounts for both gpt-4.1-nano completion and text-embedding-3-small embedding.
COST_PER_FUNCTION_USD = 0.0002


def _print_dry_run_summary(
    root: str,
    exclude_globs: list,
) -> None:
    """Print a markdown-flavoured summary to stdout.

    Walks files, counts public functions, estimates API calls and cost,
    checks API key availability. Does not call any external APIs.

    Output format:
        [index --dry-run] root=<abs path>
        --
        Files (by extension):
          .py: <N>
        Public functions: <M>
        Estimated API calls: <M> functions × ~5 calls each = <K>
        Estimated cost: ~$<C> (gpt-4.1-nano + text-embedding-3-small)
        API keys:
          OPENAI_API_KEY:    [present|MISSING]
          ANTHROPIC_API_KEY: [present|MISSING]
        --
        Run without --dry-run to execute.
    """
    from pidgin.utils.parser import extract_public_functions, walk_source_files
    from collections import defaultdict

    abs_root = os.path.abspath(root)
    files = list(walk_source_files(root, exclude_globs=exclude_globs))

    # Count files by extension.
    ext_counts: dict = defaultdict(int)
    for f in files:
        ext = os.path.splitext(str(f))[1] or "(no ext)"
        ext_counts[ext] += 1

    # Count public functions across all files.
    total_funcs = 0
    for f in files:
        total_funcs += len(extract_public_functions(str(f)))

    # Estimate API calls: each function goes through ~5 round-trips
    # (MLD generation x3 iterations + embed body + embed description).
    calls_per_function = 5
    estimated_calls = total_funcs * calls_per_function
    estimated_cost = total_funcs * COST_PER_FUNCTION_USD

    # Check API key availability (no network call — env lookup only).
    openai_key = os.environ.get("OPENAI_API_KEY") or ""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    openai_status = "present" if openai_key else "MISSING"
    anthropic_status = "present" if anthropic_key else "MISSING"

    print(f"[index --dry-run] root={abs_root}")
    print("--")
    print("Files (by extension):")
    if ext_counts:
        for ext in sorted(ext_counts):
            print(f"  {ext}: {ext_counts[ext]}")
    else:
        print("  (none)")
    print(f"Public functions: {total_funcs}")
    print(
        f"Estimated API calls: {total_funcs} functions "
        f"× ~{calls_per_function} calls each = {estimated_calls}"
    )
    print(
        f"Estimated cost: ~${estimated_cost:.4f} "
        f"(gpt-4.1-nano + text-embedding-3-small)"
    )
    print("API keys:")
    print(f"  OPENAI_API_KEY:    [{openai_status}]")
    print(f"  ANTHROPIC_API_KEY: [{anthropic_status}]")
    print("--")
    print("Run without --dry-run to execute.")


def _build_sft_records(results, funcs) -> list:
    """Build SFT training records for a batch of MLD results.

    Produces one positive record (winner = candidates[0]) and one negative
    record (candidate furthest from centroid) per converged function. Returns
    a list of SFTRecord objects ready for _sft.append().

    Extracted from run() so that on_chunk_complete can call it after each
    chunk instead of in a bulk pass at the end.
    """
    from pidgin.store import sft as _sft
    from pidgin.pipeline.geometry import cosine_similarity as _cos_sim, centroid as _centroid
    from pidgin.store.nest import function_id as _function_id

    records: list = []
    for r, fn in zip(results, funcs):
        if r.first_error or not r.candidates:
            continue
        valid_vecs = [v for v in r.vectors if v is not None]
        if not valid_vecs:
            continue
        centroid_vec = _centroid(valid_vecs)
        winner_text = r.candidates[0]
        fn_id = _function_id(fn.get("file", ""), fn.get("name", ""), fn.get("line_start", 0))
        records.append(_sft.SFTRecord(
            type="sft",
            prompt=r.prompt_used,
            completion=winner_text,
            label="positive",
            function_id=fn_id,
        ))
        cand_vec_pairs = [
            (cand, vec)
            for cand, vec in zip(r.candidates, r.vectors)
            if vec is not None
        ]
        if len(cand_vec_pairs) > 1:
            worst_cand, worst_vec = max(
                cand_vec_pairs,
                key=lambda cv: 1 - _cos_sim(cv[1], centroid_vec),
            )
            if worst_cand != winner_text:
                records.append(_sft.SFTRecord(
                    type="sft",
                    prompt=r.prompt_used,
                    completion=worst_cand,
                    label="negative",
                    function_id=fn_id,
                    centroid_distance=1 - _cos_sim(worst_vec, centroid_vec),
                ))
    return records


def _maybe_synthesise_summaries(
    chunk_funcs: list,
    chunk_results: list,
    *,
    changed_files: set,
    file_total_funcs: dict,
    file_completed_names: dict,
    file_descriptions_acc: dict,
    verbose: bool = False,
) -> tuple[int, int]:
    """Synthesise file-level summaries for any files now fully complete.

    Tracks which functions have been processed per file using the caller-owned
    file_completed_names dict (mutated in place). Accumulates per-function
    descriptions in file_descriptions_acc (also caller-owned, mutated in place)
    so that multi-chunk files get summaries from ALL their functions, not just
    the final chunk.

    When a file's completed set reaches the total expected function count (from
    file_total_funcs), generates and stores its file_summary.

    Returns (summary_count, failed_summaries) for this call.

    Extracted from run() so that on_chunk_complete can call it incrementally
    instead of a bulk pass at the end.
    """
    from pidgin.store.nest import section_put_chroma

    summary_count = 0
    failed_summaries = 0

    # Update completed-function tracking and accumulate descriptions.
    # Use (name, line_start) as unique key per function within a file.
    for r, fn in zip(chunk_results, chunk_funcs):
        file_path = fn.get("file", "")
        if not file_path:
            continue
        fn_key = (fn.get("name", ""), fn.get("line_start", 0))
        if file_path not in file_completed_names:
            file_completed_names[file_path] = set()
        file_completed_names[file_path].add(fn_key)
        # Accumulate the winning description for this function.
        if r.candidates:
            if file_path not in file_descriptions_acc:
                file_descriptions_acc[file_path] = []
            file_descriptions_acc[file_path].append(r.candidates[0])

    # Check which files are now fully complete after this chunk.
    for file_path, completed in list(file_completed_names.items()):
        expected = file_total_funcs.get(file_path, 0)
        if expected == 0 or len(completed) < expected:
            continue  # file not yet complete
        if file_path not in changed_files:
            continue  # byte-stable — no summary needed
        # Use accumulated descriptions (all functions across all chunks).
        descriptions = file_descriptions_acc.get(file_path, [])
        if not descriptions:
            continue
        try:
            summary = _synthesise_file_summary(file_path, descriptions)
        except Exception as exc:
            failed_summaries += 1
            print(
                f"[index] WARNING: file_summary synthesis raised for {file_path}: {exc}",
                file=sys.stderr,
            )
            continue
        if not summary:
            continue
        section_put_chroma(
            file=file_path,
            tag="file_summary",
            content=summary,
            doc_type="file_summary",
        )
        summary_count += 1
        if verbose:
            print(f"[index] file_summary stored for {file_path}")
        # Clear accumulated descriptions so the file isn't summarised twice
        # if the loop runs again (defensive — should only complete once).
        file_descriptions_acc[file_path] = []
        # Remove from completed so we don't try again.
        del file_completed_names[file_path]

    return summary_count, failed_summaries


def _synthesise_file_summary(file_path: str, descriptions: list) -> str:
    """Synthesise a one-paragraph file-level summary via gpt-4.1-nano.

    Builds a prompt from the per-function descriptions for the file, sends
    it to the OpenAI chat completions API, and returns the result as a
    single paragraph string.

    Returns an empty string on any API error (non-fatal — file summary is
    a byproduct; MLD results are already written).
    """
    combined = "\n".join(f"- {d}" for d in descriptions)
    prompt = (
        "Summarise the file's role in one paragraph (3-4 sentences).\n"
        "The file's public functions are described as:\n\n"
        f"{combined}\n\n"
        "Output: a single paragraph. No header, no bullets."
    )

    try:
        from pidgin.utils.api import get_openai_client
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(
            f"[index] WARNING: file summary for {file_path} failed: {exc}",
            file=sys.stderr,
        )
        return ""


def run(args) -> int:
    """Run the index verb.

    Default (no --dry-run): walk files, run MLD pipeline, write nest.
    --dry-run: discover public functions, print cost estimate, return 0.
                No API calls. No nest writes.

    After MLD completes, synthesises a one-paragraph file-level summary
    from per-function descriptions for each file and stores it via
    section_put_chroma(doc_type="file_summary").

    Exit 1 without writing the nest when ALL results are errored (M2).
    Emit per-function status lines when --verbose is set (M2).
    KeyboardInterrupt: print one-line summary and exit 130 (M2).
    """
    exclude_globs = getattr(args, "exclude", []) or []

    # --dry-run: preview mode — no API calls, no nest writes.
    if getattr(args, "dry_run", False):
        _print_dry_run_summary(args.path, exclude_globs)
        return 0

    # M2: track how many functions have been written to the nest incrementally
    # via the on_chunk_complete callback. Initialized before the try block so it
    # is always in scope in the except KeyboardInterrupt clause regardless of
    # where the interrupt fires.
    _chunk_write_count = [0]

    try:
        # Live mode — API calls happen here.
        from pidgin.utils.parser import (
            extract_public_functions,
            function_dict_hash,
            walk_source_files,
        )
        from pidgin.pipeline import run_embedding_mld_pipeline_for_functions
        from pidgin.pipeline.batch import classify_batch_results
        from pidgin.store import nest
        from pidgin.store.nest import diff_against_nest, prune
        from pathlib import Path as _Path

        repo_root_abs = os.path.abspath(args.path)

        files = list(walk_source_files(args.path, exclude_globs=exclude_globs))
        # CF3: extract_public_functions called per-file collapses `module` to the
        # basename (e.g. "parser.py"). Post-process to anchor module relative to
        # args.path so downstream callers see "pidgin/utils/parser.py" not "parser.py".
        _root_abs = _Path(args.path).resolve()
        funcs = []
        for f in files:
            for fn in extract_public_functions(str(f)):
                try:
                    fn["module"] = str(_Path(fn["file"]).resolve().relative_to(_root_abs))
                except ValueError:
                    pass  # file outside args.path — leave module as-is
                funcs.append(fn)
        print(f"[index] Discovered {len(funcs)} public functions in {args.path}")
        if not funcs:
            # No source-side functions — but the nest may contain stale records.
            # Diff with an empty source list to surface DELETED records and prune.
            diff = diff_against_nest(repo_root_abs, [])
            if diff.deleted:
                n_pruned = prune(repo_root_abs, [r.record_id for r in diff.deleted])
                print(
                    f"[index] unchanged=0 updated=0 new=0 deleted={n_pruned}"
                )
            else:
                print("[index] unchanged=0 updated=0 new=0 deleted=0")
            return 0

        # M13: precompute source_hash for every function dict and build the
        # (file_rel_path, fn) pairs that diff_against_nest expects. The dict's
        # "file" field is absolute; the upsert path uses the same absolute
        # string as the identity-key file component, so the hash diff and the
        # subsequent upsert agree on the key.
        for fn in funcs:
            fn["source_hash"] = function_dict_hash(fn)
        diff_pairs = [(fn.get("file", ""), fn) for fn in funcs]
        diff = diff_against_nest(repo_root_abs, diff_pairs)
        print(
            f"[index] unchanged={len(diff.unchanged)} "
            f"updated={len(diff.updated)} "
            f"new={len(diff.new)} "
            f"deleted={len(diff.deleted)}"
        )

        # Build the list of dicts to MLD: NEW + UPDATED. UNCHANGED dicts are
        # skipped — no API calls, no upsert, no embed.
        to_mld: list[dict] = list(diff.new) + [new_fn for _old, new_fn in diff.updated]

        # M13: compute the set of files that need a fresh file_summary.
        # Reasoning: a file's role is a function of its public surface; if the
        # surface is byte-stable, the summary need not change. Regenerate IFF the
        # file has at least one function in NEW, UPDATED, or DELETED.
        changed_files: set = set()
        for fn in diff.new:
            fp = fn.get("file", "")
            if fp:
                changed_files.add(fp)
        for _old, new_fn in diff.updated:
            fp = new_fn.get("file", "")
            if fp:
                changed_files.add(fp)
        for rec in diff.deleted:
            if rec.file_path:
                changed_files.add(rec.file_path)

        if not to_mld and not diff.deleted:
            # Fully-idempotent path — nothing to do. Still write the nest CLAUDE.md
            # if it is missing (write_nest_claude_md is itself idempotent).
            nest_dir = nest.ensure_nest(args.path)
            nest.write_nest_claude_md(args.path)
            print(f"[index] Nest unchanged at {nest_dir} (zero API calls)")
            return 0

        # Prune DELETED records up front. Pruning before MLD is safe — the diff
        # already confirmed those keys do not exist in the new source tree, so
        # there is no risk of deleting a record we are about to re-write.
        if diff.deleted:
            n_pruned = prune(repo_root_abs, [r.record_id for r in diff.deleted])
            if getattr(args, "verbose", False):
                for rec in diff.deleted:
                    print(
                        f"[index] pruned name={rec.symbol_name} file={rec.file_path}"
                    )
            print(f"[index] Pruned {n_pruned} deleted record(s).")

        if not to_mld:
            # Only deletions; no MLD needed but still rewrite the nest CLAUDE.md.
            nest_dir = nest.ensure_nest(args.path)
            nest.write_nest_claude_md(args.path)
            print(f"[index] Nest at {nest_dir} (deletions only, zero MLD calls)")
            return 0

        # M12-patch: build {rel_path: FileMeta} lookup before upsert so that
        # upsert_function_descriptions can thread signature/decorators into metadata.
        # CF9: both extract_file_meta and upsert_function_descriptions use args.path
        # as the anchor. If either helper changes its rooting convention, the identity
        # keys (rel_path) will diverge and upsert will fail to match metadata to functions.
        # Built before the pipeline runs so the on_chunk_complete callback can access it.
        from pidgin.utils.parser import extract_file_meta, write_imports_json
        file_meta_by_rel: dict = {}
        for p in files:
            try:
                fm = extract_file_meta(args.path, str(p))
                file_meta_by_rel[fm.path] = fm
            except Exception:
                pass  # parse errors are non-fatal

        # Ensure the nest directory exists before the first chunk callback fires.
        nest_dir = nest.ensure_nest(args.path)

        # M1: build per-file function totals so _maybe_synthesise_summaries can
        # determine when a file is fully complete (all its functions processed).
        from collections import defaultdict
        file_total_funcs: dict = defaultdict(int)
        for fn in to_mld:
            fp = fn.get("file", "")
            if fp:
                file_total_funcs[fp] += 1

        # M1: closure state for incremental upsert + SFT + file summaries.
        # _chunk_write_count is declared above the try block so it is accessible
        # in the except KeyboardInterrupt handler even on early interrupt.
        from pidgin.store import sft as _sft
        import time as _time
        _sft_total_written = [0]   # list so closure can mutate
        _summary_count = [0]
        _failed_summaries = [0]
        _file_completed_names: dict = {}   # file_path → set of (name, line_start) keys
        _file_descriptions_acc: dict = {}  # file_path → list of winning descriptions (all chunks)
        verbose = getattr(args, "verbose", False)
        # M3: progress tracking state.
        _n_total_to_mld = len(to_mld)
        _n_funcs_done = [0]        # count of functions processed so far
        _n_converged = [0]         # count of converged functions so far
        _n_chunks_done = [0]       # count of chunks completed so far
        _pipeline_start = _time.monotonic()
        # Estimate total chunks: batch size is BATCH_CHUNK_SIZE requests, each function
        # needs max_batches gen calls. Approximate from total request count.
        from pidgin.pipeline.batch import BATCH_CHUNK_SIZE, ADAPTIVE_MAX_BATCHES
        _reqs_per_func = ADAPTIVE_MAX_BATCHES
        _total_reqs = _n_total_to_mld * _reqs_per_func
        _n_total_chunks = max(1, (_total_reqs + BATCH_CHUNK_SIZE - 1) // BATCH_CHUNK_SIZE)

        def _format_progress_eta(elapsed_s: float, done: int, total: int) -> str:
            """Return '~Xh Ym remaining' or 'done' based on rate so far."""
            if done <= 0 or total <= done:
                return "~? remaining"
            rate = elapsed_s / done  # seconds per function
            remaining = (total - done) * rate
            total_s = int(remaining)
            hours = total_s // 3600
            minutes = (total_s % 3600) // 60
            if hours > 0:
                return f"~{hours}h {minutes}m remaining"
            secs = total_s % 60
            return f"~{minutes}m {secs}s remaining"

        def _on_chunk(chunk_results, chunk_funcs):
            """Per-chunk callback: upsert to nest, append SFT records, synthesise file summaries."""
            # 1. Upsert to ChromaDB nest.
            nest.upsert_function_descriptions(
                repo_root_abs, chunk_results, chunk_funcs,
                file_meta=file_meta_by_rel,
            )
            # 2. Build and append SFT records.
            sft_records = _build_sft_records(chunk_results, chunk_funcs)
            if sft_records:
                _sft.append(repo_root_abs, sft_records)
            _sft_total_written[0] += len(sft_records)
            # 3. Synthesise file-level summaries for any files now fully complete.
            sc, fs = _maybe_synthesise_summaries(
                chunk_funcs,
                chunk_results,
                changed_files=changed_files,
                file_total_funcs=file_total_funcs,
                file_completed_names=_file_completed_names,
                file_descriptions_acc=_file_descriptions_acc,
                verbose=verbose,
            )
            _summary_count[0] += sc
            _failed_summaries[0] += fs
            # M2: track total functions written for the KeyboardInterrupt handler.
            _chunk_write_count[0] += len(chunk_funcs)

            # M3: verbose per-function output.
            if verbose:
                for r in chunk_results:
                    if r.first_error is not None:
                        print(f"  ✗ {r.name} (error: {r.first_error})", file=sys.stderr)
                    elif r.converged:
                        print(
                            f"  ✓ {r.name} (converged, sv={r.sv:.4f}, cluster={r.cluster_size})",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            f"  ✗ {r.name} (not converged, cluster={r.cluster_size})",
                            file=sys.stderr,
                        )

            # M3: update progress counters and print progress line.
            _n_funcs_done[0] += len(chunk_funcs)
            _n_converged[0] += sum(1 for r in chunk_results if r.converged)
            _n_chunks_done[0] += 1
            elapsed = _time.monotonic() - _pipeline_start
            done = _n_funcs_done[0]
            total = _n_total_to_mld
            converged = _n_converged[0]
            pct = (converged / done * 100) if done > 0 else 0.0
            eta_str = _format_progress_eta(elapsed, done, total)
            print(
                f"[batch {_n_chunks_done[0]}/{_n_total_chunks}] "
                f"{done}/{total} functions | "
                f"{converged} converged ({pct:.1f}%) | "
                f"{eta_str}",
                file=sys.stderr,
            )

        dispatch = "batch" if args.batch else ("sync" if args.sync else "auto")
        results = run_embedding_mld_pipeline_for_functions(
            to_mld,
            dispatch=dispatch,
            on_chunk_complete=_on_chunk,
        )
        # From here on, `funcs` is replaced by `to_mld` for the post-MLD machinery.
        funcs = to_mld

        # M2: classify batch results — exit 1 on ALL_ERRORED, warn on PARTIAL.
        from types import SimpleNamespace
        proxy_results = [SimpleNamespace(error=r.first_error) for r in results]
        verdict, first_error = classify_batch_results(proxy_results)

        if verdict == "ALL_ERRORED":
            print(
                f"[index] FATAL: batch failed. First error: {first_error}",
                file=sys.stderr,
            )
            return 1

        if verdict == "PARTIAL":
            n_err = sum(1 for p in proxy_results if p.error is not None)
            print(
                f"[index] WARNING: {n_err}/{len(results)} functions errored. "
                f"Continuing with {len(results) - n_err} clean results.",
                file=sys.stderr,
            )

        converged = sum(1 for r in results if r.converged)
        print(f"[index] Converged: {converged}/{len(results)}")

        # M2: --verbose — emit one status line per function after pipeline finishes.
        if verbose:
            for r, fn in zip(results, funcs):
                if r.first_error is not None:
                    status = "errored"
                elif r.converged:
                    status = "converged"
                else:
                    status = "skipped"
                rel_path = fn.get("file", "")
                print(
                    f"[index] func={r.name} file={rel_path} status={status} "
                    f"cluster={r.cluster_size} drafts={len(r.candidates)}"
                )

        # Print SFT total (records were written incrementally by _on_chunk).
        total_sft = _sft.count(repo_root_abs)
        print(
            f"[index] Wrote {_sft_total_written[0]} training examples to "
            f".pidgin/training-data.jsonl (cumulative: {total_sft})."
        )

        # Finalize nest: write CLAUDE.md (one-time after all chunks complete).
        nest.write_nest_claude_md(args.path)
        print(f"[index] Wrote nest at {nest_dir}")

        # M12: write imports.json — full AST metadata for every walked file.
        # CF8: reuse file_meta_by_rel.values() instead of re-calling extract_file_meta
        # per file. The first loop already parsed every file; a second walk is redundant
        # and would silently double the parse cost on large repos.
        repo_root = args.path
        imports_path = write_imports_json(repo_root, list(file_meta_by_rel.values()))
        print(f"[index] Wrote imports.json at {imports_path}")

        # Print file summary totals (summaries were written incrementally by _on_chunk).
        summary_line = f"[index] Stored {_summary_count[0]} file-level summaries."
        if _failed_summaries[0]:
            summary_line += f" ({_failed_summaries[0]} failed)"
        if _summary_count[0] or _failed_summaries[0]:
            print(summary_line)

        return 0

    except KeyboardInterrupt:
        # M1's incremental writes mean partial results are already persisted.
        # Count what we have and report — no re-raise, no traceback.
        n_written = _chunk_write_count[0]
        n_total = len(to_mld) if "to_mld" in dir() else len(funcs) if "funcs" in dir() else 0
        print(
            f"\nInterrupted. Wrote {n_written}/{n_total} functions to nest. "
            f"Resume with the same command to continue.",
            file=sys.stderr,
        )
        sys.exit(130)
