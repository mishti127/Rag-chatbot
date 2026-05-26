"""Timeline extraction tests."""

from __future__ import annotations

from unittest.mock import patch

from rag.hierarchical_summary import enrich_tree_summaries
from rag.index_store import DocumentRecord
from rag.page_tree import PageNode, build_tree_from_text
from rag.timeline_extract import _find_dates_in_text, build_timeline


def test_find_dates_iso_and_year() -> None:
    found = _find_dates_in_text("Signed on 2019-06-15 and renewed in 2021.")
    displays = {d[1] for d in found}
    assert "2019-06-15" in displays
    assert "2021" in displays


def _timeline_record() -> DocumentRecord:
    text = (
        "# Events\n\n"
        "The company was founded in 2018.\n\n"
        "## Growth\n\n"
        "On Jan 15, 2020 we opened the Berlin office. "
        "Revenue milestones followed in 2021."
    )
    tree = build_tree_from_text("events.txt", text)
    enrich_tree_summaries(tree)
    return DocumentRecord(source="events.txt", file_hash="x", tree=tree)


@patch("rag.timeline_extract.load_document")
def test_build_timeline_events(mock_load) -> None:
    mock_load.return_value = _timeline_record()
    result = build_timeline("u1", source_filter="events.txt")
    d = result.to_dict()
    assert d["stats"]["event_count"] >= 2
    years = {e["date_iso"][:4] for e in d["events"]}
    assert "2018" in years or "2020" in years or "2021" in years
    assert all(e["node_id"] for e in d["events"])
    assert "regex" in d["explanation"].lower()


@patch("rag.timeline_extract.load_document")
def test_timeline_leaf_content_only(mock_load) -> None:
    tree = PageNode(
        node_id="root",
        title="Doc",
        children=[
            PageNode(
                node_id="p1",
                title="Page 1",
                content="Launch happened on 2022-03-01 according to records.",
                summary="Launch 2022",
            )
        ],
    )
    mock_load.return_value = DocumentRecord(source="x.txt", file_hash="h", tree=tree)
    d = build_timeline("u1", source_filter="x.txt").to_dict()
    assert any("2022" in e["date_iso"] for e in d["events"])
