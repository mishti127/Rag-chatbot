"""Per-user document tool run history (separate from notebook notes)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rag.auth import profile_path
from rag.guardrails import strip_bracket_citations


def _history_file(username: str) -> Path:
    p = profile_path(username)
    p.mkdir(parents=True, exist_ok=True)
    return p / "tool_history.json"


def load_tool_history(username: str) -> list[dict]:
    path = _history_file(username)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_tool_history(username: str, entries: list[dict]) -> None:
    _history_file(username).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_tool_run(
    username: str,
    *,
    action: str,
    body: str,
    fmt: str = "plain",
    source: str | None = None,
) -> None:
    entries = load_tool_history(username)
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "label": action.replace("_", " ").title(),
            "body": strip_bracket_citations(body),
            "format": fmt,
            "source": source or "",
        }
    )
    save_tool_history(username, entries[-100:])


def delete_tool_history_entry(username: str, ts: str) -> bool:
    ts = (ts or "").strip()
    entries = load_tool_history(username)
    new = [e for e in entries if (e.get("ts") or "").strip() != ts]
    if len(new) == len(entries):
        return False
    save_tool_history(username, new)
    return True
