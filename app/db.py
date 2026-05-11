"""Dual-backend database layer (SQLite + Postgres).

All callers use ``?`` as the parameter placeholder regardless of backend; the
``Conn`` wrapper translates to ``%s`` for psycopg2. Rows returned by
``fetchone``/``fetchall`` are dict-like in both backends, so ``row["col"]``
access works identically.

To switch from SQLite to Postgres, set ``DATABASE_URL`` (env var, Streamlit
secret, or ``[storage] database_url`` in ``config.toml``).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .config import AppConfig, load_config

SCHEMA_DIR = Path(__file__).resolve().parent
SQLITE_SCHEMA = SCHEMA_DIR / "schema.sql"
POSTGRES_SCHEMA = SCHEMA_DIR / "schema_pg.sql"
CURRENT_SCHEMA_VERSION = 2


class Conn:
    """Lightweight connection wrapper that hides backend differences."""

    def __init__(self, backend: str, raw: Any):
        self.backend = backend
        self.raw = raw

    def _translate(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        sql = self._translate(sql)
        if self.backend == "postgres":
            cur = self.raw.cursor()
            cur.execute(sql, tuple(params))
            return cur
        return self.raw.execute(sql, tuple(params))

    def executemany(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> Any:
        sql = self._translate(sql)
        if self.backend == "postgres":
            cur = self.raw.cursor()
            cur.executemany(sql, [tuple(p) for p in params_seq])
            return cur
        return self.raw.executemany(sql, [tuple(p) for p in params_seq])

    def query_df(self, sql: str, params: Sequence[Any] = ()):
        """Run a SELECT and return a pandas DataFrame.

        Avoids ``pd.read_sql_query`` so we do not need SQLAlchemy as a
        dependency just for the Postgres path.
        """
        import pandas as pd

        sql_t = self._translate(sql)
        if self.backend == "postgres":
            cur = self.raw.cursor()
            cur.execute(sql_t, tuple(params))
            cols = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            cur.close()
            normalized = [
                {c: row[c] for c in cols} if hasattr(row, "keys") else dict(zip(cols, row))
                for row in rows
            ]
            return pd.DataFrame(normalized, columns=cols)
        cur = self.raw.execute(sql_t, tuple(params))
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return pd.DataFrame([dict(zip(cols, r)) for r in rows], columns=cols)

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def _open_sqlite(db_path: Path) -> Conn:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(db_path)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")
    raw.execute("PRAGMA journal_mode = WAL")
    return Conn("sqlite", raw)


def _open_postgres(url: str) -> Conn:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    raw = psycopg2.connect(url, cursor_factory=RealDictCursor)
    return Conn("postgres", raw)


@contextmanager
def connect(config: AppConfig | None = None) -> Iterator[Conn]:
    cfg = config or load_config()
    conn = _open_postgres(cfg.database_url) if cfg.is_postgres else _open_sqlite(cfg.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apply_schema(conn: Conn, sql_text: str) -> None:
    if conn.backend == "postgres":
        cur = conn.raw.cursor()
        try:
            cur.execute(sql_text)
        finally:
            cur.close()
    else:
        conn.raw.executescript(sql_text)


def initialize(config: AppConfig | None = None) -> None:
    """Apply schema and seed default categories if needed."""

    cfg = config or load_config()
    schema_path = POSTGRES_SCHEMA if cfg.is_postgres else SQLITE_SCHEMA
    schema_sql = schema_path.read_text(encoding="utf-8")

    with connect(cfg) as conn:
        _apply_schema(conn, schema_sql)

        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = (row["v"] if row else None) or 0
        if current < CURRENT_SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_version(version) VALUES (?) ON CONFLICT DO NOTHING",
                (CURRENT_SCHEMA_VERSION,),
            )

        count_row = conn.execute("SELECT COUNT(*) AS c FROM categories").fetchone()
        if int(count_row["c"]) == 0:
            for idx, name in enumerate(cfg.default_categories):
                is_income = 1 if name.lower() == "income" else 0
                conn.execute(
                    "INSERT INTO categories(name, sort_order, is_income) VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO NOTHING",
                    (name, idx, is_income),
                )


def _row_to_dict(row: Any, cols: list[str]) -> dict:
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {c: row[c] for c in cols}
    return dict(zip(cols, row))


def fetchall(query: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        cur = conn.execute(query, params)
        cols = [
            (d.name if hasattr(d, "name") else d[0])
            for d in (cur.description or [])
        ]
        return [_row_to_dict(r, cols) for r in cur.fetchall()]


def execute(query: str, params: tuple = ()) -> None:
    with connect() as conn:
        conn.execute(query, params)
