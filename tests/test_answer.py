"""Tests for answer post-processing."""

from rag.answer import _limit_answer_length


def test_limit_answer_length_short_unchanged() -> None:
    s = "hello"
    assert _limit_answer_length(s) == s


def test_limit_answer_length_trims_with_ellipsis(monkeypatch) -> None:
    monkeypatch.setattr("rag.answer.RAG_ANSWER_MAX_CHARS", 10)
    out = _limit_answer_length("abcdefghijklmnop")
    assert len(out) <= 10
    assert out.endswith("…")
