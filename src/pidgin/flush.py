"""Flush — write the buffer to disk and run the post-write pipeline.

Sequence (AD-7):
  1. atomic write (tempfile + os.replace)
  2. black format (SOFT skip if black not installed)
  3. reindex via index_file(force=True)
  4. graph.save
  5. egg.egg for the file's directory (recursive=False)
  6. git commit (only the touched file)

Failure matrix (AD-7):
  write       -> raise FlushError
  black       -> log warning, continue
  reindex     -> raise FlushError
  graph.save  -> raise FlushError
  egg         -> log warning, continue
  git_commit  -> raise FlushError
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pidgin.egg import egg as run_egg
from pidgin.graph import ImportGraph
from pidgin.index import collect_repo_files, index_file
from pidgin.nest import Nest


class FlushError(RuntimeError):
    """Raised on critical flush-step failures (write, reindex,
    graph.save, commit)."""


@dataclass
class FlushReport:
    file_path: str
    bytes_written: int
    black_ran: bool
    black_warning: str | None
    indexed: bool
    graph_edges: int
    egg_paths: list[str]
    egg_warning: str | None
    commit_sha: str | None
    commit_message: str
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- #
# Public entry point                                                  #
# ----------------------------------------------------------------- #

def flush(
    *,
    file_path: Path,
    buffer: str,
    original_buffer: str,
    changes: list,             # list[ChangeRecord] — avoids circular import
    nest: Nest,
) -> FlushReport:
    """Run the flush sequence. Returns a FlushReport."""
    # Step 1 — atomic write
    file_path = Path(file_path).resolve()
    _atomic_write(file_path, buffer)
    bytes_written = len(buffer.encode("utf-8"))

    # Step 2 — black (SOFT)
    black_ran, black_warning = _run_black(file_path)

    # Step 3 — reindex (HARD)
    graph_path = nest.nest_path / "imports.json"
    graph = ImportGraph.load(graph_path)
    repo_files = collect_repo_files(nest.repo_root)
    try:
        result = index_file(
            file_path, nest, graph, repo_files, force=True
        )
        if result.error is not None:
            raise FlushError(f"reindex failed: {result.error}")
    except FlushError:
        raise
    except Exception as exc:
        raise FlushError(f"reindex raised: {exc}") from exc

    # Step 4 — graph.save (HARD)
    try:
        graph.save(graph_path)
    except Exception as exc:
        raise FlushError(f"graph.save failed: {exc}") from exc

    # Step 5 — egg (SOFT)
    egg_paths: list[str] = []
    egg_warning: str | None = None
    try:
        written = run_egg(file_path.parent, nest, recursive=False)
        egg_paths = [str(p) for p in written]
    except Exception as exc:
        egg_warning = f"egg raised: {exc}"

    # Step 6 — git commit (HARD)
    rel_path = _repo_rel(file_path, nest.repo_root)
    msg = _build_commit_message(rel_path, changes, original_buffer, buffer)
    sha = _git_commit(nest.repo_root, [rel_path], msg)

    return FlushReport(
        file_path=str(file_path),
        bytes_written=bytes_written,
        black_ran=black_ran,
        black_warning=black_warning,
        indexed=True,
        graph_edges=graph.edge_count,
        egg_paths=egg_paths,
        egg_warning=egg_warning,
        commit_sha=sha,
        commit_message=msg,
    )


# ----------------------------------------------------------------- #
# Step 1 — atomic write                                              #
# ----------------------------------------------------------------- #

def _atomic_write(path: Path, content: str) -> None:
    """Write `content` to `path` atomically via tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".pidgin-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ----------------------------------------------------------------- #
# Step 2 — black                                                      #
# ----------------------------------------------------------------- #

def _run_black(path: Path) -> tuple[bool, str | None]:
    """Run black on `path` if importable. Returns (ran, warning)."""
    try:
        import black  # noqa: F401
    except ImportError:
        return False, "black not installed"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "black", "--quiet", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return False, f"black exit={proc.returncode}: {proc.stderr.strip()}"
        return True, None
    except Exception as exc:
        return False, f"black raised: {exc}"


# ----------------------------------------------------------------- #
# Step 6 — git commit                                                 #
# ----------------------------------------------------------------- #

def _git_commit(
    repo_root: Path,
    rel_paths: list[str],
    message: str,
) -> str | None:
    """Stage `rel_paths` and commit with `message`. Returns the new
    commit SHA, or None if the commit was a no-op."""

    # Pre-flight: refuse if there are unrelated staged changes.
    staged = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(repo_root), text=True,
    ).strip().splitlines()
    unrelated = [s for s in staged if s and s not in rel_paths]
    if unrelated:
        raise FlushError(
            f"git index has unrelated staged changes: {unrelated[:5]}"
        )

    # Stage only the touched files.
    subprocess.check_call(
        ["git", "add", "--", *rel_paths],
        cwd=str(repo_root),
    )

    # Confirm the staged set matches.
    staged_after = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(repo_root), text=True,
    ).strip().splitlines()
    if set(staged_after) != set(rel_paths):
        raise FlushError(
            f"staged files {staged_after} do not match expected {rel_paths}"
        )

    # Commit.
    proc = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise FlushError(
            f"git commit failed (rc={proc.returncode}): {proc.stderr.strip()}"
        )

    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_root), text=True,
    ).strip()
    return sha


# ----------------------------------------------------------------- #
# Commit message builder (AD-10)                                      #
# ----------------------------------------------------------------- #

def _build_commit_message(
    rel_path: str,
    changes: list,             # list[ChangeRecord]
    original_buffer: str,
    new_buffer: str,
) -> str:
    """Build the AD-10 commit message from the change list."""
    head = changes[0]
    title = f"pidgin: {head.name} @ {rel_path}"
    body_blocks: list[str] = []
    for ch in changes:
        old = ch.old_comment if ch.old_comment is not None else "(none)"
        new = ch.new_comment

        if ch.prudence_skipped and ch.old_comment is None:
            prudence_label = "skipped (no old comment)"
        elif ch.prudence_skipped:
            prudence_label = "force"
        else:
            prudence_label = "TRUE"

        body_blocks.append(
            f"old: {old}\nnew: {new}\n\n"
            f"fidelity: TRUE\nprudence: {prudence_label}"
        )

    diff_summary = _short_diff_stat(original_buffer, new_buffer)
    sep = "\n\n---\n\n"
    return f"{title}\n\n" + sep.join(body_blocks) + f"\n\n{diff_summary}"


def _short_diff_stat(old: str, new: str) -> str:
    """Return a short line-count diff summary."""
    old_n = len(old.splitlines())
    new_n = len(new.splitlines())
    delta = new_n - old_n
    sign = "+" if delta >= 0 else ""
    return f"diff: {old_n} -> {new_n} lines ({sign}{delta})"


# ----------------------------------------------------------------- #
# Helper                                                              #
# ----------------------------------------------------------------- #

def _repo_rel(file_path: Path, repo_root: Path) -> str:
    """Return file_path as a repo-relative POSIX path."""
    return file_path.resolve().relative_to(repo_root.resolve()).as_posix()
