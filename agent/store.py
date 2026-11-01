"""SQLite persistence for matches, pause state, and poll status."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Match:
    id: int
    reddit_fullname: str
    subreddit: str
    title: str
    url: str
    author: str
    created_utc: float
    matched_keywords: tuple[str, ...]
    community_note: str
    status: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RunStatus:
    paused: bool
    last_run_at: str | None
    last_error: str | None
    last_found: int
    last_message: str | None


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reddit_fullname TEXT NOT NULL UNIQUE,
                    subreddit TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    author TEXT NOT NULL,
                    created_utc REAL NOT NULL,
                    matched_keywords TEXT NOT NULL,
                    community_note TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._ensure_meta(conn, "paused", "0")
            self._ensure_meta(conn, "last_run_at", "")
            self._ensure_meta(conn, "last_error", "")
            self._ensure_meta(conn, "last_found", "0")
            self._ensure_meta(conn, "last_message", "")

    @staticmethod
    def _ensure_meta(conn: sqlite3.Connection, key: str, default: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
            (key, default),
        )

    def get_paused(self) -> bool:
        return self._get_meta("paused") == "1"

    def set_paused(self, paused: bool) -> None:
        self._set_meta("paused", "1" if paused else "0")

    def record_run(self, *, found: int, message: str, error: str | None = None) -> None:
        self._set_meta("last_run_at", utc_now())
        self._set_meta("last_found", str(found))
        self._set_meta("last_message", message)
        self._set_meta("last_error", error or "")

    def status(self) -> RunStatus:
        return RunStatus(
            paused=self.get_paused(),
            last_run_at=self._get_meta("last_run_at") or None,
            last_error=self._get_meta("last_error") or None,
            last_found=int(self._get_meta("last_found") or "0"),
            last_message=self._get_meta("last_message") or None,
        )

    def upsert_match(
        self,
        *,
        reddit_fullname: str,
        subreddit: str,
        title: str,
        url: str,
        author: str,
        created_utc: float,
        matched_keywords: list[str],
        community_note: str,
    ) -> bool:
        """Insert a new match. Returns True if inserted, False if already known or ignored."""
        now = utc_now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT status FROM matches WHERE reddit_fullname = ?",
                (reddit_fullname,),
            ).fetchone()
            if existing:
                return False
            conn.execute(
                """
                INSERT INTO matches (
                    reddit_fullname, subreddit, title, url, author, created_utc,
                    matched_keywords, community_note, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
                """,
                (
                    reddit_fullname,
                    subreddit,
                    title,
                    url,
                    author,
                    created_utc,
                    json.dumps(matched_keywords),
                    community_note,
                    now,
                    now,
                ),
            )
            return True

    def list_matches(self, *, include_ignored: bool = False, limit: int = 100) -> list[Match]:
        query = "SELECT * FROM matches"
        params: list = []
        if not include_ignored:
            query += " WHERE status != 'ignored' AND status != 'deleted'"
        query += " ORDER BY created_utc DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_match(row) for row in rows]

    def set_status(self, match_id: int, status: str) -> bool:
        if status not in {"new", "reviewing", "ignored", "completed", "deleted"}:
            raise ValueError(f"Unsupported status: {status}")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE matches SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), match_id),
            )
            return cur.rowcount == 1

    def mark_fullname_deleted(self, reddit_fullname: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE matches SET status = 'deleted', updated_at = ? WHERE reddit_fullname = ? AND status != 'deleted'",
                (utc_now(), reddit_fullname),
            )
            return cur.rowcount == 1

    def known_fullnames(self, limit: int = 500) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT reddit_fullname FROM matches
                WHERE status != 'deleted'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [row["reddit_fullname"] for row in rows]

    def counts(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM matches GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}

    def _get_meta(self, key: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return "" if row is None else row["value"]

    def _set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @staticmethod
    def _row_to_match(row: sqlite3.Row) -> Match:
        keywords = tuple(json.loads(row["matched_keywords"]))
        return Match(
            id=row["id"],
            reddit_fullname=row["reddit_fullname"],
            subreddit=row["subreddit"],
            title=row["title"],
            url=row["url"],
            author=row["author"],
            created_utc=row["created_utc"],
            matched_keywords=keywords,
            community_note=row["community_note"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
