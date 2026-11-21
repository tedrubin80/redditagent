"""Ephemeral in-memory sessions for pasted API credentials.

Credentials live only in process memory and are removed on logout or
process restart. Nothing is written to disk.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field


COOKIE_NAME = "agentman_sid"


@dataclass
class SessionData:
    treg_token: str = field(default="", repr=False)
    created_at: float = field(default_factory=time.time)

    def has_treg(self) -> bool:
        return bool(self.treg_token)

    def clear(self) -> None:
        self.treg_token = ""

    def public_status(self) -> dict:
        return {
            "configured": self.has_treg(),
            "source": "session" if self.has_treg() else None,
        }


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionData] = {}

    def create(self) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[sid] = SessionData()
        return sid

    def get(self, sid: str | None) -> SessionData | None:
        if not sid:
            return None
        with self._lock:
            return self._sessions.get(sid)

    def get_or_create(self, sid: str | None) -> tuple[str, SessionData]:
        existing = self.get(sid)
        if existing is not None and sid:
            return sid, existing
        new_sid = self.create()
        session = self.get(new_sid)
        assert session is not None
        return new_sid, session

    def delete(self, sid: str | None) -> None:
        if not sid:
            return
        with self._lock:
            self._sessions.pop(sid, None)


SESSIONS = SessionStore()
