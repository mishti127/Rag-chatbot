"""Knowledge map graph tests."""

from __future__ import annotations

from unittest.mock import patch

from rag.hierarchical_summary import enrich_tree_summaries
from rag.index_store import DocumentRecord
from rag.knowledge_map import build_knowledge_map
from rag.page_tree import build_tree_from_text


def _sample_record(source: str = "history.txt") -> DocumentRecord:
    text = (
        "# Introduction\n\n"
        "Overview of the project started in 2020.\n\n"
        "## Chapter One\n\n"
        "Revenue grew in Q1 2021. Costs remained stable.\n\n"
        "## Chapter Two\n\n"
        "Expansion continued through 2022 with new markets."
    )
    tree = build_tree_from_text(source, text)
    enrich_tree_summaries(tree)
    return DocumentRecord(source=source, file_hash="abc", tree=tree)


@patch("rag.index_store.load_document")
def test_build_knowledge_map_single_doc(mock_load) -> None:
    rec = _sample_record()
    mock_load.return_value = rec
    km = build_knowledge_map("user1", source_filter="history.txt")
    d = km.to_dict()
    assert d["stats"]["node_count"] >= 2
    assert d["stats"]["hierarchy_edges"] >= 1
    assert any(e["type"] == "parent" for e in d["edges"])
    assert all(n["source"] == "history.txt" for n in d["nodes"])


@patch("rag.knowledge_map.load_all_documents")
def test_build_knowledge_map_all_docs(mock_all) -> None:
    mock_all.return_value = [_sample_record("a.txt"), _sample_record("b.txt")]
    km = build_knowledge_map("user1", source_filter=None)
    sources = {n["source"] for n in km.to_dict()["nodes"]}
    assert "a.txt" in sources
    assert "b.txt" in sources


@patch("rag.index_store.load_document")
def test_knowledge_map_missing_doc(mock_load) -> None:
    mock_load.return_value = None
    try:
        build_knowledge_map("user1", source_filter="missing.pdf")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "not indexed" in str(exc).lower()
