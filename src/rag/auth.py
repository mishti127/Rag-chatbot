"""User accounts for the web UI."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from rag.config import INDEX_DATA_DIR

_USERS_FILE = INDEX_DATA_DIR / "users.json"
_DEFAULT_THEME = "midnight"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class UserProfile:
    username: str
    display_name: str
    email: str
    theme: str = _DEFAULT_THEME


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _load_users_db() -> dict[str, dict]:
    if _USERS_FILE.is_file():
        try:
            return json.loads(_USERS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_users_db(db: dict[str, dict]) -> None:
    _USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USERS_FILE.write_text(json.dumps(db, indent=2), encoding="utf-8")


def ensure_bootstrap_user() -> None:
    """Create one admin user from env only if no users exist (not shown in UI)."""
    db = _load_users_db()
    if db:
        return
    demo_user = (os.environ.get("RAG_BOOTSTRAP_USER") or "").strip()
    demo_pass = os.environ.get("RAG_BOOTSTRAP_PASSWORD") or ""
    if not demo_user or not demo_pass:
        return
    email = os.environ.get("RAG_BOOTSTRAP_EMAIL") or f"{demo_user}@local.dev"
    salt = "rag_v1"
    db[demo_user.lower()] = {
        "password_hash": _hash_password(demo_pass, salt),
        "salt": salt,
        "display_name": demo_user.title(),
        "email": email,
        "theme": _DEFAULT_THEME,
    }
    _save_users_db(db)


def ensure_demo_user() -> None:
    """Ensure RAG_DEMO_USER exists when set in .env (helps first-time sign-in)."""
    demo_user = (os.environ.get("RAG_DEMO_USER") or "demo").strip().lower()
    demo_pass = os.environ.get("RAG_DEMO_PASSWORD") or "demo123"
    db = _load_users_db()
    if demo_user in db:
        if "email" not in db[demo_user]:
            db[demo_user]["email"] = os.environ.get("RAG_DEMO_EMAIL") or f"{demo_user}@local.dev"
            _save_users_db(db)
        return
    salt = "rag_v1"
    db[demo_user] = {
        "password_hash": _hash_password(demo_pass, salt),
        "salt": salt,
        "display_name": demo_user.title(),
        "email": os.environ.get("RAG_DEMO_EMAIL") or f"{demo_user}@local.dev",
        "theme": _DEFAULT_THEME,
    }
    _save_users_db(db)


def init_auth_store() -> None:
    ensure_bootstrap_user()
    ensure_demo_user()


def register_user(username: str, password: str, email: str) -> None:
    init_auth_store()
    user = (username or "").strip().lower()
    if len(user) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    em = (email or "").strip()
    if not _EMAIL_RE.match(em):
        raise ValueError("Enter a valid email address.")
    db = _load_users_db()
    if user in db:
        raise ValueError("Username already taken.")
    salt = "rag_v1"
    db[user] = {
        "password_hash": _hash_password(password, salt),
        "salt": salt,
        "display_name": user.title(),
        "email": em,
        "theme": _DEFAULT_THEME,
    }
    _save_users_db(db)


def verify_login(username: str, password: str) -> bool:
    init_auth_store()
    user = (username or "").strip().lower()
    if not user or not password:
        return False
    db = _load_users_db()
    rec = db.get(user)
    if not rec:
        return False
    salt = str(rec.get("salt", "rag_v1"))
    expected = str(rec.get("password_hash", ""))
    return _hash_password(password, salt) == expected


def get_profile(username: str) -> UserProfile:
    db = _load_users_db()
    rec = db.get(username) or {}
    return UserProfile(
        username=username,
        display_name=str(rec.get("display_name") or username),
        email=str(rec.get("email") or ""),
        theme=str(rec.get("theme") or _DEFAULT_THEME),
    )


def save_user_theme(username: str, theme: str) -> None:
    db = _load_users_db()
    if username not in db:
        return
    db[username]["theme"] = theme
    _save_users_db(db)


def profile_path(username: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._\-]", "_", username)
    return INDEX_DATA_DIR / "users" / safe


def load_notebook(username: str) -> list[dict]:
    path = profile_path(username) / "notebook.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_notebook(username: str, entries: list[dict]) -> None:
    path = profile_path(username)
    path.mkdir(parents=True, exist_ok=True)
    nb = path / "notebook.json"
    nb.write_text(json.dumps(entries[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
