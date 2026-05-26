"""Tests for PageIndex-style tree building."""

from rag.page_tree import build_tree_from_text


def test_build_tree_from_headings() -> None:
    text = "# Intro\n\nHello world.\n\n## Details\n\nMore text here."
    tree = build_tree_from_text("doc.txt", text)
    leaves = tree.iter_leaves()
    assert len(leaves) >= 1
    combined = " ".join(l.content for l in leaves)
    assert "Hello" in combined or "More" in combined


def test_build_tree_paragraph_fallback() -> None:
    text = "Paragraph one.\n\nParagraph two with extra content."
    tree = build_tree_from_text("plain.txt", text)
    assert tree.iter_leaves()
