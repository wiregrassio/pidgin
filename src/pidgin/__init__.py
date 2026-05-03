"""pidgin — code access layer for LLM agents.

This package owns the OpenAI routing layer plus the nine verbs:
index, search, graph, egg, get, put, assert (internal), score, rank.

Sprint 1a shipped the read path: index, search, graph, egg, get.
Sprint 1b adds the write path: put, edit (context manager), flush.
"""

__version__ = "0.6.0a1"

# Read-path entry points (Sprint 1a).
from pidgin.get import get, GetResult                          # noqa: F401
from pidgin.search import search, SearchResult                  # noqa: F401
from pidgin.graph import ImportGraph                            # noqa: F401
from pidgin.egg import egg                                      # noqa: F401
from pidgin.index import index_file, index_directory, IndexResult, collect_repo_files  # noqa: F401
from pidgin.nest import Nest                                    # noqa: F401

# Write-path entry points (Sprint 1b).
from pidgin.edit import edit, EditContext, EditContextBusyError, ChangeRecord  # noqa: F401
from pidgin.put import put_symbol, PutResult, FidelityError, PrudenceWarning   # noqa: F401
from pidgin.flush import flush, FlushReport, FlushError                        # noqa: F401

# Eval verbs (Sprint v0.6).
from pidgin.assert_ import verify  # noqa: F401
from pidgin.score import score  # noqa: F401
from pidgin.rank import rank  # noqa: F401
