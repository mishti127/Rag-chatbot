"""Persist PageIndex-style trees per user workspace (JSON, no vector DB)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from rag.config import INDEX_DATA_DIR
from rag.page_tree import PageNode, file_content_hash

_SAFE = re.compile(r"[^a-zA-Z0-9._\-]+")


def _safe_name(source: str) -> str:
    base = source.replace("\\", "/").strip("/")
    slug = _SAFE.sub("_", base)
    return slug[:120] or "document"


def user_workspace(user_id: str) -> Path:
    root = INDEX_DATA_DIR / "users" / _SAFE.sub("_", user_id.strip() or "default")
    (root / "documents").mkdir(parents=True, exist_ok=True)
    (root / "index").mkdir(parents=True, exist_ok=True)
    return root


def index_path(user_id: str, source: str) -> Path:
    return user_workspace(user_id) / "index" / f"{_safe_name(source)}.json"


@dataclass(frozen=True)
class DocumentRecord:
    source: str
    file_hash: str
    tree: PageNode

    def to_json(self) -> dict:
        return {
            "source": self.source,
            "file_hash": self.file_hash,
            "tree": self.tree.to_dict(),
        }

    @classmethod
    def from_json(cls, data: dict) -> DocumentRecord:
        return cls(
            source=str(data.get("source", "")),
            file_hash=str(data.get("file_hash", "")),
            tree=PageNode.from_dict(data.get("tree") or {}),
        )


def save_document(user_id: str, source: str, tree: PageNode, *, file_hash: str) -> None:
    path = index_path(user_id, source)
    rec = DocumentRecord(source=source, file_hash=file_hash, tree=tree)
    path.write_text(json.dumps(rec.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_document(user_id: str, source: str) -> DocumentRecord | None:
    path = index_path(user_id, source)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return DocumentRecord.from_json(data)


def list_sources(user_id: str) -> list[str]:
    idx = user_workspace(user_id) / "index"
    if not idx.is_dir():
        return []
    out: list[str] = []
    for p in sorted(idx.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            src = str(data.get("source", ""))
            if src:
                out.append(src)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(out)


def load_all_documents(user_id: str) -> list[DocumentRecord]:
    return [rec for s in list_sources(user_id) if (rec := load_document(user_id, s))]


def delete_document(user_id: str, source: str) -> bool:
    path = index_path(user_id, source)
    if path.is_file():
        path.unlink()
        return True
    return False


def clear_user_index(user_id: str) -> int:
    idx = user_workspace(user_id) / "index"
    n = 0
    if idx.is_dir():
        for p in idx.glob("*.json"):
            p.unlink()
            n += 1
    return n


def build_workspace_forest(user_id: str) -> PageNode | None:
    docs = load_all_documents(user_id)
    if not docs:
        return None
    root = PageNode(
        node_id="workspace",
        title="All documents",
        summary=f"{len(docs)} indexed document(s)",
    )
    for rec in docs:
        doc_root = rec.tree
        root.children.append(doc_root)
    return root


def hash_text(text: str) -> str:
    return file_content_hash(text)
