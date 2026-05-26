"""Semantic document comparison (embeddings + LLM) for two PDF/TXT sources."""

from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI

from rag.answer import _openrouter_client
from rag.config import (
    OPENROUTER_EMBED_MODEL,
    OPENROUTER_MODEL,
    RAG_COMPARE_EMBED_BATCH,
    RAG_COMPARE_MAX_SECTIONS,
    RAG_COMPARE_SECTION_CHARS,
    RAG_COMPARE_SIM_CHANGED,
    RAG_COMPARE_SIM_MATCH,
    RAG_TEMPERATURE,
    get_openrouter_api_key,
    normalize_openrouter_model,
)
from rag.index_store import load_document
from rag.ingest import _read_pdf, _read_txt
from rag.page_tree import PageNode, build_tree_from_pdf_pages, build_tree_from_text

@dataclass
class CompareSection:
    section_id: str
    title: str
    text: str


@dataclass
class CompareRow:
    title: str
    status: str
    left_text: str
    right_text: str
    semantic_note: str
    similarity: float = 0.0


@dataclass
class CompareResult:
    doc_a: str
    doc_b: str
    similarities: list[str] = field(default_factory=list)
    differences: list[str] = field(default_factory=list)
    missing_in_b: list[str] = field(default_factory=list)
    missing_in_a: list[str] = field(default_factory=list)
    changed_sections: list[str] = field(default_factory=list)
    rows: list[CompareRow] = field(default_factory=list)
    report_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_a": self.doc_a,
            "doc_b": self.doc_b,
            "similarities": self.similarities,
            "differences": self.differences,
            "missing_in_b": self.missing_in_b,
            "missing_in_a": self.missing_in_a,
            "changed_sections": self.changed_sections,
            "rows": [
                {
                    "title": r.title,
                    "status": r.status,
                    "left_text": r.left_text,
                    "right_text": r.right_text,
                    "semantic_note": r.semantic_note,
                    "similarity": round(r.similarity, 3),
                }
                for r in self.rows
            ],
            "report_markdown": self.report_markdown,
        }


def tree_from_bytes(filename: str, data: bytes) -> PageNode:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise ValueError("Only PDF and TXT files are supported for comparison.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = Path(tmp.name)
    try:
        if suffix == ".txt":
            raw = _read_txt(path)
            return build_tree_from_text(filename, raw)
        raw, pages = _read_pdf(path)
        return build_tree_from_pdf_pages(filename, pages)
    finally:
        path.unlink(missing_ok=True)


def load_tree_for_source(user_id: str, source: str, *, upload: bytes | None = None) -> PageNode:
    if upload is not None:
        return tree_from_bytes(source, upload)
    rec = load_document(user_id, source)
    if not rec:
        raise ValueError(f"Document {source!r} is not indexed.")
    return rec.tree


def _sample_sections(tree: PageNode, label: str) -> list[CompareSection]:
    leaves = tree.iter_leaves()
    if not leaves:
        body = (tree.content or tree.title or "").strip()
        if body:
            leaves = [
                PageNode(
                    node_id="root",
                    title=tree.title or label,
                    content=body[:RAG_COMPARE_SECTION_CHARS],
                )
            ]
    if len(leaves) > RAG_COMPARE_MAX_SECTIONS:
        step = max(1, len(leaves) // RAG_COMPARE_MAX_SECTIONS)
        leaves = leaves[::step][:RAG_COMPARE_MAX_SECTIONS]
    sections: list[CompareSection] = []
    for i, leaf in enumerate(leaves):
        text = (leaf.content or "").strip()
        if not text:
            continue
        title = leaf.title or f"Section {i + 1}"
        sections.append(
            CompareSection(
                section_id=leaf.node_id or f"{label}-{i}",
                title=title[:200],
                text=text[:RAG_COMPARE_SECTION_CHARS],
            )
        )
    return sections


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    return dot / (na * nb)


def _token_overlap_sim(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]{4,}", (a or "").lower()))
    tb = set(re.findall(r"[a-z0-9]{4,}", (b or "").lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = OPENROUTER_EMBED_MODEL
    out: list[list[float]] = []
    batch = max(1, RAG_COMPARE_EMBED_BATCH)
    for i in range(0, len(texts), batch):
        chunk = [t[:6000] if t else " " for t in texts[i : i + batch]]
        try:
            resp = client.embeddings.create(model=model, input=chunk)
            out.extend([list(d.embedding) for d in resp.data])
        except Exception:
            out.extend([[] for _ in chunk])
    return out


def _align_sections(
    left: list[CompareSection],
    right: list[CompareSection],
    emb_left: list[list[float]],
    emb_right: list[list[float]],
) -> list[CompareRow]:
    used_right: set[int] = set()
    rows: list[CompareRow] = []

    for i, sec_a in enumerate(left):
        best_j = -1
        best_sim = -1.0
        for j, sec_b in enumerate(right):
            if j in used_right:
                continue
            sim = 0.0
            if i < len(emb_left) and j < len(emb_right) and emb_left[i] and emb_right[j]:
                sim = _cosine(emb_left[i], emb_right[j])
            else:
                sim = _token_overlap_sim(sec_a.text, sec_b.text)
            if sim > best_sim:
                best_sim = sim
                best_j = j

        if best_j >= 0 and best_sim >= RAG_COMPARE_SIM_CHANGED:
            used_right.add(best_j)
            sec_b = right[best_j]
            if best_sim >= RAG_COMPARE_SIM_MATCH:
                status = "similar"
                note = "Semantically aligned content."
            else:
                status = "changed"
                note = "Same topic area with meaningful wording or detail changes."
            rows.append(
                CompareRow(
                    title=sec_a.title if len(sec_a.title) >= len(sec_b.title) else sec_b.title,
                    status=status,
                    left_text=_clip(sec_a.text, 900),
                    right_text=_clip(sec_b.text, 900),
                    semantic_note=note,
                    similarity=best_sim,
                )
            )
        else:
            rows.append(
                CompareRow(
                    title=sec_a.title,
                    status="only_left",
                    left_text=_clip(sec_a.text, 900),
                    right_text="",
                    semantic_note="Present only in document A.",
                    similarity=0.0,
                )
            )

    for j, sec_b in enumerate(right):
        if j in used_right:
            continue
        rows.append(
            CompareRow(
                title=sec_b.title,
                status="only_right",
                left_text="",
                right_text=_clip(sec_b.text, 900),
                semantic_note="Present only in document B.",
                similarity=0.0,
            )
        )
    return rows


def _clip(text: str, n: int) -> str:
    t = " ".join((text or "").split())
    if len(t) <= n:
        return t
    return t[: n - 1].rstrip() + "…"


def _build_report(result: CompareResult) -> str:
    lines = [
        f"# Document comparison: {result.doc_a} vs {result.doc_b}",
        "",
        "## Key similarities",
    ]
    lines.extend([f"- {s}" for s in result.similarities] or ["- (none detected)"])
    lines += ["", "## Key differences"]
    lines.extend([f"- {d}" for d in result.differences] or ["- (none detected)"])
    lines += ["", f"## Topics in {result.doc_a} missing from {result.doc_b}"]
    lines.extend([f"- {m}" for m in result.missing_in_b] or ["- (none)"])
    lines += ["", f"## Topics in {result.doc_b} missing from {result.doc_a}"]
    lines.extend([f"- {m}" for m in result.missing_in_a] or ["- (none)"])
    lines += ["", "## Changed sections"]
    lines.extend([f"- {c}" for c in result.changed_sections] or ["- (none)"])
    lines += ["", "## Side-by-side sections", ""]
    for row in result.rows:
        lines.append(f"### {row.title} ({row.status})")
        if row.semantic_note:
            lines.append(f"_{row.semantic_note}_")
        lines.append(f"\n**{result.doc_a}**\n{row.left_text or '—'}\n")
        lines.append(f"\n**{result.doc_b}**\n{row.right_text or '—'}\n")
    return "\n".join(lines)


def _llm_summarize(
    client: OpenAI,
    *,
    doc_a: str,
    doc_b: str,
    rows: list[CompareRow],
    outline_a: str,
    outline_b: str,
) -> dict[str, list[str]]:
    pair_lines = []
    for r in rows[:24]:
        pair_lines.append(
            f"- [{r.status}] {r.title}: A={_clip(r.left_text, 200)} | B={_clip(r.right_text, 200)}"
        )
    prompt = f"""Compare two documents using semantic alignment (not exact string match).

Document A: {doc_a}
Outline A:
{outline_a[:3500]}

Document B: {doc_b}
Outline B:
{outline_b[:3500]}

Aligned section pairs (embedding-based):
{chr(10).join(pair_lines)[:6000]}

Return ONLY valid JSON with keys:
- similarities (array of short strings, max 8)
- differences (array of short strings, max 8)
- missing_in_b (topics in A not in B, max 8)
- missing_in_a (topics in B not in A, max 8)
- changed_sections (sections with meaningful changes, max 8)

Do not include file paths or bracketed citations."""

    model = normalize_openrouter_model(OPENROUTER_MODEL)
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=min(0.3, RAG_TEMPERATURE),
            max_tokens=1200,
            messages=[
                {
                    "role": "system",
                    "content": "You compare documents. Output strict JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if isinstance(data, dict):
            return {
                "similarities": [str(x) for x in data.get("similarities") or []][:8],
                "differences": [str(x) for x in data.get("differences") or []][:8],
                "missing_in_b": [str(x) for x in data.get("missing_in_b") or []][:8],
                "missing_in_a": [str(x) for x in data.get("missing_in_a") or []][:8],
                "changed_sections": [str(x) for x in data.get("changed_sections") or []][:8],
            }
    except Exception:
        pass
    return {
        "similarities": [],
        "differences": [],
        "missing_in_b": [],
        "missing_in_a": [],
        "changed_sections": [],
    }


def _fallback_summaries(rows: list[CompareRow]) -> dict[str, list[str]]:
    sim = [r.title for r in rows if r.status == "similar"][:8]
    diff = [r.title for r in rows if r.status == "changed"][:8]
    only_l = [r.title for r in rows if r.status == "only_left"][:8]
    only_r = [r.title for r in rows if r.status == "only_right"][:8]
    changed = [f"{r.title}: content revised" for r in rows if r.status == "changed"][:8]
    return {
        "similarities": sim or ["Overall structure partially overlaps."],
        "differences": diff or only_l[:4] + only_r[:4] or ["Documents diverge in several sections."],
        "missing_in_b": only_l,
        "missing_in_a": only_r,
        "changed_sections": changed,
    }


def compare_documents(
    user_id: str,
    *,
    name_a: str,
    name_b: str,
    data_a: bytes | None = None,
    data_b: bytes | None = None,
) -> CompareResult:
    api_key = get_openrouter_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    tree_a = load_tree_for_source(user_id, name_a, upload=data_a)
    tree_b = load_tree_for_source(user_id, name_b, upload=data_b)

    sections_a = _sample_sections(tree_a, name_a)
    sections_b = _sample_sections(tree_b, name_b)
    if not sections_a or not sections_b:
        raise ValueError("Could not extract readable sections from one or both documents.")

    client = _openrouter_client(api_key=api_key)
    texts_a = [s.text for s in sections_a]
    texts_b = [s.text for s in sections_b]
    emb_a = _embed_texts(client, texts_a)
    emb_b = _embed_texts(client, texts_b)

    rows = _align_sections(sections_a, sections_b, emb_a, emb_b)

    outline_a = "\n".join(tree_a.outline_lines()[:40])
    outline_b = "\n".join(tree_b.outline_lines()[:40])
    summary = _llm_summarize(
        client,
        doc_a=name_a,
        doc_b=name_b,
        rows=rows,
        outline_a=outline_a,
        outline_b=outline_b,
    )
    if not any(summary.values()):
        summary = _fallback_summaries(rows)

    result = CompareResult(
        doc_a=name_a,
        doc_b=name_b,
        similarities=summary["similarities"],
        differences=summary["differences"],
        missing_in_b=summary["missing_in_b"],
        missing_in_a=summary["missing_in_a"],
        changed_sections=summary["changed_sections"],
        rows=rows,
    )
    result.report_markdown = _build_report(result)
    return result
