"""Retrieval explanation engine for vectorless tree RAG."""

from __future__ import annotations

from dataclasses import dataclass, field

from rag.vectorless_retrieval import RetrievedPage, text_relevance_score


@dataclass
class TraversalRecorder:
    """Collects parent-child traversal events during retrieve_pages (optional)."""

    decisions: list[dict] = field(default_factory=list)
    page_collects: list[dict] = field(default_factory=list)

    def record_decision(
        self,
        *,
        depth: int,
        parent_title: str,
        parent_id: str,
        method: str,
        selected_ids: list[str],
        sufficient: bool,
        child_scores: list[tuple[str, str, float]],
    ) -> None:
        self.decisions.append(
            {
                "depth": depth,
                "parent_title": parent_title,
                "parent_id": parent_id,
                "method": method,
                "selected_ids": list(selected_ids),
                "sufficient": sufficient,
                "child_scores": [
                    {"node_id": nid, "title": title, "keyword_score": round(sc, 4)}
                    for nid, title, sc in child_scores
                ],
            }
        )

    def record_page(
        self,
        *,
        source: str,
        node_id: str,
        title: str,
        path: str,
        depth: int,
        collection_method: str,
        parent_title: str,
        llm_selected: bool,
        summary: str = "",
    ) -> None:
        self.page_collects.append(
            {
                "source": source,
                "node_id": node_id,
                "title": title,
                "path": path,
                "depth": depth,
                "collection_method": collection_method,
                "parent_title": parent_title,
                "llm_selected": llm_selected,
                "summary": summary[:200],
            }
        )


def _keyword_on_content(query: str, page: RetrievedPage) -> float:
    return text_relevance_score(query, title="", text=page.text, summary="")


def _semantic_on_metadata(query: str, page: RetrievedPage, summary: str = "") -> float:
    return text_relevance_score(query, title=page.title, text="", summary=summary)


def _hierarchy_score(
    *,
    depth: int,
    llm_selected: bool,
    path: str,
    query: str,
) -> float:
    depth_factor = max(0.35, 1.0 - depth * 0.12)
    llm_boost = 0.15 if llm_selected else 0.0
    path_blob = (path or "").lower()
    q_terms = [t for t in query.lower().split() if len(t) > 3]
    path_hits = sum(1 for t in q_terms if t in path_blob) / max(1, len(q_terms))
    return min(1.0, depth_factor + llm_boost + path_hits * 0.25)


def _traversal_narrative(
    page: RetrievedPage,
    collect_meta: dict | None,
    decisions: list[dict],
) -> str:
    parts: list[str] = []
    if collect_meta:
        method = collect_meta.get("collection_method", "tree_walk")
        parent = collect_meta.get("parent_title") or "document root"
        if method == "keyword_fallback":
            parts.append(f"Ranked by keyword overlap after tree walk (parent: {parent}).")
        elif collect_meta.get("llm_selected"):
            parts.append(f"LLM branch navigation selected this path under “{parent}”.")
        else:
            parts.append(f"Reached via hierarchical walk from “{parent}”.")
        parts.append(f"Depth {collect_meta.get('depth', 0)} in the document tree.")
    for d in decisions:
        if page.node_id in d.get("selected_ids", []):
            parts.append(
                f"At depth {d['depth']}, parent “{d['parent_title']}” used "
                f"{d['method']} to include this branch."
            )
            break
    if not parts:
        parts.append("Collected as a relevant leaf during document tree retrieval.")
    return " ".join(parts)


def explain_retrieved_pages(
    query: str,
    pages: list[RetrievedPage],
    *,
    recorder: TraversalRecorder | None,
    trace: list[str],
    summaries: dict[str, str] | None = None,
) -> dict:
    """Build per-page explanations and overall “why this answer” summary."""
    summaries = summaries or {}
    collect_by_id = {}
    if recorder:
        for ev in recorder.page_collects:
            collect_by_id[ev["node_id"]] = ev

    explained: list[dict] = []
    for rank, page in enumerate(pages, start=1):
        meta = collect_by_id.get(page.node_id)
        summary = summaries.get(page.node_id) or (meta or {}).get("summary", "")
        kw = _keyword_on_content(query, page)
        sem = _semantic_on_metadata(query, page, summary=summary)
        hier = _hierarchy_score(
            depth=(meta or {}).get("depth", 1),
            llm_selected=bool((meta or {}).get("llm_selected")),
            path=page.path,
            query=query,
        )
        composite = round(0.45 * kw + 0.35 * sem + 0.20 * hier, 4)
        method = (meta or {}).get("collection_method", "tree_walk")
        explained.append(
            {
                "rank": rank,
                "source": page.source,
                "node_id": page.node_id,
                "title": page.title,
                "path": page.path,
                "scores": {
                    "keyword_overlap": round(kw, 4),
                    "semantic_relevance": round(sem, 4),
                    "hierarchy_relevance": round(hier, 4),
                    "composite": composite,
                },
                "selection_method": method,
                "traversal_logic": _traversal_narrative(
                    page,
                    meta,
                    recorder.decisions if recorder else [],
                ),
            }
        )

    explained.sort(key=lambda x: x["scores"]["composite"], reverse=True)
    for i, row in enumerate(explained, start=1):
        row["rank"] = i

    why = _why_answer_summary(query, explained, trace)
    return {
        "why_answer": why,
        "pages": explained,
        "trace": trace,
        "decisions": recorder.decisions if recorder else [],
        "scoring_weights": {
            "keyword_overlap": 0.45,
            "semantic_relevance": 0.35,
            "hierarchy_relevance": 0.20,
        },
    }


def _why_answer_summary(query: str, pages: list[dict], trace: list[str]) -> str:
    if not pages:
        return "No pages were retrieved — the answer is based only on guardrails or empty context."
    top = pages[0]
    methods = {p.get("selection_method") for p in pages}
    method_txt = ", ".join(sorted(methods)) or "tree walk"
    return (
        f"For your question, the system retrieved {len(pages)} page(s) using vectorless tree navigation "
        f"({method_txt}). The top match is “{top['title']}” with composite score {top['scores']['composite']:.2f} "
        f"(keyword {top['scores']['keyword_overlap']:.2f}, semantic {top['scores']['semantic_relevance']:.2f}, "
        f"hierarchy {top['scores']['hierarchy_relevance']:.2f}). "
        f"The answer was generated only from these retrieved excerpts."
    )
