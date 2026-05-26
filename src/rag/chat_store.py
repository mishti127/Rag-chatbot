"""Per-user chat threads (ChatGPT-style sidebar history)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rag.auth import profile_path


def _chat_file(username: str) -> Path:
    p = profile_path(username).parent
    p.mkdir(parents=True, exist_ok=True)
    return p / "chats.json"


def _load(username: str) -> dict:
    path = _chat_file(username)
    if not path.is_file():
        return {"threads": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"threads": []}
    except (OSError, json.JSONDecodeError):
        return {"threads": []}


def _save(username: str, data: dict) -> None:
    _chat_file(username).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_threads(username: str) -> list[dict]:
    threads = _load(username).get("threads") or []
    out = []
    for t in threads:
        if not isinstance(t, dict):
            continue
        out.append(
            {
                "id": t.get("id"),
                "title": t.get("title") or "New chat",
                "updated": t.get("updated"),
            }
        )
    out.sort(key=lambda x: x.get("updated") or "", reverse=True)
    return out


def get_thread(username: str, thread_id: str) -> dict | None:
    for t in _load(username).get("threads") or []:
        if isinstance(t, dict) and t.get("id") == thread_id:
            return t
    return None


def create_thread(username: str, title: str = "New chat") -> dict:
    data = _load(username)
    now = datetime.now(timezone.utc).isoformat()
    thread = {
        "id": uuid.uuid4().hex[:12],
        "title": title[:80],
        "created": now,
        "updated": now,
        "messages": [],
    }
    data.setdefault("threads", []).insert(0, thread)
    _save(username, data)
    return thread


def delete_thread(username: str, thread_id: str) -> bool:
    data = _load(username)
    before = len(data.get("threads") or [])
    data["threads"] = [t for t in data.get("threads") or [] if t.get("id") != thread_id]
    if len(data["threads"]) < before:
        _save(username, data)
        return True
    return False


def append_messages(
    username: str,
    thread_id: str,
    *,
    user_content: str,
    assistant_content: str,
    citations: list[str],
) -> dict | None:
    data = _load(username)
    now = datetime.now(timezone.utc).isoformat()
    for t in data.get("threads") or []:
        if t.get("id") != thread_id:
            continue
        if not t.get("title") or t.get("title") == "New chat":
            t["title"] = user_content[:80] + ("…" if len(user_content) > 80 else "")
        t.setdefault("messages", []).append(
            {"role": "user", "content": user_content, "ts": now}
        )
        t["messages"].append(
            {
                "role": "assistant",
                "content": assistant_content,
                "citations": citations,
                "ts": now,
            }
        )
        t["updated"] = now
        _save(username, data)
        return t
    return None
