"""Log of document uploads per user (for History → Documents)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rag.auth import profile_path


def _log_file(username: str) -> Path:
    p = profile_path(username)
    p.mkdir(parents=True, exist_ok=True)
    return p / "uploads.json"


def load_upload_log(username: str) -> list[dict]:
    path = _log_file(username)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def append_upload(username: str, filename: str) -> None:
    entries = load_upload_log(username)
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "filename": filename,
            "action": "uploaded",
        }
    )
    save_upload_log(username, entries[-200:])


def append_removal(username: str, filename: str) -> None:
    entries = load_upload_log(username)
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "filename": filename,
            "action": "removed",
        }
    )
    save_upload_log(username, entries[-200:])


def save_upload_log(username: str, entries: list[dict]) -> None:
    _log_file(username).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_upload_log_entry(username: str, ts: str) -> bool:
    ts = (ts or "").strip()
    entries = load_upload_log(username)
    new = [e for e in entries if (e.get("ts") or "").strip() != ts]
    if len(new) == len(entries):
        return False
    save_upload_log(username, new)
    return True
