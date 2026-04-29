# MODULE: pidgin.write
# DOES: Re-exports for the write sub-package.
#       M1: artifact_write (Mode 3), compress_write (Mode 4), ArtifactWriteResult.
#       M2: update (Mode 2 — transaction context manager), Transaction, EditOp, OverlappingEdit.

from pidgin.write.new import artifact_write, ArtifactWriteResult
from pidgin.write.compress import compress_write
from pidgin.write.update import update, Transaction, EditOp, OverlappingEdit

__all__ = [
    "artifact_write",
    "compress_write",
    "ArtifactWriteResult",
    "update",
    "Transaction",
    "EditOp",
    "OverlappingEdit",
]
