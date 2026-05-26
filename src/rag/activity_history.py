"""Per-user history for compare, AI notes, knowledge map, and timeline runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rag.auth import profile_path

_MAX_ENTRIES = 100
_MAX_BODY_CHARS = 4000

VALID_KINDS = frozenset({"compare", "notes", "map", "timeline"})


def _history_file(username: str) -> Path:
    p = profile_path(username)
    p.mkdir(parents=True, exist_ok=True)
    return p / "activity_history.json"


def load_activity_history(username: str) -> list[dict]:
    path = _history_file(username)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_activity_history(username: str, entries: list[dict]) -> None:
    _history_file(username).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_activity_by_kind(username: str, kind: str) -> list[dict]:
    k = (kind or "").strip().lower()
    if k not in VALID_KINDS:
        return []
    return [e for e in load_activity_history(username) if (e.get("kind") or "") == k]


def _trim_body(text: str) -> str:
    t = (text or "").strip()
    if len(t) <= _MAX_BODY_CHARS:
        return t
    return t[: _MAX_BODY_CHARS - 1].rstrip() + "…"


def append_activity(
    username: str,
    kind: str,
    *,
    title: str,
    summary: str = "",
    body: str = "",
    meta: dict | None = None,
) -> None:
    k = (kind or "").strip().lower()
    if k not in VALID_KINDS:
        return
    entries = load_activity_history(username)
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": k,
            "title": (title or "").strip() or k.title(),
            "summary": (summary or "").strip(),
            "body": _trim_body(body),
            "meta": meta or {},
        }
    )
    save_activity_history(username, entries[-_MAX_ENTRIES:])


def delete_activity_entry(username: str, kind: str, ts: str) -> bool:
    k = (kind or "").strip().lower()
    ts = (ts or "").strip()
    if k not in VALID_KINDS or not ts:
        return False
    entries = load_activity_history(username)
    new = [
        e
        for e in entries
        if not ((e.get("kind") or "") == k and (e.get("ts") or "").strip() == ts)
    ]
    if len(new) == len(entries):
        return False
    save_activity_history(username, new)
    return True
