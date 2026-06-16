"""SQLite cache for the light memory index (10 min TTL by default)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from neosapien_mcp import constants
from neosapien_mcp.models.memory import MemoryLight


def _default_path() -> Path:
    override = os.environ.get("NEOSAPIEN_CACHE_PATH")
    if override:
        return Path(override).expanduser()
    d = Path.home() / ".neo-recall"
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d / "memories.db"


def _ttl() -> int:
    raw = os.environ.get("NEOSAPIEN_CACHE_TTL")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return constants.CACHE_TTL_SECONDS


class MemoryCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_path()
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY,
              payload TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def is_fresh(self) -> bool:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'synced_at'").fetchone()
        if not row:
            return False
        try:
            synced = float(row[0])
        except ValueError:
            return False
        return (time.time() - synced) < _ttl()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0]) if row else 0

    def replace_all(self, memories: list[MemoryLight]) -> None:
        self._conn.execute("DELETE FROM memories")
        self._conn.executemany(
            "INSERT INTO memories (id, payload, created_at) VALUES (?, ?, ?)",
            [(m.id, m.model_dump_json(), m.created_at) for m in memories],
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('synced_at', ?)",
            (str(time.time()),),
        )
        self._conn.commit()

    def list_all(self) -> list[MemoryLight]:
        rows = self._conn.execute(
            "SELECT payload FROM memories ORDER BY created_at DESC"
        ).fetchall()
        return [MemoryLight.model_validate_json(r[0]) for r in rows]

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()
