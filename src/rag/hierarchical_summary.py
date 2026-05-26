"""Hierarchical extractive summaries for PageIndex trees (ingestion-time)."""

from __future__ import annotations

import re
from typing import Literal

from rag.config import (
    RAG_SUMMARY_MAX_CHARS,
    RAG_SUMMARY_MAX_SOURCE_CHARS,
    RAG_SUMMARY_SECTION_PAGES,
)
from rag.page_tree import NodeKind, PageNode, _new_id

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_PAGE_TITLE_RE = re.compile(r"^Page\s+\d+", re.IGNORECASE)
_PART_TITLE_RE = re.compile(r"\s+—\s+part\s+\d+", re.IGNORECASE)
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_STOP = frozenset(
    "a an the and or but if is are was were be been being to of in on at for with by from as it this that".split()
)


def _sentences(text: str) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    parts = _SENTENCE_RE.split(t)
    return [p.strip() for p in parts if len(p.strip()) > 12]


def extractive_summary(
    text: str,
    *,
    title: str = "",
    max_chars: int | None = None,
    max_source_chars: int | None = None,
) -> str:
    """Fast extractive summary — optimized for large documents (no LLM)."""
    cap = max_chars if max_chars is not None else RAG_SUMMARY_MAX_CHARS
    src_cap = max_source_chars if max_source_chars is not None else RAG_SUMMARY_MAX_SOURCE_CHARS
    body = (text or "").strip()
    if not body:
        return (title or "Empty section").strip()[:cap]
    if len(body) <= cap:
        return body
    body = body[:src_cap]
    sents = _sentences(body)
    if not sents:
        return _truncate(body, cap)
    if len(sents) == 1:
        return _truncate(sents[0], cap)

    freq: dict[str, int] = {}
    for s in sents:
        for w in _WORD_RE.findall(s.lower()):
            if w not in _STOP and len(w) > 2:
                freq[w] = freq.get(w, 0) + 1

    def score(sentence: str, idx: int) -> float:
        words = [w for w in _WORD_RE.findall(sentence.lower()) if w not in _STOP]
        if not words:
            return 0.0
        tf = sum(freq.get(w, 0) for w in words) / len(words)
        lead = 1.0 if idx < 2 else 0.0
        return tf + lead

    ranked = sorted(enumerate(sents), key=lambda x: score(x[1], x[0]), reverse=True)
    chosen: list[str] = []
    size = 0
    used: set[int] = set()
    # Always prefer opening sentence for context
    if sents:
        chosen.append(sents[0])
        used.add(0)
        size = len(sents[0])
    for idx, sent in ranked:
        if idx in used:
            continue
        if size + len(sent) + 1 > cap:
            continue
        chosen.append(sent)
        used.add(idx)
        size += len(sent) + 1
        if size >= cap * 0.85:
            break
    if not chosen:
        return _truncate(sents[0], cap)
    out = " ".join(chosen)
    return _truncate(out, cap)


def _truncate(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


def infer_node_kind(
    node: PageNode,
    *,
    depth: int,
    is_document_root: bool,
) -> NodeKind:
    if is_document_root:
        return NodeKind.DOCUMENT
    if node.is_leaf():
        if _PAGE_TITLE_RE.match(node.title.strip()) or _PART_TITLE_RE.search(node.title):
            return NodeKind.PAGE
        if node.content.strip():
            return NodeKind.PAGE
        return NodeKind.NODE
    if node.children and all(c.is_leaf() for c in node.children):
        return NodeKind.SECTION
    if node.children:
        return NodeKind.SECTION
    return NodeKind.NODE


def rollup_summary(title: str, child_summaries: list[str], kind: NodeKind) -> str:
    parts = [s.strip() for s in child_summaries if s and s.strip()]
    if not parts:
        return _truncate(title, RAG_SUMMARY_MAX_CHARS)
    if len(parts) == 1:
        head = _truncate(parts[0], RAG_SUMMARY_MAX_CHARS - len(title) - 4)
        return f"{title}: {head}" if title else head

    prefix = {
        NodeKind.DOCUMENT: "Document overview",
        NodeKind.SECTION: "Section",
        NodeKind.PAGE: "Pages",
        NodeKind.NODE: "Summary",
    }.get(kind, "Summary")

    joined = " · ".join(_truncate(p, 120) for p in parts[:6])
    if len(parts) > 6:
        joined += f" · (+{len(parts) - 6} more)"
    text = f"{prefix} — {title}: {joined}" if title else f"{prefix}: {joined}"
    return _truncate(text, RAG_SUMMARY_MAX_CHARS)


def _maybe_section_group_pdf(root: PageNode) -> None:
    """For large flat PDFs, insert section nodes (page groups) under the document root."""
    if not root.children:
        return
    if not all(ch.is_leaf() and _PAGE_TITLE_RE.match(ch.title.strip()) for ch in root.children):
        return
    n = len(root.children)
    chunk = max(4, RAG_SUMMARY_SECTION_PAGES)
    if n < chunk * 2:
        return
    pages = list(root.children)
    root.children = []
    for i in range(0, n, chunk):
        group = pages[i : i + chunk]
        start = i + 1
        end = i + len(group)
        section = PageNode(
            node_id=_new_id(),
            title=f"Pages {start}–{end}",
            kind=NodeKind.SECTION,
            children=group,
        )
        root.children.append(section)


def enrich_tree_summaries(root: PageNode) -> None:
    """Bottom-up summaries at page → section → document levels."""
    _maybe_section_group_pdf(root)

    def visit(node: PageNode, depth: int, *, is_document_root: bool) -> None:
        for ch in node.children:
            visit(ch, depth + 1, is_document_root=False)

        kind = node.kind if node.kind != NodeKind.NODE else infer_node_kind(
            node, depth=depth, is_document_root=is_document_root
        )
        node.kind = kind

        if node.is_leaf() and node.content.strip():
            node.summary = extractive_summary(node.content, title=node.title)
        elif node.children:
            child_summaries = [c.summary for c in node.children if c.summary]
            if not child_summaries:
                blob = " ".join(c.content for c in node.children if c.content)[: RAG_SUMMARY_MAX_SOURCE_CHARS]
                node.summary = extractive_summary(blob or node.title, title=node.title)
            else:
                node.summary = rollup_summary(node.title, child_summaries, kind)
        elif not node.summary.strip():
            node.summary = _truncate(node.title, RAG_SUMMARY_MAX_CHARS)

    visit(root, 0, is_document_root=True)


def needs_summary_enrichment(root: PageNode) -> bool:
    """True when stored tree lacks rollup summaries (legacy indexes)."""
    leaves = root.iter_leaves()
    if not leaves:
        return bool(not root.summary.strip())
    for leaf in leaves[:3]:
        if leaf.content.strip() and len(leaf.summary.strip()) < 40:
            return True
    if root.children and len(root.summary.strip()) < 25:
        return True
    return False


def ensure_tree_summaries(root: PageNode) -> PageNode:
    if needs_summary_enrichment(root):
        enrich_tree_summaries(root)
    return root


def outline_dict(node: PageNode, *, depth: int = 0, is_document_root: bool = True) -> dict:
    kind = node.kind if node.kind != NodeKind.NODE else infer_node_kind(
        node, depth=depth, is_document_root=is_document_root
    )
    return {
        "node_id": node.node_id,
        "title": node.title,
        "summary": node.summary,
        "kind": kind.value,
        "has_content": bool((node.content or "").strip()),
        "children": [
            outline_dict(ch, depth=depth + 1, is_document_root=False) for ch in node.children
        ],
    }
