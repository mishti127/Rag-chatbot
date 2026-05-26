"""Lightweight timeline extraction from document trees."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from rag.config import RAG_TIMELINE_MAX_EVENTS
from rag.hierarchical_summary import ensure_tree_summaries
from rag.index_store import load_all_documents, load_document
from rag.page_tree import PageNode

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_DATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "iso",
        re.compile(r"\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b"),
    ),
    (
        "mdy",
        re.compile(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2}|19\d{2})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "dmy",
        re.compile(
            r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(20\d{2}|19\d{2})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "year",
        re.compile(r"\b(19\d{2}|20\d{2})\b"),
    ),
]

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class TimelineEvent:
    event_id: str
    date_iso: str
    date_display: str
    title: str
    snippet: str
    source: str
    node_id: str
    node_title: str
    path: str
    extraction: str = "regex"

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "date_iso": self.date_iso,
            "date_display": self.date_display,
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "node_id": self.node_id,
            "node_title": self.node_title,
            "path": self.path,
            "extraction": self.extraction,
        }


@dataclass
class TimelineResult:
    events: list[TimelineEvent] = field(default_factory=list)
    sequences: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "events": [e.to_dict() for e in self.events],
            "sequences": self.sequences,
            "sources": self.sources,
            "explanation": self.explanation,
            "stats": {"event_count": len(self.events)},
        }


def _parse_date(match: re.Match[str], pattern_name: str) -> datetime | None:
    try:
        if pattern_name == "iso":
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return datetime(y, m, d)
        if pattern_name == "mdy":
            mon = _MONTHS[match.group(1).lower()[:3]]
            return datetime(int(match.group(3)), mon, int(match.group(2)))
        if pattern_name == "dmy":
            mon = _MONTHS[match.group(2).lower()[:3]]
            return datetime(int(match.group(3)), mon, int(match.group(1)))
        if pattern_name == "year":
            return datetime(int(match.group(1)), 1, 1)
    except (ValueError, KeyError):
        return None
    return None


def _find_dates_in_text(text: str) -> list[tuple[datetime, str, str]]:
    found: list[tuple[datetime, str, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    for pname, pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            span = m.span()
            if span in seen_spans:
                continue
            dt = _parse_date(m, pname)
            if dt:
                seen_spans.add(span)
                found.append((dt, m.group(0), pname))
    return found


def _sentences(text: str) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    parts = _SENTENCE_RE.split(t)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def _event_title(sentence: str, date_display: str) -> str:
    s = sentence.strip()
    s = re.sub(re.escape(date_display), "", s, count=1, flags=re.IGNORECASE).strip()
    s = " ".join(s.split())
    if len(s) > 100:
        s = s[:99].rstrip() + "…"
    return s or f"Event on {date_display}"


def _extract_from_node(
    node: PageNode,
    *,
    source: str,
    path: str,
    events: list[TimelineEvent],
) -> None:
    blob = f"{node.title}\n{node.content}"
    if not blob.strip():
        return
    for sent in _sentences(blob):
        for dt, disp, pname in _find_dates_in_text(sent):
            events.append(
                TimelineEvent(
                    event_id=uuid.uuid4().hex[:12],
                    date_iso=dt.strftime("%Y-%m-%d"),
                    date_display=disp,
                    title=_event_title(sent, disp),
                    snippet=sent[:400],
                    source=source,
                    node_id=node.node_id,
                    node_title=node.title,
                    path=path,
                    extraction=f"regex:{pname}",
                )
            )
            if len(events) >= RAG_TIMELINE_MAX_EVENTS:
                return


def _walk_leaves(
    node: PageNode,
    *,
    source: str,
    path: str,
    events: list[TimelineEvent],
) -> None:
    here = f"{path}/{node.title}" if path else node.title
    if node.is_leaf() and node.content.strip():
        _extract_from_node(node, source=source, path=here, events=events)
        return
    for ch in node.children:
        if len(events) >= RAG_TIMELINE_MAX_EVENTS:
            return
        _walk_leaves(ch, source=source, path=here, events=events)


def build_timeline(
    user_id: str,
    *,
    source_filter: str | None = None,
) -> TimelineResult:
    events: list[TimelineEvent] = []
    sources: list[str] = []

    if source_filter:
        rec = load_document(user_id, source_filter)
        if not rec:
            raise ValueError(f"Document {source_filter!r} is not indexed.")
        tree = ensure_tree_summaries(rec.tree)
        sources = [source_filter]
        _walk_leaves(tree, source=source_filter, path="", events=events)
    else:
        for rec in load_all_documents(user_id):
            if len(events) >= RAG_TIMELINE_MAX_EVENTS:
                break
            sources.append(rec.source)
            tree = ensure_tree_summaries(rec.tree)
            _walk_leaves(tree, source=rec.source, path="", events=events)

    # Dedupe by date+snippet prefix
    seen: set[str] = set()
    unique: list[TimelineEvent] = []
    for ev in events:
        key = f"{ev.date_iso}|{ev.snippet[:80]}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(ev)

    unique.sort(key=lambda e: (e.date_iso, e.source, e.title))
    sequences: list[dict] = []
    by_source: dict[str, list[str]] = {}
    for ev in unique:
        by_source.setdefault(ev.source, []).append(ev.event_id)
    for src, ids in sorted(by_source.items()):
        sequences.append({"source": src, "event_ids": ids, "label": f"Timeline — {src}"})

    explanation = (
        f"Extracted {len(unique)} event(s) using explainable date regex patterns "
        f"(ISO, month-day-year, year). Each event links to a document node/page. "
        f"{'Limited to ' + str(RAG_TIMELINE_MAX_EVENTS) + ' events max.' if len(events) >= RAG_TIMELINE_MAX_EVENTS else ''}"
    )

    return TimelineResult(
        events=unique,
        sequences=sequences,
        sources=sources,
        explanation=explanation.strip(),
    )
