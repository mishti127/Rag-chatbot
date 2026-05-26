"""AI notes generator using hierarchical page trees."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openai import OpenAI

from rag.answer import _complete_chat, _openrouter_client
from rag.config import (
    OPENROUTER_MODEL,
    RAG_TOP_K,
    RAG_TREE_MAX_PAGES,
    get_openrouter_api_key,
    normalize_openrouter_model,
)
from rag.hierarchical_summary import ensure_tree_summaries
from rag.index_store import build_workspace_forest, load_document
from rag.page_tree import NodeKind, PageNode
from rag.retrieval_explain import TraversalRecorder
from rag.vectorless_retrieval import retrieve_pages


class NotesScope(str, Enum):
    CHAPTER = "chapter"
    TOPIC = "topic"
    PAGE = "page"


class NotesStyle(str, Enum):
    BULLETS = "bullets"
    EXAM = "exam"
    CONCEPTS = "concepts"
    DEFINITIONS = "definitions"


_STYLE_PROMPTS = {
    NotesStyle.BULLETS: (
        "Produce concise bullet notes (use • lines). Group under the section heading."
    ),
    NotesStyle.EXAM: (
        "Produce exam-style notes: key points, likely questions, and short model answers "
        "where the text supports them. Use clear headings."
    ),
    NotesStyle.CONCEPTS: (
        "List key concepts with one-line explanations. Use a numbered or bulleted list."
    ),
    NotesStyle.DEFINITIONS: (
        "Extract term → definition pairs from the text only. Format: **Term** — definition."
    ),
}


@dataclass(frozen=True)
class NotesSection:
    node_id: str
    title: str
    kind: str
    path: str
    body: str


@dataclass(frozen=True)
class NotesResult:
    source: str
    scope: str
    style: str
    markdown: str
    sections: list[NotesSection]


def _scope_targets(tree: PageNode, scope: NotesScope) -> list[PageNode]:
    ensure_tree_summaries(tree)
    if scope == NotesScope.PAGE:
        return tree.iter_leaves()
    if scope == NotesScope.CHAPTER:
        out: list[PageNode] = []
        for n in tree.walk():
            if n.node_id == tree.node_id:
                continue
            if n.children and any(c.is_leaf() for c in n.children):
                out.append(n)
            elif n.kind == NodeKind.SECTION:
                out.append(n)
        if not out and tree.children:
            return list(tree.children)
        return out or [tree]
    # topic: sections + top-level children with summaries
    topics: list[PageNode] = []
    for n in tree.walk():
        if n.node_id == tree.node_id:
            continue
        if n.children and (n.summary or n.title):
            topics.append(n)
    return topics[:24] or [tree]


def _gather_section_text(
    node: PageNode,
    *,
    focus: str,
    client: OpenAI,
    model_id: str,
    forest: PageNode | None,
) -> str:
    leaves = node.iter_leaves() if not node.is_leaf() else [node]
    if not leaves:
        return node.summary or node.content or node.title
    if focus.strip() and forest is not None:
        recorder = TraversalRecorder()
        pages, _ = retrieve_pages(
            forest,
            focus,
            client=client,
            model_id=model_id,
            max_pages=min(RAG_TOP_K, RAG_TREE_MAX_PAGES),
            use_llm=True,
            recorder=recorder,
        )
        leaf_ids = {n.node_id for n in leaves}
        picked = [p for p in pages if p.node_id in leaf_ids]
        if picked:
            return "\n\n".join(f"### {p.title}\n{p.text[:3500]}" for p in picked)
    parts: list[str] = []
    for leaf in leaves[:12]:
        blob = leaf.content[:4000] if leaf.content else leaf.summary
        if blob:
            parts.append(f"### {leaf.title}\n{blob}")
    return "\n\n".join(parts) or node.summary or node.title


def generate_notes(
    user_id: str,
    source: str,
    *,
    scope: str = "chapter",
    style: str = "bullets",
    focus: str = "",
) -> NotesResult:
    rec = load_document(user_id, source)
    if not rec:
        raise ValueError(f"Document {source!r} is not indexed.")
    api_key = get_openrouter_api_key()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set.")
    try:
        scope_enum = NotesScope(scope)
    except ValueError:
        scope_enum = NotesScope.CHAPTER
    try:
        style_enum = NotesStyle(style)
    except ValueError:
        style_enum = NotesStyle.BULLETS

    tree = ensure_tree_summaries(rec.tree)
    forest = build_workspace_forest(user_id)
    client = _openrouter_client(api_key=api_key)
    model_id = normalize_openrouter_model(OPENROUTER_MODEL)
    targets = _scope_targets(tree, scope_enum)

    md_parts = [f"# Notes: {source}", f"*Scope: {scope_enum.value} · Style: {style_enum.value}*\n"]
    sections_out: list[NotesSection] = []

    for target in targets[:16]:
        context = _gather_section_text(
            target,
            focus=focus,
            client=client,
            model_id=model_id,
            forest=forest,
        )
        if len(context.strip()) < 30:
            continue
        prompt = (
            f"Document section: {target.title}\n"
            f"Instruction: {_STYLE_PROMPTS[style_enum]}\n"
            f"Use ONLY the text below. Do not invent facts.\n\n"
            f"{context[:14000]}"
        )
        system = (
            "You are an academic note-taking assistant. Output markdown only. "
            "Preserve hierarchy with headings. No file paths or bracket citations."
        )
        body = _complete_chat(client, system=system, user_content=prompt, model_id=model_id)
        heading = f"## {target.title}"
        md_parts.append(f"{heading}\n\n{body}\n")
        sections_out.append(
            NotesSection(
                node_id=target.node_id,
                title=target.title,
                kind=target.kind.value if target.kind != NodeKind.NODE else scope_enum.value,
                path=target.title,
                body=body,
            )
        )

    if len(md_parts) <= 2:
        raise ValueError("Could not generate notes — no content sections matched this scope.")

    return NotesResult(
        source=source,
        scope=scope_enum.value,
        style=style_enum.value,
        markdown="\n".join(md_parts),
        sections=sections_out,
    )
