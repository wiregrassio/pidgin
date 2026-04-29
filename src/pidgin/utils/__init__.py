# pidgin v0.2 — extracted from tools/store/audit.py (v0.1)
# Provenance: function `crispr_write` (legacy Mode-2 only). This module
# implements Modes 3 (artifact_write) and 4 (compress_write) which were
# missing in v0.1.
# M10 adds: parser module re-export for `from pidgin.utils import parser, api`.

from pidgin.utils import api, parser  # noqa: F401 — re-exported for discovery
