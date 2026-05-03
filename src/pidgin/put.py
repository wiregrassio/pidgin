"""AST-targeted symbol replacement with assert-gated fidelity.

put_symbol() takes a buffer (current source string) and produces a
new buffer (string) with one symbol replaced. It does NOT write to
disk — the caller (EditContext or a one-off CLI wrapper) owns disk.

Fidelity (mandatory): does the new source match the new comment?
Prudence (default-on, skippable with force=True): is the comment
delta reasonable?

Both checks route through pidgin._assert.run_assert.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field

from pidgin._assert import run_assert
from pidgin.extract import extract_symbol_by_name


# ----------------------------------------------------------------- #
# Errors                                                             #
# ----------------------------------------------------------------- #

class FidelityError(Exception):
    """Raised when the assert fidelity check returns FALSE."""

    def __init__(self, message: str, evidence: str) -> None:
        super().__init__(message)
        self.evidence = evidence


class PrudenceWarning(Exception):
    """Raised when the assert prudence check returns FALSE and force=False.

    Despite the name, this is an Exception, not a Python warning —
    callers catch it. The class name matches the spec's vocabulary.
    """

    def __init__(self, message: str, evidence: str) -> None:
        super().__init__(message)
        self.evidence = evidence


# ----------------------------------------------------------------- #
# Result model                                                       #
# ----------------------------------------------------------------- #

@dataclass
class PutResult:
    name: str
    new_source: str           # the WHOLE-FILE source after splice
    old_comment: str | None
    new_comment: str
    start_line: int           # 1-based, inclusive (matched Symbol.start_line)
    end_line: int             # 1-based, inclusive
    fidelity_evidence: str
    prudence_skipped: bool
    prudence_evidence: str | None  # None if skipped


# ----------------------------------------------------------------- #
# put_symbol                                                         #
# ----------------------------------------------------------------- #

def put_symbol(
    *,
    buffer: str,
    name: str,
    new_source: str,
    new_comment: str,
    old_comment: str | None,
    fidelity_model: str = "gpt-4.1",
    prudence_model: str = "gpt-4.1",
    force: bool = False,
) -> PutResult:
    """Replace one symbol in `buffer` and return the resulting buffer.

    Steps:
      1. Validate new_source parses as Python (ast.parse).
      2. Locate the symbol via extract_symbol_by_name(buffer, name).
         Raise ValueError if not found.
      3. Run fidelity: assert(new_source matches new_comment).
         On FALSE -> raise FidelityError. No override.
      4. If force is False AND old_comment is not None:
         Run prudence: assert(comment delta is reasonable).
         On FALSE -> raise PrudenceWarning. force=True bypasses.
      5. Splice: replace lines [start_line .. end_line] in buffer with
         new_source.splitlines().
      6. Return PutResult.
    """
    # Step 1: AST validation
    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        raise ValueError(f"new_source is not valid Python: {exc}") from exc

    # Step 2: Locate symbol in buffer
    sym = extract_symbol_by_name(buffer, name)
    if sym is None:
        raise ValueError(f"symbol {name!r} not found in buffer")

    # Step 3: Fidelity check (mandatory)
    fidelity_claim = (
        "The provided code implements the behavior described by the comment."
    )
    fidelity_verdict, fidelity_evidence = run_assert(
        fidelity_claim,
        new_comment,
        new_source,
        model=fidelity_model,
    )
    if not fidelity_verdict:
        raise FidelityError(
            f"Fidelity check failed for {name!r}: code does not match comment",
            fidelity_evidence,
        )

    # Step 4: Prudence check (skippable via force=True or old_comment is None)
    prudence_skipped = force or old_comment is None
    prudence_evidence: str | None = None

    if not prudence_skipped:
        prudence_claim = (
            "The change from the OLD comment to the NEW comment describes a "
            "reasonable refactor of a single function/class — same general "
            "intent, related domain, no scope explosion."
        )
        prudence_verdict, prudence_evidence = run_assert(
            prudence_claim,
            f"OLD comment:\n{old_comment}",
            f"NEW comment:\n{new_comment}",
            model=prudence_model,
        )
        if not prudence_verdict:
            raise PrudenceWarning(
                f"Prudence check failed for {name!r}: comment delta is unreasonable",
                prudence_evidence,
            )

    # Step 5: Splice
    buffer_lines = buffer.splitlines(keepends=False)
    new_lines = new_source.splitlines(keepends=False)
    prefix = buffer_lines[: sym.start_line - 1]
    suffix = buffer_lines[sym.end_line :]
    out_lines = prefix + new_lines + suffix
    new_buffer = "\n".join(out_lines)
    if buffer.endswith("\n"):
        new_buffer += "\n"

    # Step 6: Return result
    return PutResult(
        name=name,
        new_source=new_buffer,
        old_comment=old_comment,
        new_comment=new_comment,
        start_line=sym.start_line,
        end_line=sym.end_line,
        fidelity_evidence=fidelity_evidence,
        prudence_skipped=prudence_skipped,
        prudence_evidence=prudence_evidence,
    )


# --------------------------------------------------------------------------- #
# CLI entry point                                                              #
# --------------------------------------------------------------------------- #

def main() -> int:
    import argparse
    import sys
    from pathlib import Path

    def log(msg: str) -> None:
        print(f"     put | {msg}", file=sys.stderr, flush=True)

    def _read_source(arg: str) -> str:
        if arg == "-":
            return sys.stdin.read()
        return Path(arg).read_text(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="pidgin put",
                                     description="put — pidgin symbol replacement")
    parser.add_argument("--file", required=True, help="Python file to edit")
    parser.add_argument("--name", required=True, help="Symbol name (Class.method ok)")
    parser.add_argument("--new-source", required=True,
                        help="Path to new source, or '-' for stdin")
    parser.add_argument("--new-comment", required=True, help="New one-sentence comment")
    parser.add_argument("--force", action="store_true", help="Skip prudence check")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        log(f"error: {file_path} is not a file")
        return 1

    new_source = _read_source(args.new_source)

    import pidgin

    try:
        with pidgin.edit(file_path) as ctx:
            ctx.put(new_source, args.new_comment, name=args.name, force=args.force)
            report = ctx.flush()
    except pidgin.FidelityError as e:
        log(f"FIDELITY FAIL: {e}\n{e.evidence}")
        return 2
    except pidgin.PrudenceWarning as e:
        log(f"PRUDENCE WARN (re-run with --force to override): {e}\n{e.evidence}")
        return 3
    except pidgin.FlushError as e:
        log(f"FLUSH FAIL: {e}")
        return 4

    if report is None:
        log("no changes flushed")
        return 0
    log(f"committed {report.commit_sha}")
    print(report.commit_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
