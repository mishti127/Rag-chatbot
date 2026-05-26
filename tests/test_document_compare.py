"""Document compare unit tests."""

from __future__ import annotations

import pytest

from rag.document_compare import (
    CompareRow,
    CompareSection,
    _align_sections,
    _clip,
    _cosine,
    _fallback_summaries,
    _token_overlap_sim,
)


def test_cosine_identical() -> None:
    v = [1.0, 0.0, 1.0]
    assert _cosine(v, v) == pytest.approx(1.0)


def test_clip_shortens() -> None:
    assert _clip("hello world", 5).endswith("…")


def test_align_sections_similar_and_only() -> None:
    left = [
        CompareSection("a1", "Intro", "Revenue grew in Q1."),
        CompareSection("a2", "Risk", "Market volatility remains."),
    ]
    right = [
        CompareSection("b1", "Introduction", "Revenue increased during Q1."),
        CompareSection("b2", "Outlook", "Future expansion plans."),
    ]
    emb_l = [[1.0, 0.0], [0.0, 1.0]]
    emb_r = [[0.99, 0.01], [0.1, 0.9]]
    rows = _align_sections(left, right, emb_l, emb_r)
    assert len(rows) >= 2
    assert any(r.status in {"similar", "changed", "only_left", "only_right"} for r in rows)


def test_token_overlap_sim() -> None:
    assert _token_overlap_sim("alpha beta gamma", "alpha beta delta") > 0


def test_fallback_summaries() -> None:
    rows = [
        CompareRow("A", "similar", "x", "x", "ok", 0.9),
        CompareRow("B", "only_left", "x", "", "missing", 0.0),
    ]
    out = _fallback_summaries(rows)
    assert out["similarities"]
    assert out["missing_in_b"]
