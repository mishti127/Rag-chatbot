"""Reasoning-based tree retrieval (vectorless PageIndex-style)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from rag.config import RAG_TREE_MAX_DEPTH, RAG_TREE_MAX_PAGES
from rag.page_tree import PageNode

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RetrievedPage:
    source: str
    node_id: str
    title: str
    text: str
    path: str


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _keyword_score(query: str, node: PageNode) -> float:
    return text_relevance_score(
        query,
        title=node.title,
        text=node.content,
        summary=node.summary,
    )


def text_relevance_score(
    query: str,
    *,
    title: str = "",
    text: str = "",
    summary: str = "",
) -> float:
    """Token-overlap relevance in [0, 1] for retrieval confidence checks."""
    q = _tokenize(query)
    if not q:
        return 0.0
    blob = f"{title} {summary} {text}".lower()
    hits = sum(1 for t in q if t in blob)
    return hits / len(q)


def _collect_branch_nodes(node: PageNode, *, source: str, path: str) -> list[tuple[PageNode, str, str]]:
    """Nodes with children (navigation) or leaves with content."""
    out: list[tuple[PageNode, str, str]] = []
    here = f"{path}/{node.title}" if path else node.title
    if node.is_leaf() and node.content.strip():
        out.append((node, source, here))
    elif node.children:
        out.append((node, source, here))
        for ch in node.children:
            out.extend(_collect_branch_nodes(ch, source=source, path=here))
    return out


def _parse_llm_selection(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _llm_pick_children(
    client: OpenAI,
    *,
    model_id: str,
    query: str,
    parent_title: str,
    children: list[PageNode],
    temperature: float,
) -> tuple[list[str], bool]:
    if not children:
        return [], True
    lines = []
    for ch in children[:40]:
        preview = ch.summary or _summarize_short(ch.title)
        lines.append(f"- id={ch.node_id!r} title={ch.title!r} preview={preview!r}")
    prompt = (
        f"You navigate a document tree to answer a question. Parent section: {parent_title!r}\n"
        f"User question: {query}\n\n"
        "Child nodes:\n" + "\n".join(lines) + "\n\n"
        'Reply with JSON only: {"selected_ids": ["id1"], "sufficient": false}\n'
        "- selected_ids: child node ids worth exploring (1–4 ids).\n"
        "- sufficient: true only if leaf content under these nodes is enough to answer.\n"
        "Pick nodes whose titles/previews match the question. Ignore unrelated branches."
    )
    resp = client.chat.completions.create(
        model=model_id,
        temperature=temperature,
        max_tokens=200,
        messages=[
            {"role": "system", "content": "You output strict JSON for tree navigation. No markdown."},
            {"role": "user", "content": prompt},
        ],
    )
    data = _parse_llm_selection((resp.choices[0].message.content or "").strip())
    ids = data.get("selected_ids") or data.get("selected") or []
    if isinstance(ids, str):
        ids = [ids]
    sufficient = bool(data.get("sufficient", False))
    return [str(i) for i in ids if i], sufficient


def _summarize_short(text: str, n: int = 80) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[: n - 1] + "…"


def retrieve_pages_keyword(
    forest: PageNode,
    query: str,
    *,
    max_pages: int,
    source_label: str = "",
    recorder: Any = None,
) -> list[RetrievedPage]:
    """Fallback: rank all leaves by keyword overlap (no LLM)."""
    leaves: list[tuple[PageNode, str, str]] = []
    for ch in forest.children or [forest]:
        src = ch.title if forest.node_id == "workspace" else source_label or ch.title
        for node, src2, path in _collect_branch_nodes(ch, source=src, path=""):
            if node.is_leaf() and node.content.strip():
                leaves.append((node, src2, path))

    scored = sorted(
        ((n, s, p, _keyword_score(query, n)) for n, s, p in leaves),
        key=lambda x: x[3],
        reverse=True,
    )
    out: list[RetrievedPage] = []
    seen: set[str] = set()
    for node, src, path, kw_sc in scored:
        key = f"{src}:{node.node_id}"
        if key in seen:
            continue
        seen.add(key)
        page = RetrievedPage(
            source=src,
            node_id=node.node_id,
            title=node.title,
            text=node.content,
            path=path,
        )
        if recorder:
            recorder.record_page(
                source=src,
                node_id=node.node_id,
                title=node.title,
                path=path,
                depth=0,
                collection_method="keyword_ranking",
                parent_title="keyword fallback",
                llm_selected=False,
                summary=node.summary,
            )
        out.append(page)
        if len(out) >= max_pages:
            break
    return out


def retrieve_pages(
    forest: PageNode,
    query: str,
    *,
    client: OpenAI | None,
    model_id: str,
    max_pages: int | None = None,
    max_depth: int | None = None,
    temperature: float = 0.1,
    use_llm: bool = True,
    recorder: Any = None,
) -> tuple[list[RetrievedPage], list[str]]:
    """
    Hierarchical tree search: LLM-guided branch selection with keyword fallback.
    Returns (pages, trace_lines).
    """
    cap = max_pages if max_pages is not None else RAG_TREE_MAX_PAGES
    depth_cap = max_depth if max_depth is not None else RAG_TREE_MAX_DEPTH
    trace: list[str] = []
    collected: list[RetrievedPage] = []
    seen: set[str] = set()

    def walk(node: PageNode, source: str, path: str, depth: int) -> bool:
        nonlocal collected
        if len(collected) >= cap:
            return True
        here = f"{path}/{node.title}" if path else node.title
        src = source or node.title

        if node.is_leaf() and node.content.strip():
            key = f"{src}:{node.node_id}"
            if key not in seen:
                seen.add(key)
                collected.append(
                    RetrievedPage(
                        source=src,
                        node_id=node.node_id,
                        title=node.title,
                        text=node.content,
                        path=here,
                    )
                )
                if recorder:
                    recorder.record_page(
                        source=src,
                        node_id=node.node_id,
                        title=node.title,
                        path=here,
                        depth=depth,
                        collection_method="leaf",
                        parent_title=node.title if depth == 0 else path.rsplit("/", 1)[0],
                        llm_selected=False,
                        summary=node.summary,
                    )
                trace.append(f"Leaf: [{node.node_id}] {node.title}")
            return len(collected) >= cap

        if depth >= depth_cap:
            return False

        children = node.children
        if not children:
            return False

        if use_llm and client is not None:
            try:
                picked_ids, sufficient = _llm_pick_children(
                    client,
                    model_id=model_id,
                    query=query,
                    parent_title=node.title,
                    children=children,
                    temperature=temperature,
                )
                child_scores = [(c.node_id, c.title, _keyword_score(query, c)) for c in children]
                trace.append(f"Depth {depth} @ {node.title}: LLM → {picked_ids or 'none'}")
                if recorder:
                    recorder.record_decision(
                        depth=depth,
                        parent_title=node.title,
                        parent_id=node.node_id,
                        method="llm_navigation",
                        selected_ids=picked_ids,
                        sufficient=sufficient,
                        child_scores=child_scores,
                    )
                chosen = [c for c in children if c.node_id in picked_ids]
                if not chosen:
                    chosen = sorted(children, key=lambda c: _keyword_score(query, c), reverse=True)[:2]
                    if recorder:
                        recorder.record_decision(
                            depth=depth,
                            parent_title=node.title,
                            parent_id=node.node_id,
                            method="keyword_fallback_children",
                            selected_ids=[c.node_id for c in chosen],
                            sufficient=False,
                            child_scores=child_scores,
                        )
                for ch in chosen:
                    if walk(ch, src if node.node_id != "workspace" else ch.title, here, depth + 1):
                        return True
                if sufficient and collected:
                    return True
                return False
            except Exception:
                trace.append(f"Depth {depth}: LLM failed, keyword fallback")

        ranked = sorted(children, key=lambda c: _keyword_score(query, c), reverse=True)
        top = ranked[:3]
        if recorder:
            recorder.record_decision(
                depth=depth,
                parent_title=node.title,
                parent_id=node.node_id,
                method="keyword_rank_children",
                selected_ids=[c.node_id for c in top],
                sufficient=False,
                child_scores=[(c.node_id, c.title, _keyword_score(query, c)) for c in children],
            )
        for ch in top:
            if walk(ch, src if node.node_id != "workspace" else ch.title, here, depth + 1):
                return True
        return False

    if not forest.children and forest.content.strip():
        walk(forest, forest.title, "", 0)
    else:
        walk(forest, "", "", 0)

    if not collected:
        collected = retrieve_pages_keyword(forest, query, max_pages=cap, recorder=recorder)
        trace.append("Used keyword leaf ranking (no LLM hits).")

    return collected[:cap], trace
