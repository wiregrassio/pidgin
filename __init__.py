# MIT License
# Copyright (c) 2026 Elliot Willis
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

# MODULE: pidgin
# DOES: Write-model package for artifact_write (Modes 3/4) and future update
#       semantics. Supersedes the per-operation git bracket in tools/store/audit.py.
# VERSION: 0.2.0

__version__ = "0.2.0"

# ---------------------------------------------------------------------------
# Re-exports — public API (M10 adds store + pipeline + prompts re-exports)
# ---------------------------------------------------------------------------

# pidgin.write — Modes 2, 3, 4
# Note: `update` is the function (factory returning Transaction), not the module.
# Naming collision resolved: `from pidgin.write import update` imports the function.
from pidgin.write import artifact_write, compress_write, ArtifactWriteResult
from pidgin.write import update

# pidgin.prompts
from pidgin.prompts import assemble_xml_prompt

# pidgin.pipeline
from pidgin.pipeline import run_embedding_mld_pipeline_for_functions

# pidgin.store — re-exported as module references (callers use nest.section_put_chroma etc.)
from pidgin.store import nest, audit

__all__ = [
    # write
    "artifact_write",
    "compress_write",
    "ArtifactWriteResult",
    "update",
    # prompts
    "assemble_xml_prompt",
    # pipeline
    "run_embedding_mld_pipeline_for_functions",
    # store (module refs)
    "nest",
    "audit",
]
