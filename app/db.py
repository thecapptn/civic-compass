"""SQLite access layer.

Read-heavy by design: the public surface is fully cacheable and never renders per-user state
on the critical path. Writes are limited to correction reports, saved plans, and ops actions.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR.parent / "data" / "civic_compass.sqlite3"
SCHEMA_PATH = APP_DIR / "schema.sql"


def db_path() -> Path:
    return Path(os.environ.get("CIVIC_COMPASS_DB", str(DEFAULT_DB)))


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def query_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def audit(conn: sqlite3.Connection, actor: str, action: str, entity_table: str | None = None,
          entity_id: str | None = None, source_record_id: str | None = None,
          note: str | None = None) -> None:
    from .logic import utc_now_iso
    conn.execute(
        "INSERT INTO audit_log (at, actor, action, entity_table, entity_id, source_record_id, note)"
        " VALUES (?,?,?,?,?,?,?)",
        (utc_now_iso(), actor, action, entity_table, entity_id, source_record_id, note),
    )
    conn.commit()
