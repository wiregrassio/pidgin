# MODULE: pidgin.utils.git
# DOES: Git bracket helpers for artifact_write batch commits.
# PROVENANCE: Extracted and refactored from tools/store/audit.py (v0.1).
#             The legacy `_git_commit` in audit.py operated per-file and used
#             --allow-empty for pre-write brackets. This module commits a
#             LIST of paths in one operation with no pre-write bracket.
#
# pidgin v0.2 — extracted from tools/store/audit.py (v0.1)
# Provenance: function `crispr_write` (legacy Mode-2 only). This module
# implements Modes 3 (artifact_write) and 4 (compress_write) which were
# missing in v0.1.

import subprocess
from pathlib import Path


def find_project_root(start_dir: str) -> str | None:
    """Walk up from start_dir to find the nearest directory containing .git.

    Returns the directory path as a string, or None if no .git found.
    """
    current = Path(start_dir).resolve()
    for directory in [current] + list(current.parents):
        if (directory / ".git").exists():
            return str(directory)
    return None


def is_git_repo(project_root: str) -> bool:
    """Return True if project_root is inside a git repository.

    Runs `git rev-parse --git-dir` in project_root; returns True on exit 0.
    """
    result = subprocess.run(
        ["git", "-C", project_root, "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def git_commit_files(
    project_root: str,
    paths: list[str],
    message: str,
) -> str:
    """Stage `paths` and create one commit in `project_root`.

    All paths must be under project_root. Raises ValueError if any path
    escapes the root. Raises RuntimeError on git add/commit failure.

    Returns the full commit SHA of the resulting commit.
    """
    root = Path(project_root).resolve()

    # Security: reject paths that escape project_root.
    for p in paths:
        resolved = Path(p).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            raise ValueError(
                f"Path {p!r} is not under project_root {project_root!r}"
            )

    # Stage all files in one call.
    add_result = subprocess.run(
        ["git", "-C", str(root), "add", "--"] + paths,
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        raise RuntimeError(
            f"git add failed: {add_result.stderr.strip()}"
        )

    # Commit.
    commit_result = subprocess.run(
        ["git", "-C", str(root), "commit", "-m", message],
        capture_output=True,
        text=True,
    )
    if commit_result.returncode != 0:
        raise RuntimeError(
            f"git commit failed: {commit_result.stderr.strip()}"
        )

    # Return full SHA of the new commit.
    sha_result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return sha_result.stdout.strip()
