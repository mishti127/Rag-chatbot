"""Knowledge graph from hierarchical page trees (lightweight, no embeddings)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.config import RAG_GRAPH_MAX_NODES, RAG_GRAPH_MAX_RELATED_EDGES, RAG_GRAPH_RELATED_MIN_SCORE
from rag.hierarchical_summary import ensure_tree_summaries, infer_node_kind
from rag.index_store import load_all_documents
from rag.page_tree import NodeKind, PageNode
from rag.vectorless_retrieval import text_relevance_score

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class GraphNode:
    id: str
    label: str
    title: str
    kind: str
    source: str
    summary: str
    level: int
    parent_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "title": self.title,
            "kind": self.kind,
            "source": self.source,
            "summary": self.summary[:280],
            "level": self.level,
            "parent_id": self.parent_id,
        }


@dataclass
class GraphEdge:
    id: str
    from_id: str
    to_id: str
    edge_type: str
    weight: float
    label: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_id,
            "to": self.to_id,
            "type": self.edge_type,
            "weight": round(self.weight, 3),
            "label": self.label,
        }


@dataclass
class KnowledgeMap:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "sources": self.sources,
            "truncated": self.truncated,
            "stats": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "hierarchy_edges": sum(1 for e in self.edges if e.edge_type == "parent"),
                "related_edges": sum(1 for e in self.edges if e.edge_type == "related"),
            },
        }


def _node_key(source: str, node_id: str) -> str:
    return f"{source}::{node_id}"


def _label(title: str, max_len: int = 36) -> str:
    t = " ".join((title or "").split())
    return t if len(t) <= max_len else t[: max_len - 1].rstrip() + "…"


def _fingerprint(node: PageNode) -> str:
    return f"{node.title} {node.summary}"[:2000]


def _collect_nodes(
    node: PageNode,
    *,
    source: str,
    parent_id: str | None,
    level: int,
    is_doc_root: bool,
    out: list[tuple[PageNode, str, str | None, int, str]],
) -> None:
    kind = node.kind if node.kind != NodeKind.NODE else infer_node_kind(
        node, depth=level, is_document_root=is_doc_root
    )
    nid = _node_key(source, node.node_id)
    out.append((node, source, parent_id, level, kind.value))
    for ch in node.children:
        _collect_nodes(ch, source=source, parent_id=nid, level=level + 1, is_doc_root=False, out=out)


def _sample_nodes(
    entries: list[tuple[PageNode, str, str | None, int, str]],
    cap: int,
) -> list[tuple[PageNode, str, str | None, int, str]]:
    if len(entries) <= cap:
        return entries
    by_level: dict[int, list] = {}
    for e in entries:
        by_level.setdefault(e[3], []).append(e)
    picked: list = []
    for lvl in sorted(by_level.keys()):
        for e in by_level[lvl]:
            if len(picked) >= cap:
                return picked
            picked.append(e)
    return picked[:cap]


def build_knowledge_map(
    user_id: str,
    *,
    source_filter: str | None = None,
) -> KnowledgeMap:
    """Build graph for one document or entire workspace."""
    sources: list[str] = []
    entries: list[tuple[PageNode, str, str | None, int, str]] = []

    if source_filter:
        from rag.index_store import load_document

        rec = load_document(user_id, source_filter)
        if not rec:
            raise ValueError(f"Document {source_filter!r} is not indexed.")
        tree = ensure_tree_summaries(rec.tree)
        sources = [source_filter]
        _collect_nodes(tree, source=source_filter, parent_id=None, level=0, is_doc_root=True, out=entries)
    else:
        docs = load_all_documents(user_id)
        if not docs:
            raise ValueError("No indexed documents.")
        for rec in docs:
            sources.append(rec.source)
            tree = ensure_tree_summaries(rec.tree)
            _collect_nodes(
                tree,
                source=rec.source,
                parent_id=None,
                level=0,
                is_doc_root=True,
                out=entries,
            )

    truncated = len(entries) > RAG_GRAPH_MAX_NODES
    sampled = _sample_nodes(entries, RAG_GRAPH_MAX_NODES)

    nodes: list[GraphNode] = []
    id_set: set[str] = set()
    for node, source, parent_id, level, kind in sampled:
        nid = _node_key(source, node.node_id)
        id_set.add(nid)
        nodes.append(
            GraphNode(
                id=nid,
                label=_label(node.title),
                title=node.title,
                kind=kind,
                source=source,
                summary=node.summary or "",
                level=level,
                parent_id=parent_id if parent_id in id_set else None,
            )
        )

    edges: list[GraphEdge] = []
    edge_i = 0
    for gn in nodes:
        if gn.parent_id and gn.parent_id in id_set:
            edges.append(
                GraphEdge(
                    id=f"e{edge_i}",
                    from_id=gn.parent_id,
                    to_id=gn.id,
                    edge_type="parent",
                    weight=1.0,
                    label="contains",
                )
            )
            edge_i += 1

    # Related topic edges (token overlap on title+summary)
    id_to_page = {_node_key(s, n.node_id): n for n, s, _, _, _ in sampled}

    related_pairs: list[tuple[float, str, str]] = []
    for i, ga in enumerate(nodes):
        na = id_to_page.get(ga.id)
        if not na:
            continue
        for gb in nodes[i + 1 :]:
            if ga.source != gb.source:
                continue
            nb = id_to_page.get(gb.id)
            if not nb:
                continue
            score = text_relevance_score(
                _fingerprint(na),
                title=nb.title,
                text="",
                summary=nb.summary,
            )
            if score >= RAG_GRAPH_RELATED_MIN_SCORE:
                related_pairs.append((score, ga.id, gb.id))

    related_pairs.sort(key=lambda x: x[0], reverse=True)
    for score, a, b in related_pairs[:RAG_GRAPH_MAX_RELATED_EDGES]:
        edges.append(
            GraphEdge(
                id=f"e{edge_i}",
                from_id=a,
                to_id=b,
                edge_type="related",
                weight=score,
                label="related topic",
            )
        )
        edge_i += 1

    return KnowledgeMap(nodes=nodes, edges=edges, sources=sources, truncated=truncated)
