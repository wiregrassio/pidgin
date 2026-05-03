"""pidgin.edit() context manager — batches get/put on a single file.

Usage:
    with pidgin.edit("path/to/file.py") as ctx:
        source, comment, sig = ctx.get("function_name")
        ctx.put(modified_source, new_comment)
        ctx.flush()  # or ctx.dump() for unverified emergency dump
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pidgin.extract import extract_symbol_by_name
from pidgin.nest import Nest
from pidgin.put import put_symbol, PutResult


# ----------------------------------------------------------------- #
# Errors                                                             #
# ----------------------------------------------------------------- #

class EditContextBusyError(RuntimeError):
    """Raised when a second context is opened on a file that is
    already under edit in this process (AD-6)."""


# ----------------------------------------------------------------- #
# Change records (used by flush for the commit message)              #
# ----------------------------------------------------------------- #

@dataclass
class ChangeRecord:
    name: str
    old_comment: str | None
    new_comment: str
    fidelity_evidence: str
    prudence_skipped: bool
    prudence_evidence: str | None


# ----------------------------------------------------------------- #
# EditContext                                                        #
# ----------------------------------------------------------------- #

_OPEN_CONTEXTS: dict[Path, "EditContext"] = {}


class EditContext:
    """Holds the buffer for one file and the queue of pending changes.

    The context does NOT auto-flush on __exit__. The caller must call
    flush() (writes + black + reindex + graph + egg + commit) or
    dump() (writes only, marks output as unverified).
    """

    def __init__(self, file_path: Path, *, nest: Nest | None = None) -> None:
        self._file_path = Path(file_path).resolve()
        self._nest: Nest | None = nest
        self._buffer: str = ""
        self._original_buffer: str = ""
        self._changes: list[ChangeRecord] = []
        self._flushed: bool = False
        # Cache of (name -> last comment seen at ctx.get time) so put can
        # pass the right old_comment to put_symbol without an extra LanceDB
        # roundtrip.
        self._comment_cache: dict[str, str | None] = {}

    # ----------------------- entry / exit ------------------------- #

    def __enter__(self) -> "EditContext":
        if self._file_path in _OPEN_CONTEXTS:
            raise EditContextBusyError(
                f"already editing {self._file_path}"
            )
        self._buffer = self._file_path.read_text(encoding="utf-8")
        self._original_buffer = self._buffer
        if self._nest is None:
            self._nest = Nest()
            self._nest.ensure_table()
        _OPEN_CONTEXTS[self._file_path] = self
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # No auto-flush. The buffer is dropped — disk is untouched.
        _OPEN_CONTEXTS.pop(self._file_path, None)

    # ----------------------- get --------------------------------- #

    def get(self, name: str) -> tuple[str, str | None, str | None]:
        """Extract source + comment + signature from the in-memory buffer.

        Returns (source, comment, signature). source is the AST-extracted
        symbol text from the current buffer. comment is from LanceDB
        (None if the symbol has not been indexed). signature is from the
        AST.
        """
        sym = extract_symbol_by_name(self._buffer, name)
        if sym is None:
            raise ValueError(
                f"symbol {name!r} not found in {self._file_path}"
            )

        # LanceDB description lookup (if the symbol is indexed).
        comment: str | None = None
        try:
            rel = self._file_path.relative_to(self._nest.repo_root).as_posix()
        except ValueError:
            rel = self._file_path.as_posix()
        symbol_id = f"{rel}::{name}"
        record = self._nest.get_by_id(symbol_id)
        if record is not None:
            comment = record.get("description")

        self._comment_cache[name] = comment
        return sym.source, comment, sym.signature

    # ----------------------- put --------------------------------- #

    def put(
        self,
        modified_source: str,
        new_comment: str,
        *,
        name: str | None = None,
        force: bool = False,
    ) -> PutResult:
        """Replace a symbol in the buffer.

        name is required — the name of the symbol to replace.

        Re-parses the buffer after each put so subsequent ctx.get()
        sees correct line numbers.
        """
        if name is None:
            raise ValueError("ctx.put requires the name of the symbol to replace")

        old_comment = self._comment_cache.get(name)

        result = put_symbol(
            buffer=self._buffer,
            name=name,
            new_source=modified_source,
            new_comment=new_comment,
            old_comment=old_comment,
            force=force,
        )

        # Update buffer with the spliced result.
        self._buffer = result.new_source

        # Track for the commit message.
        self._changes.append(ChangeRecord(
            name=name,
            old_comment=old_comment,
            new_comment=new_comment,
            fidelity_evidence=result.fidelity_evidence,
            prudence_skipped=result.prudence_skipped,
            prudence_evidence=result.prudence_evidence,
        ))

        # Refresh the comment cache so a subsequent ctx.get(name)
        # returns the new comment.
        self._comment_cache[name] = new_comment
        return result

    # ----------------------- flush ------------------------------- #

    def flush(self):
        """Write buffer to disk and run the post-write pipeline.

        Implementation lives in pidgin.flush — imported lazily so a
        from-scratch import of pidgin.edit doesn't pull lancedb /
        rustworkx / git surface unnecessarily for callers that only
        want to inspect the context manager API.
        """
        from pidgin.flush import flush as _flush
        if self._flushed:
            raise RuntimeError("EditContext already flushed; open a new context")
        if not self._changes:
            # No-op: nothing to flush.
            return None
        report = _flush(
            file_path=self._file_path,
            buffer=self._buffer,
            original_buffer=self._original_buffer,
            changes=self._changes,
            nest=self._nest,
        )
        self._flushed = True
        return report

    def dump(self) -> Path:
        """Emergency unverified dump. Writes buffer to disk WITHOUT
        running fidelity, black, LanceDB, graph, egg, or commit. Marks
        the output with an unverified-dump comment line at end of file.

        Returns the file path written. The dump path is the original
        file path — the caller can `git diff` against the working tree
        to inspect.
        """
        from datetime import datetime, timezone
        ts = datetime.now(tz=timezone.utc).isoformat()
        marker = f"\n# pidgin: unverified dump @ {ts}\n"
        self._file_path.write_text(self._buffer + marker, encoding="utf-8")
        return self._file_path


# ----------------------------------------------------------------- #
# Public entry point                                                  #
# ----------------------------------------------------------------- #

def edit(file_path: str | Path, *, nest: Nest | None = None) -> EditContext:
    """Open an EditContext for `file_path`.

    Use as a context manager:
        with pidgin.edit(path) as ctx:
            ...
            ctx.flush()
    """
    return EditContext(Path(file_path), nest=nest)
