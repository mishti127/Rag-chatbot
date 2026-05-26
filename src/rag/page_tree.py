"""Build hierarchical PageIndex-style trees from documents (no embeddings)."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum

_HEADING_RE = re.compile(
    r"^(?P<level>#{1,6})\s+(?P<title>.+)$|^(?P<uc>[A-Z][A-Z0-9 \-]{4,})$",
    re.MULTILINE,
)
_PAGE_TARGET_CHARS = 2200


class NodeKind(str, Enum):
    DOCUMENT = "document"
    SECTION = "section"
    PAGE = "page"
    NODE = "node"


@dataclass
class PageNode:
    node_id: str
    title: str
    content: str = ""
    summary: str = ""
    kind: NodeKind = NodeKind.NODE
    children: list[PageNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        out: dict = {
            "node_id": self.node_id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "children": [c.to_dict() for c in self.children],
        }
        if self.kind != NodeKind.NODE:
            out["kind"] = self.kind.value
        return out

    @classmethod
    def from_dict(cls, data: dict) -> PageNode:
        raw_kind = data.get("kind")
        kind = NodeKind.NODE
        if raw_kind:
            try:
                kind = NodeKind(str(raw_kind))
            except ValueError:
                kind = NodeKind.NODE
        return cls(
            node_id=str(data.get("node_id", "")),
            title=str(data.get("title", "")),
            content=str(data.get("content", "")),
            summary=str(data.get("summary", "")),
            kind=kind,
            children=[cls.from_dict(c) for c in data.get("children") or []],
        )

    def find_node(self, node_id: str) -> PageNode | None:
        if self.node_id == node_id:
            return self
        for ch in self.children:
            found = ch.find_node(node_id)
            if found:
                return found
        return None

    def walk(self) -> list[PageNode]:
        nodes = [self]
        for ch in self.children:
            nodes.extend(ch.walk())
        return nodes

    def is_leaf(self) -> bool:
        return not self.children

    def iter_leaves(self) -> list[PageNode]:
        if self.is_leaf() and self.content.strip():
            return [self]
        out: list[PageNode] = []
        for ch in self.children:
            out.extend(ch.iter_leaves())
        return out

    def outline_lines(self, depth: int = 0) -> list[str]:
        indent = "  " * depth
        lines = [f"{indent}- [{self.node_id}] {self.title}"]
        for ch in self.children:
            lines.extend(ch.outline_lines(depth + 1))
        return lines


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _summarize(text: str, max_len: int = 160) -> str:
    t = " ".join(text.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _paragraph_pages(body: str, *, prefix: str) -> list[PageNode]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paras:
        return []
    pages: list[PageNode] = []
    buf: list[str] = []
    size = 0
    idx = 0
    for p in paras:
        if size + len(p) > _PAGE_TARGET_CHARS and buf:
            text = "\n\n".join(buf)
            pages.append(
                PageNode(
                    node_id=_new_id(),
                    title=f"{prefix} — part {idx + 1}",
                    content=text,
                    summary=_summarize(text),
                )
            )
            idx += 1
            buf = [p]
            size = len(p)
        else:
            buf.append(p)
            size += len(p)
    if buf:
        text = "\n\n".join(buf)
        pages.append(
            PageNode(
                node_id=_new_id(),
                title=f"{prefix} — part {idx + 1}" if idx else prefix,
                content=text,
                summary=_summarize(text),
            )
        )
    return pages


def _sections_from_headings(text: str) -> list[tuple[int, str, str]] | None:
    matches = list(_HEADING_RE.finditer(text))
    if len(matches) < 2:
        return None
    sections: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        if m.group("level"):
            level = len(m.group("level"))
            title = m.group("title").strip()
        else:
            level = 1
            title = m.group("uc").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((level, title, body))
    return sections


def build_tree_from_text(source: str, text: str) -> PageNode:
    """Build a document tree: root → sections → pages (natural boundaries, not fixed chunks)."""
    text = text.strip()
    root = PageNode(node_id=_new_id(), title=source, summary=f"Document: {source}")

    if not text:
        root.summary = "Empty document"
        return root

    sections = _sections_from_headings(text)
    if sections:
        stack: list[tuple[int, PageNode]] = [(0, root)]
        for level, title, body in sections:
            node = PageNode(node_id=_new_id(), title=title, summary=_summarize(body or title))
            pages = _paragraph_pages(body, prefix=title) if body else []
            if pages:
                node.children = pages
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            parent.children.append(node)
            stack.append((level, node))
        root.summary = f"{source}: {len(root.iter_leaves())} page(s)"
        return root

    pages = _paragraph_pages(text, prefix=source)
    root.children = pages
    root.summary = f"{source}: {len(pages)} page(s)"
    return root


def build_tree_from_pdf_pages(source: str, page_texts: list[str]) -> PageNode:
    """One leaf per PDF page — preserves page boundaries (PageIndex-style)."""
    root = PageNode(node_id=_new_id(), title=source, summary=f"PDF: {source}")
    for i, raw in enumerate(page_texts, start=1):
        body = (raw or "").strip()
        if not body:
            continue
        root.children.append(
            PageNode(
                node_id=_new_id(),
                title=f"Page {i}",
                content=body,
                summary=_summarize(body),
            )
        )
    if not root.children:
        root.summary = "Empty PDF"
    else:
        root.summary = f"{source}: {len(root.children)} PDF page(s)"
    return root


def file_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
