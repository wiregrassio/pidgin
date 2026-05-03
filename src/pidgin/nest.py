"""LanceDB-backed symbol store for pidgin.

Nest manages the on-disk LanceDB database under .pidgin/nest/lance/
and exposes CRUD over the 12-field symbols table.
"""
from __future__ import annotations

from pathlib import Path

import lancedb
import lancedb.table
import pyarrow as pa


# 256-dim float32 fixed-size list for embeddings.
VECTOR_TYPE = pa.list_(pa.float32(), 256)

# Canonical symbols schema. The 12 fields are fixed by the target spec.
SYMBOLS_SCHEMA = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("file_path", pa.string(), nullable=False),
    pa.field("kind", pa.string(), nullable=False),
    pa.field("description", pa.string(), nullable=True),
    pa.field("description_vector", VECTOR_TYPE, nullable=False),
    pa.field("signature", pa.string(), nullable=False),
    pa.field("signature_vector", VECTOR_TYPE, nullable=False),
    pa.field("source_hash", pa.string(), nullable=False),
    pa.field("last_modified", pa.string(), nullable=False),
    pa.field("git_author", pa.string(), nullable=False),
    pa.field("mutation_count", pa.int64(), nullable=False),
    pa.field("repo_id", pa.string(), nullable=False),
])


def _find_repo_root(start: Path) -> Path:
    """Walk up from `start` looking for a .git directory.

    Returns the first ancestor (inclusive of start) that contains
    a .git entry. If none is found, returns `start` itself — Nest
    will create .pidgin/ relative to whatever caller chose.
    """
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return cur


class Nest:
    """LanceDB-backed symbol store rooted at a repo's .pidgin/nest/."""

    def __init__(self, repo_root: Path | None = None) -> None:
        if repo_root is None:
            self._repo_root = _find_repo_root(Path.cwd())
        else:
            self._repo_root = Path(repo_root).resolve()

        self._nest_path = self._repo_root / ".pidgin" / "nest"
        self._nest_path.mkdir(parents=True, exist_ok=True)

        self._db: lancedb.DBConnection | None = None

    # ---------- properties ----------

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def nest_path(self) -> Path:
        return self._nest_path

    # ---------- connection / schema ----------

    def connect(self) -> lancedb.DBConnection:
        """Open (or reuse) a LanceDB connection at .pidgin/nest/lance/."""
        if self._db is None:
            lance_dir = self._nest_path / "lance"
            lance_dir.mkdir(parents=True, exist_ok=True)
            self._db = lancedb.connect(str(lance_dir))
        return self._db

    def ensure_table(self) -> lancedb.table.Table:
        """Create or open the 'symbols' table with SYMBOLS_SCHEMA.

        Uses db.list_tables() (lancedb 0.30.2) — db.table_names() is
        deprecated. In 0.30.2 list_tables() returns a
        ListTablesResponse with a `.tables` attribute (list[str]); we
        also fall back to `.table_names` and to plain iteration for
        forward/back compatibility.
        """
        db = self.connect()
        existing = db.list_tables()

        names: list[str]
        if hasattr(existing, "tables"):
            names = list(existing.tables)
        elif hasattr(existing, "table_names"):
            names = list(existing.table_names)
        else:
            try:
                names = list(existing)
            except TypeError:
                names = []

        if "symbols" not in names:
            return db.create_table("symbols", schema=SYMBOLS_SCHEMA)
        return db.open_table("symbols")

    # ---------- writes ----------

    def upsert(self, records: list[dict]) -> None:
        """Upsert records into the symbols table, matching on 'id'.

        Records are coerced into a PyArrow Table against SYMBOLS_SCHEMA
        before being handed to merge_insert.execute() — this avoids
        type-coercion surprises in lancedb 0.30.2.
        """
        if not records:
            return
        tbl = self.ensure_table()
        pa_table = pa.Table.from_pylist(records, schema=SYMBOLS_SCHEMA)
        (
            tbl.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(pa_table)
        )

    def delete_by_file(self, file_path: str) -> None:
        """Delete all rows whose file_path equals `file_path`."""
        tbl = self.ensure_table()
        # SQL-style predicate; escape single quotes by doubling them.
        escaped = file_path.replace("'", "''")
        tbl.delete(f"file_path = '{escaped}'")

    # ---------- reads ----------

    def get_by_id(self, symbol_id: str) -> dict | None:
        """Return the single record with the given id, or None."""
        tbl = self.ensure_table()
        escaped = symbol_id.replace("'", "''")
        rows = tbl.search().where(f"id = '{escaped}'").limit(1).to_list()
        if not rows:
            return None
        return rows[0]

    def get_by_file(self, file_path: str) -> list[dict]:
        """Return all records for an exact file_path match."""
        tbl = self.ensure_table()
        escaped = file_path.replace("'", "''")
        return tbl.search().where(f"file_path = '{escaped}'").to_list()

    def get_by_directory(self, dir_path: str) -> list[dict]:
        """Return all records whose file_path starts with dir_path/.

        Empty string and '/' are treated as "whole repo" — no prefix
        filter is applied. Otherwise a trailing '/' is appended (if
        missing) so that 'pidgin' does not match 'pidgin_extras/...'.
        """
        tbl = self.ensure_table()
        if dir_path in ("", "/"):
            return tbl.search().to_list()

        prefix = dir_path if dir_path.endswith("/") else dir_path + "/"
        escaped = prefix.replace("'", "''")
        # LanceDB / DataFusion supports LIKE with '%' wildcard.
        return tbl.search().where(f"file_path LIKE '{escaped}%'").to_list()

    def search(
        self,
        vector: list[float],
        column: str,
        top_k: int = 10,
    ) -> list[dict]:
        """Cosine vector similarity search on `column`.

        Returns the raw list of dicts as produced by LanceDB,
        including the injected '_distance' column. Callers convert
        distance to similarity.
        """
        tbl = self.ensure_table()
        return (
            tbl.search(vector, vector_column_name=column)
            .metric("cosine")
            .limit(top_k)
            .to_list()
        )
