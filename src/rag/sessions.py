"""In-memory API session tokens."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

_TOKEN_TTL_SEC = 60 * 60 * 24 * 7  # 7 days
_sessions: dict[str, tuple[str, float]] = {}


@dataclass(frozen=True)
class SessionInfo:
    username: str
    token: str


def create_session(username: str) -> SessionInfo:
    token = secrets.token_urlsafe(32)
    _sessions[token] = (username.strip(), time.time())
    return SessionInfo(username=username.strip(), token=token)


def resolve_session(token: str | None) -> str | None:
    if not token:
        return None
    rec = _sessions.get(token.strip())
    if not rec:
        return None
    user, created = rec
    if time.time() - created > _TOKEN_TTL_SEC:
        _sessions.pop(token.strip(), None)
        return None
    return user


def revoke_session(token: str | None) -> None:
    if token:
        _sessions.pop(token.strip(), None)
