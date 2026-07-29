"""État persistant du scanner (SQLite) : un scan instantané ne suffit pas à
savoir si un fichier est "utilisé" — on doit comparer l'atime observé d'un
scan à l'autre. Cette base garde donc l'historique minimal nécessaire pour ça.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    first_seen REAL NOT NULL,
    first_atime REAL NOT NULL,
    last_atime REAL NOT NULL,
    last_used_at REAL NOT NULL,
    last_scan_time REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    deleted_at REAL
);

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class FileStat:
    path: str
    size_bytes: int
    mtime: float
    atime: float


class StateDB:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def upsert_seen(self, stat: FileStat, scan_time: float) -> None:
        """Insère ou met à jour un fichier vu pendant le scan courant.

        `last_used_at` n'avance que si l'atime observé a progressé par rapport
        à la valeur connue: c'est le signal qu'un accès a eu lieu depuis le
        dernier scan.
        """
        row = self._conn.execute(
            "SELECT last_atime, last_used_at, first_seen, first_atime FROM files WHERE path = ?",
            (stat.path,),
        ).fetchone()

        if row is None:
            self._conn.execute(
                """
                INSERT INTO files (
                    path, size_bytes, mtime, first_seen, first_atime,
                    last_atime, last_used_at, last_scan_time, status, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL)
                """,
                (stat.path, stat.size_bytes, stat.mtime, scan_time, stat.atime,
                 stat.atime, stat.atime, scan_time),
            )
            return

        prev_last_atime, prev_last_used_at, first_seen, first_atime = row
        last_used_at = stat.atime if stat.atime > prev_last_atime else prev_last_used_at

        self._conn.execute(
            """
            UPDATE files
            SET size_bytes = ?, mtime = ?, last_atime = ?, last_used_at = ?,
                last_scan_time = ?, status = 'active', deleted_at = NULL
            WHERE path = ?
            """,
            (stat.size_bytes, stat.mtime, stat.atime, last_used_at, scan_time, stat.path),
        )

    def mark_missing_as_deleted(self, scan_time: float) -> int:
        """Marque comme supprimés les fichiers actifs non revus lors du scan courant."""
        cur = self._conn.execute(
            "UPDATE files SET status = 'deleted', deleted_at = ? "
            "WHERE status = 'active' AND last_scan_time < ?",
            (scan_time, scan_time),
        )
        return cur.rowcount

    def commit(self) -> None:
        self._conn.commit()

    def iter_active_files(self):
        cur = self._conn.execute(
            "SELECT path, size_bytes, first_seen, last_atime, last_used_at "
            "FROM files WHERE status = 'active'"
        )
        for row in cur:
            yield row

    def aggregate_counts(self, now: float, stale_seconds: float) -> dict:
        """Calcule les compteurs used/stale/unknown + octets, en une passe SQL."""
        row = self._conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(size_bytes), 0) AS total_bytes,
                COALESCE(SUM(CASE
                    WHEN (? - first_seen) > ? AND (? - last_used_at) <= ? THEN 1 ELSE 0 END), 0) AS used,
                COALESCE(SUM(CASE
                    WHEN (? - first_seen) > ? AND (? - last_used_at) > ? THEN 1 ELSE 0 END), 0) AS stale,
                COALESCE(SUM(CASE
                    WHEN (? - first_seen) > ? AND (? - last_used_at) > ? THEN size_bytes ELSE 0 END), 0) AS stale_bytes,
                COALESCE(SUM(CASE WHEN (? - first_seen) <= ? THEN 1 ELSE 0 END), 0) AS unknown
            FROM files
            WHERE status = 'active'
            """,
            (
                now, stale_seconds, now, stale_seconds,
                now, stale_seconds, now, stale_seconds,
                now, stale_seconds, now, stale_seconds,
                now, stale_seconds,
            ),
        ).fetchone()
        keys = ("total", "total_bytes", "used", "stale", "stale_bytes", "unknown")
        return dict(zip(keys, row))
