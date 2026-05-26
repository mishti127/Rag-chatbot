"""Hierarchical summary tests."""

from __future__ import annotations

from rag.hierarchical_summary import (
    enrich_tree_summaries,
    extractive_summary,
    needs_summary_enrichment,
    outline_dict,
    rollup_summary,
)
from rag.page_tree import NodeKind, PageNode, build_tree_from_pdf_pages, build_tree_from_text


def test_extractive_summary_nonempty() -> None:
    text = "Revenue grew twelve percent in Q1. Costs remained flat. Margins improved."
    s = extractive_summary(text, title="Q1")
    assert len(s) > 20
    assert "Revenue" in s or "Q1" in s or "twelve" in s


def test_enrich_tree_txt_headings() -> None:
    text = "# Intro\n\nHello world paragraph.\n\n## Details\n\nMore content in section two."
    tree = build_tree_from_text("doc.txt", text)
    enrich_tree_summaries(tree)
    assert tree.summary
    assert tree.children
    kinds = {n.kind for n in tree.walk()}
    assert NodeKind.DOCUMENT in kinds or tree.kind == NodeKind.DOCUMENT
    leaves = tree.iter_leaves()
    assert all(leaf.summary for leaf in leaves)


def test_pdf_section_grouping_large() -> None:
    pages = [f"Content of page {i} with unique keyword{i}." for i in range(1, 25)]
    tree = build_tree_from_pdf_pages("big.pdf", pages)
    enrich_tree_summaries(tree)
    # Should create section nodes between document and pages
    assert any(c.kind == NodeKind.SECTION for c in tree.children)
    assert tree.summary


def test_outline_dict_shape() -> None:
    tree = build_tree_from_text("a.txt", "Line one.\n\nLine two.")
    enrich_tree_summaries(tree)
    out = outline_dict(tree)
    assert out["node_id"]
    assert out["kind"] == "document"
    assert "children" in out


def test_rollup_summary() -> None:
    s = rollup_summary("Section A", ["Point one.", "Point two."], NodeKind.SECTION)
    assert "Section" in s or "Section A" in s


def test_needs_enrichment_legacy_short_summary() -> None:
    tree = PageNode(
        node_id="1",
        title="doc",
        children=[
            PageNode(
                node_id="2",
                title="Page 1",
                content="A" * 500,
                summary="short",
            )
        ],
    )
    assert needs_summary_enrichment(tree)
