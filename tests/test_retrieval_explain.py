"""Retrieval explanation tests."""

from __future__ import annotations

from rag.retrieval_explain import TraversalRecorder, explain_retrieved_pages
from rag.vectorless_retrieval import RetrievedPage, text_relevance_score


def test_text_relevance_score_range() -> None:
    s = text_relevance_score("revenue growth", title="Q1", text="revenue grew", summary="earnings")
    assert 0 <= s <= 1


def test_explain_retrieved_pages() -> None:
    pages = [
        RetrievedPage("a.pdf", "n1", "Revenue", "Q1 revenue grew.", "doc/Revenue"),
    ]
    recorder = TraversalRecorder()
    recorder.record_page(
        source="a.pdf",
        node_id="n1",
        title="Revenue",
        path="doc/Revenue",
        depth=2,
        collection_method="leaf",
        parent_title="Section",
        llm_selected=True,
        summary="Revenue section",
    )
    out = explain_retrieved_pages("revenue Q1", pages, recorder=recorder, trace=["Leaf: n1"])
    assert out["why_answer"]
    assert len(out["pages"]) == 1
    assert "keyword_overlap" in out["pages"][0]["scores"]
    assert out["pages"][0]["scores"]["composite"] > 0
