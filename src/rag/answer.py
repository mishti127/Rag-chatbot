from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from openai import AuthenticationError, BadRequestError, OpenAI, PermissionDeniedError

from rag.config import (
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL,
    RAG_ANSWER_MAX_CHARS,
    RAG_ANSWER_MIN_CHARS,
    RAG_TEMPERATURE,
    RAG_TREE_MAX_PAGES,
    get_openrouter_api_key,
    normalize_openrouter_model,
    refresh_env_from_project_dotenv,
)
from rag.guardrails import (
    get_guardrails_pipeline,
    normalize_bullet_lines,
    strip_bracket_citations,
)
from rag.index_store import build_workspace_forest, list_sources
from rag.retrieval_explain import TraversalRecorder, explain_retrieved_pages
from rag.vectorless_retrieval import RetrievedPage, retrieve_pages


class TaskKind(str, Enum):
    ASK = "ask"
    SUMMARIZE = "summarize"


SYSTEM_STRICT = """You are a careful document assistant using ONLY the provided pages from the user's indexed files.
- Do not use outside knowledge.
- If pages do not contain enough information, say clearly: "I do not know" or "Not found in the documents."
- Do not include file names, paths, or bracketed source citations in your reply.
- Be accurate and concise."""

SYSTEM_SUMMARIZE = """You summarize ONLY from the provided document pages.
- Produce a structured summary with short bullets or paragraphs as appropriate.
- Do not invent facts not present in the pages.
- Do not include file names, paths, or bracketed source citations."""

SYSTEM_TOOLS = """You analyze ONLY from the provided document pages.
- Follow the user's requested format (summary, bullets, outline, etc.).
- Do not invent facts not present in the pages.
- Never include file names, paths, or bracketed source citations in your answer."""

SYSTEM_BULLETS = """You extract key facts ONLY from the provided document pages.
- Output a bullet list: one important point per line, each line starting with •.
- Each bullet: at most 2 short sentences (about 25 words). About 6–10 bullets total.
- Do not use markdown, asterisks, or headings — only plain • lines.
- Do not include file names, paths, or bracketed source citations.
- Do not invent facts not present in the pages."""


def _length_rule_suffix() -> str:
    return (
        f"\n\nReply length: never more than {RAG_ANSWER_MAX_CHARS} characters (including spaces). "
        f"When useful, aim for about {RAG_ANSWER_MIN_CHARS}–{RAG_ANSWER_MAX_CHARS} characters; "
        "be dense and avoid filler."
    )


def _system_with_length_rule(system: str) -> str:
    return system + _length_rule_suffix()


def _limit_answer_length(text: str) -> str:
    if len(text) <= RAG_ANSWER_MAX_CHARS:
        return text
    suffix = "…"
    head = RAG_ANSWER_MAX_CHARS - len(suffix)
    if head < 1:
        return suffix[: RAG_ANSWER_MAX_CHARS]
    trimmed = text[:head].rstrip()
    if " " in trimmed:
        sp = trimmed.rfind(" ")
        if sp > RAG_ANSWER_MAX_CHARS // 3:
            trimmed = trimmed[:sp].rstrip()
    out = trimmed + suffix
    if len(out) > RAG_ANSWER_MAX_CHARS:
        return out[: RAG_ANSWER_MAX_CHARS]
    return out


@dataclass(frozen=True)
class RetrievedChunk:
    source: str
    text: str
    chunk_index: int | None
    distance: float | None
    title: str = ""
    path: str = ""


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[str]
    retrieved_chunks: list[RetrievedChunk]
    retrieval_trace: list[str] = ()
    retrieval_explanation: dict | None = None


def build_user_message(question: str, context_blocks: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    for source, body in context_blocks:
        lines.append(f"[{source}]\n{body}")
    ctx = "\n\n---\n\n".join(lines)
    return f"Document pages (strict — use only this text):\n\n{ctx}\n\nQuestion: {question}"


def _pages_to_blocks(pages: list[RetrievedPage]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for p in pages:
        header = f"{p.title} ({p.path})" if p.path else p.title
        blocks.append((p.source, f"{header}\n\n{p.text}"))
    return blocks


def _pages_to_chunks(pages: list[RetrievedPage]) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for i, p in enumerate(pages):
        out.append(
            RetrievedChunk(
                source=p.source,
                text=p.text,
                chunk_index=i,
                distance=None,
                title=p.title,
                path=p.path,
            )
        )
    return out


def _openrouter_client(*, api_key: str) -> OpenAI:
    headers: dict[str, str] = {}
    if OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_APP_TITLE:
        headers["X-OpenRouter-Title"] = OPENROUTER_APP_TITLE
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers=headers or None,
    )


def _complete_chat(
    client: OpenAI,
    *,
    system: str,
    user_content: str,
    model_id: str,
) -> str:
    _tok_budget = int(RAG_ANSWER_MAX_CHARS / 2.5) + 100
    try:
        resp = client.chat.completions.create(
            model=model_id,
            temperature=RAG_TEMPERATURE,
            max_tokens=max(280, min(1200, _tok_budget)),
            messages=[
                {"role": "system", "content": _system_with_length_rule(system)},
                {"role": "user", "content": user_content},
            ],
        )
    except BadRequestError as e:
        err_txt = str(e).lower()
        if "not a valid model" in err_txt or "invalid model" in err_txt:
            raise RuntimeError(
                "OpenRouter rejected the model id. Use a valid id from "
                "https://openrouter.ai/models\n\n"
                f"Model sent: {model_id!r}\nAPI message: {e}"
            ) from e
        raise
    except AuthenticationError as e:
        raise RuntimeError(
            "Invalid or missing OPENROUTER_API_KEY. Update `.env` and try again.\n\n"
            f"Details: {e}"
        ) from e
    except PermissionDeniedError as e:
        raise RuntimeError(f"Access denied (403). Details: {e}") from e
    choice = resp.choices[0].message
    return _limit_answer_length((choice.content or "").strip())


def answer_question(
    question: str,
    *,
    top_k: int,
    model: str | None = None,
    context_mode: str | None = None,  # noqa: ARG001 — always strict
    collection_name: str | None = None,
    hybrid: bool | None = None,  # noqa: ARG001 — legacy
    hybrid_oversample: int | None = None,  # noqa: ARG001
    user_id: str | None = None,
    task: TaskKind | str = TaskKind.ASK,
    source_filter: str | None = None,
    tool_action: str | None = None,
) -> AnswerResult:
    refresh_env_from_project_dotenv()
    uid = (user_id or collection_name or "default").strip() or "default"
    pipeline = get_guardrails_pipeline()
    guard = pipeline.validate_input(question, user_id=uid)
    if not guard.ok:
        raise RuntimeError(guard.user_message())

    api_key = get_openrouter_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy `.env.example` to `.env` and add your key."
        )
    if not list_sources(uid):
        return AnswerResult(
            answer=(
                "No documents are indexed yet. Upload PDF or TXT files in the Documents tab, "
                "or run `rag ingest <folder>` for your user workspace."
            ),
            sources=[],
            retrieved_chunks=[],
        )

    forest = build_workspace_forest(uid)
    if forest is None:
        return AnswerResult(
            answer="Document index is empty.",
            sources=[],
            retrieved_chunks=[],
        )

    if source_filter:
        filt = source_filter.strip()
        forest.children = [c for c in forest.children if c.title == filt or filt in c.title]
        if not forest.children:
            return AnswerResult(
                answer=f"No indexed document matches {filt!r}.",
                sources=[],
                retrieved_chunks=[],
            )

    model_id = normalize_openrouter_model(model) if model else OPENROUTER_MODEL
    client = _openrouter_client(api_key=api_key)

    q = question.strip()
    task_kind = TaskKind(task) if isinstance(task, str) else task
    action = (tool_action or "").strip().lower()
    is_tool = bool(action)
    is_bullets = action == "bullet_points"
    if is_bullets:
        q = q or "List the most important points from the documents."
    elif task_kind == TaskKind.SUMMARIZE:
        q = (
            f"Summarize the indexed document content. Focus: {q}"
            if q
            else "Provide a concise summary of the indexed document content."
        )

    recorder = TraversalRecorder()
    pages, trace = retrieve_pages(
        forest,
        q,
        client=client,
        model_id=model_id,
        max_pages=min(top_k, RAG_TREE_MAX_PAGES),
        temperature=RAG_TEMPERATURE,
        use_llm=True,
        recorder=recorder,
    )
    retrieval_explanation = explain_retrieved_pages(
        q, pages, recorder=recorder, trace=trace
    )

    ret_guard = pipeline.validate_retrieval(q, pages, user_id=uid)
    if not ret_guard.ok:
        return AnswerResult(
            answer=ret_guard.user_message(),
            sources=[],
            retrieved_chunks=[],
            retrieval_trace=trace,
            retrieval_explanation=retrieval_explanation,
        )

    blocks = _pages_to_blocks(pages)
    seen_sources: list[str] = []
    for src, _ in blocks:
        if src and src not in seen_sources:
            seen_sources.append(src)

    if is_bullets:
        system = SYSTEM_BULLETS
    elif is_tool:
        system = SYSTEM_TOOLS
    elif task_kind == TaskKind.SUMMARIZE:
        system = SYSTEM_SUMMARIZE
    else:
        system = SYSTEM_STRICT
    user_msg = build_user_message(q, blocks)
    text = _complete_chat(client, system=system, user_content=user_msg, model_id=model_id)
    text = pipeline.finalize_answer(
        text,
        had_context=True,
        sources=seen_sources,
        preserve_lines=is_bullets or is_tool,
    )
    if is_bullets:
        text = normalize_bullet_lines(text)
    else:
        text = strip_bracket_citations(text)

    resp_guard = pipeline.validate_response(
        q, text, pages, sources=seen_sources, user_id=uid
    )
    if not resp_guard.ok:
        text = resp_guard.user_message()

    return AnswerResult(
        answer=text,
        sources=[] if is_tool else seen_sources,
        retrieved_chunks=_pages_to_chunks(pages),
        retrieval_trace=trace,
        retrieval_explanation=retrieval_explanation,
    )
