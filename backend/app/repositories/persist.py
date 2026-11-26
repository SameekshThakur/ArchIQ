"""Small SQLite store for what people add to the platform: uploaded documents, ad-hoc reviews and inventory imports.

The seeded Northwind estate stays read-only and is regenerated deterministically; only user-created items are saved here, so a restart no longer
loses them. Location: ``backend/data/archiq.db`` by default, or whatever ``ARCHIQ_DB`` points to. ``ARCHIQ_DB=:memory:`` turns persistence off.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_ROOT

log = logging.getLogger("archiq.persist")
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads (n INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items (n INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_kind ON items(kind, n);
"""


def db_path() -> str:
    return os.environ.get("ARCHIQ_DB") or str(BACKEND_ROOT / "data" / "archiq.db")


def _open(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    c.executescript(SCHEMA)
    return c


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is not None:
            return _conn
        path = db_path()
        try:
            _conn = _open(path)
        except sqlite3.DatabaseError:
            # a damaged file must never stop the app from starting: keep it aside and start fresh
            bad = Path(path + ".corrupt")
            try:
                bad.unlink(missing_ok=True)
                Path(path).replace(bad)
                log.warning("database %s was unreadable; moved to %s and recreated", path, bad)
                _conn = _open(path)
            except OSError:
                _conn = _open(":memory:")
        except OSError:
            log.warning("cannot write %s; continuing without persistence", path)
            _conn = _open(":memory:")
        return _conn


def close() -> None:
    """Drop the connection (tests use this to switch database files)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ uploaded documents
def add_upload(title: str, text: str, doc_type: str, domain: str) -> int:
    with _lock:
        cur = conn().execute("INSERT INTO uploads (created_at, payload) VALUES (?, ?)", (_now(), json.dumps(dict(title=title, text=text, doc_type=doc_type, domain=domain))))
        return int(cur.lastrowid or 0)


def list_uploads() -> list[tuple[int, dict]]:
    with _lock:
        return [(n, json.loads(p)) for n, p in conn().execute("SELECT n, payload FROM uploads ORDER BY n")]


def delete_upload(n: int) -> bool:
    with _lock:
        return conn().execute("DELETE FROM uploads WHERE n = ?", (n,)).rowcount > 0


# ------------------------------------------------------------------ generic saved items (reviews, imports)
def add_item(kind: str, payload: dict[str, Any]) -> int:
    with _lock:
        cur = conn().execute("INSERT INTO items (kind, created_at, payload) VALUES (?, ?, ?)", (kind, _now(), json.dumps(payload)))
        return int(cur.lastrowid or 0)


def list_items(kind: str, limit: int = 20) -> list[dict]:
    with _lock:
        rows = conn().execute("SELECT n, created_at, payload FROM items WHERE kind = ? ORDER BY n DESC LIMIT ?", (kind, limit)).fetchall()
    return [dict(id=n, created_at=c, **json.loads(p)) for n, c, p in rows]


def get_item(kind: str, n: int) -> dict | None:
    with _lock:
        row = conn().execute("SELECT n, created_at, payload FROM items WHERE kind = ? AND n = ?", (kind, n)).fetchone()
    return dict(id=row[0], created_at=row[1], **json.loads(row[2])) if row else None


def update_item(kind: str, n: int, payload: dict[str, Any]) -> bool:
    with _lock:
        return conn().execute("UPDATE items SET payload = ? WHERE kind = ? AND n = ?", (json.dumps(payload), kind, n)).rowcount > 0


def delete_item(kind: str, n: int) -> bool:
    with _lock:
        return conn().execute("DELETE FROM items WHERE kind = ? AND n = ?", (kind, n)).rowcount > 0


def clear_all() -> None:
    with _lock:
        c = conn()
        c.execute("DELETE FROM uploads")
        c.execute("DELETE FROM items WHERE kind != 'connection'")  # saved platform connections survive a reset
