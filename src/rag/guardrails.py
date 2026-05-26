"""Enterprise guardrails for strict document-only vectorless RAG."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from rag.config import (
    INDEX_DATA_DIR,
    RAG_GUARDRAIL_BLOCK_INJECTION,
    RAG_GUARDRAIL_BLOCK_JAILBREAK,
    RAG_GUARDRAIL_LOG_BLOCKS,
    RAG_GUARDRAIL_LOG_PATH,
    RAG_GUARDRAILS_ENABLED,
    RAG_MAX_QUERY_CHARS,
    RAG_RESPONSE_MIN_CONTEXT_OVERLAP,
    RAG_RETRIEVAL_MIN_PAGES,
    RAG_RETRIEVAL_MIN_SCORE,
)
from rag.vectorless_retrieval import RetrievedPage, text_relevance_score

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class ValidationStage(str, Enum):
    INPUT = "input"
    RETRIEVAL = "retrieval"
    RESPONSE = "response"


class BlockReason(str, Enum):
    EMPTY_QUERY = "empty_query"
    QUERY_TOO_LONG = "query_too_long"
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    NO_DOCUMENTS = "no_documents"
    LOW_RETRIEVAL_CONFIDENCE = "low_retrieval_confidence"
    UNGROUNDED_RESPONSE = "ungrounded_response"
    LOW_CONTEXT_OVERLAP = "low_context_overlap"
    UNSAFE_RESPONSE = "unsafe_response"


SAFE_REFUSAL = (
    "I can only answer from your uploaded documents. "
    "That information is not supported by the retrieved pages."
)

SAFE_NO_CONTEXT = (
    "No relevant document pages were found. Upload or index documents, then ask again."
)

SAFE_BLOCKED_INPUT = (
    "Your message was blocked by safety rules. "
    "Ask a direct question about your uploaded documents without override instructions."
)


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    message: str = ""
    stage: ValidationStage | None = None
    code: str = ""
    safe_response: str = ""

    def user_message(self) -> str:
        return self.message or self.safe_response or SAFE_REFUSAL


@dataclass(frozen=True)
class GuardrailsConfig:
    enabled: bool = True
    min_retrieval_score: float = 0.18
    min_retrieval_pages: int = 1
    min_context_overlap: float = 0.12
    block_injection: bool = True
    block_jailbreak: bool = True
    log_blocks: bool = True
    log_path: Path = field(default_factory=lambda: INDEX_DATA_DIR / "guardrails" / "blocked_queries.jsonl")
    max_query_chars: int = RAG_MAX_QUERY_CHARS


@dataclass(frozen=True)
class RetrievalMetrics:
    page_scores: tuple[float, ...]
    max_score: float
    mean_top_score: float
    page_count: int


def load_guardrails_config() -> GuardrailsConfig:
    return GuardrailsConfig(
        enabled=RAG_GUARDRAILS_ENABLED,
        min_retrieval_score=RAG_RETRIEVAL_MIN_SCORE,
        min_retrieval_pages=RAG_RETRIEVAL_MIN_PAGES,
        min_context_overlap=RAG_RESPONSE_MIN_CONTEXT_OVERLAP,
        block_injection=RAG_GUARDRAIL_BLOCK_INJECTION,
        block_jailbreak=RAG_GUARDRAIL_BLOCK_JAILBREAK,
        log_blocks=RAG_GUARDRAIL_LOG_BLOCKS,
        log_path=Path(RAG_GUARDRAIL_LOG_PATH),
        max_query_chars=RAG_MAX_QUERY_CHARS,
    )


# ---------------------------------------------------------------------------
# Pattern libraries (configurable via rules flags)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[BlockReason, re.Pattern[str]]] = [
    (BlockReason.PROMPT_INJECTION, re.compile(p, re.IGNORECASE))
    for p in (
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+instructions",
        r"disregard\s+(the\s+)?(system|document|context|rules)",
        r"override\s+(your\s+|the\s+)?(instructions|rules|policy)",
        r"forget\s+(everything|all)\s+(you\s+)?(were\s+)?(told|trained)",
        r"reveal\s+(your\s+|the\s+)?(system|hidden|secret)\s+prompt",
        r"print\s+(the\s+)?(system|initial)\s+prompt",
        r"new\s+instructions\s*:",
        r"<\s*/?\s*system\s*>",
        r"\[INST\]",
        r"###\s*instruction",
        r"act\s+as\s+if\s+you\s+(are|were)\s+",
        r"developer\s+mode",
        r"bypass\s+(safety|content|restrictions|filters)",
        r"do\s+anything\s+now",
        r"you\s+must\s+now\s+",
    )
]

_JAILBREAK_PATTERNS: list[tuple[BlockReason, re.Pattern[str]]] = [
    (BlockReason.JAILBREAK, re.compile(p, re.IGNORECASE))
    for p in (
        r"\bjailbreak\b",
        r"\bDAN\s+mode\b",
        r"you\s+are\s+now\s+(dan|unrestricted|uncensored)",
        r"pretend\s+you\s+are\s+not\s+(bound|restricted|an?\s+ai)",
        r"no\s+(ethical|safety)\s+restrictions",
        r"role\s*play\s+as\s+",
        r"hypothetically[,]?\s+if\s+you\s+(could|had)\s+no\s+restrictions",
        r"simulate\s+an?\s+unfiltered\s+",
        r"opposite\s+mode",
        r"evil\s+mode",
        r"disable\s+(your\s+)?guardrails",
    )
]

_UNGROUNDED_PHRASES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bas an ai language model\b",
        r"\bas a language model\b",
        r"\bi don't have access to\b",
        r"\bmy training data\b",
        r"\bmy knowledge cutoff\b",
        r"\baccording to (wikipedia|the internet|general knowledge)\b",
        r"\bit is widely known\b",
        r"\bin general,?\s+(people|users|companies)\b",
        r"\btypically,?\s+organizations\b",
        r"\boutside (of )?the (provided )?documents?\b",
    )
]

_REFUSAL_MARKERS = (
    "i do not know",
    "i don't know",
    "not found in the documents",
    "not in the documents",
    "no relevant",
    "cannot find",
    "can't find",
    "insufficient information in",
    "the documents do not",
    "uploaded documents do not",
)

_BRACKET_CITATION_RE = re.compile(r"\s*\[[^\]]+\]", re.IGNORECASE)
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_STOPWORDS = frozenset(
    "a an the and or but if is are was were be been being to of in on at for with by from as it this that these those".split()
)


# ---------------------------------------------------------------------------
# Blocked-query logger
# ---------------------------------------------------------------------------


def log_blocked_query(
    *,
    config: GuardrailsConfig,
    user_id: str | None,
    stage: ValidationStage,
    code: str,
    query: str,
    detail: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    if not config.log_blocks:
        return
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": (user_id or "").strip() or "anonymous",
        "stage": stage.value,
        "code": code,
        "query_preview": (query or "")[:240],
        "detail": detail[:500] if detail else "",
    }
    if extra:
        entry["extra"] = extra
    path = config.log_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must not break requests


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def compute_retrieval_metrics(query: str, pages: list[RetrievedPage]) -> RetrievalMetrics:
    scores = [
        text_relevance_score(query, title=p.title, text=p.text, summary=p.title)
        for p in pages
    ]
    if not scores:
        return RetrievalMetrics((), 0.0, 0.0, 0)
    top = sorted(scores, reverse=True)[:3]
    return RetrievalMetrics(
        page_scores=tuple(scores),
        max_score=max(scores),
        mean_top_score=sum(top) / len(top),
        page_count=len(pages),
    )


def _fail(
    *,
    config: GuardrailsConfig,
    user_id: str | None,
    stage: ValidationStage,
    code: BlockReason,
    message: str,
    safe_response: str,
    query: str = "",
    detail: str = "",
    extra: dict[str, Any] | None = None,
) -> GuardResult:
    log_blocked_query(
        config=config,
        user_id=user_id,
        stage=stage,
        code=code.value,
        query=query,
        detail=detail or message,
        extra=extra,
    )
    return GuardResult(
        ok=False,
        message=message,
        stage=stage,
        code=code.value,
        safe_response=safe_response,
    )


def validate_input(
    query: str,
    *,
    config: GuardrailsConfig | None = None,
    user_id: str | None = None,
) -> GuardResult:
    cfg = config or load_guardrails_config()
    q = (query or "").strip()
    if not cfg.enabled:
        return GuardResult(True)

    if not q:
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.INPUT,
            code=BlockReason.EMPTY_QUERY,
            message="Question cannot be empty.",
            safe_response="Please enter a question about your documents.",
            query=q,
        )
    if len(q) > cfg.max_query_chars:
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.INPUT,
            code=BlockReason.QUERY_TOO_LONG,
            message=f"Question is too long (max {cfg.max_query_chars} characters).",
            safe_response=f"Shorten your question to under {cfg.max_query_chars} characters.",
            query=q,
        )

    if cfg.block_injection:
        for reason, pat in _INJECTION_PATTERNS:
            if pat.search(q):
                return _fail(
                    config=cfg,
                    user_id=user_id,
                    stage=ValidationStage.INPUT,
                    code=reason,
                    message=SAFE_BLOCKED_INPUT,
                    safe_response=SAFE_BLOCKED_INPUT,
                    query=q,
                    detail=f"pattern={pat.pattern}",
                )

    if cfg.block_jailbreak:
        for reason, pat in _JAILBREAK_PATTERNS:
            if pat.search(q):
                return _fail(
                    config=cfg,
                    user_id=user_id,
                    stage=ValidationStage.INPUT,
                    code=reason,
                    message=SAFE_BLOCKED_INPUT,
                    safe_response=SAFE_BLOCKED_INPUT,
                    query=q,
                    detail=f"pattern={pat.pattern}",
                )

    return GuardResult(True)


def validate_retrieval(
    query: str,
    pages: list[RetrievedPage],
    *,
    config: GuardrailsConfig | None = None,
    user_id: str | None = None,
) -> GuardResult:
    cfg = config or load_guardrails_config()
    if not cfg.enabled:
        return GuardResult(True)

    if not pages:
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.RETRIEVAL,
            code=BlockReason.NO_DOCUMENTS,
            message=SAFE_NO_CONTEXT,
            safe_response=SAFE_NO_CONTEXT,
            query=query,
        )

    metrics = compute_retrieval_metrics(query, pages)
    if metrics.page_count < cfg.min_retrieval_pages:
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.RETRIEVAL,
            code=BlockReason.LOW_RETRIEVAL_CONFIDENCE,
            message=SAFE_NO_CONTEXT,
            safe_response=SAFE_NO_CONTEXT,
            query=query,
            detail="insufficient_pages",
            extra={"page_count": metrics.page_count},
        )

    if metrics.max_score < cfg.min_retrieval_score:
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.RETRIEVAL,
            code=BlockReason.LOW_RETRIEVAL_CONFIDENCE,
            message=SAFE_NO_CONTEXT,
            safe_response=SAFE_NO_CONTEXT,
            query=query,
            detail="below_confidence_threshold",
            extra={
                "max_score": round(metrics.max_score, 4),
                "mean_top_score": round(metrics.mean_top_score, 4),
                "threshold": cfg.min_retrieval_score,
            },
        )

    return GuardResult(True)


def _context_overlap_ratio(answer: str, context: str) -> float:
    ans = {t for t in _TOKEN_RE.findall((answer or "").lower()) if t not in _STOPWORDS and len(t) > 2}
    if not ans:
        return 1.0
    ctx = set(_TOKEN_RE.findall((context or "").lower()))
    if not ctx:
        return 0.0
    return len(ans & ctx) / len(ans)


def _has_refusal_tone(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def validate_response(
    query: str,
    answer: str,
    pages: list[RetrievedPage],
    *,
    sources: list[str] | None = None,
    config: GuardrailsConfig | None = None,
    user_id: str | None = None,
) -> GuardResult:
    cfg = config or load_guardrails_config()
    text = (answer or "").strip()
    if not cfg.enabled or not text:
        return GuardResult(True)

    for pat in _UNGROUNDED_PHRASES:
        if pat.search(text):
            return _fail(
                config=cfg,
                user_id=user_id,
                stage=ValidationStage.RESPONSE,
                code=BlockReason.UNGROUNDED_RESPONSE,
                message=SAFE_REFUSAL,
                safe_response=SAFE_REFUSAL,
                query=query,
                detail=f"pattern={pat.pattern}",
            )

    context_blob = "\n".join(f"{p.title}\n{p.text}" for p in pages)
    overlap = _context_overlap_ratio(text, context_blob)
    if overlap < cfg.min_context_overlap and not _has_refusal_tone(text):
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.RESPONSE,
            code=BlockReason.LOW_CONTEXT_OVERLAP,
            message=SAFE_REFUSAL,
            safe_response=SAFE_REFUSAL,
            query=query,
            detail="low_overlap_with_retrieval",
            extra={"overlap": round(overlap, 4), "threshold": cfg.min_context_overlap},
        )

    grounded = enforce_grounded_reply(text, sources or [])
    if grounded != text and not _has_refusal_tone(grounded):
        return _fail(
            config=cfg,
            user_id=user_id,
            stage=ValidationStage.RESPONSE,
            code=BlockReason.UNSAFE_RESPONSE,
            message=grounded,
            safe_response=grounded,
            query=query,
            detail="enforce_grounded_reply",
        )

    return GuardResult(True)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class GuardrailsPipeline:
    """Modular input → retrieval → response validation."""

    def __init__(self, config: GuardrailsConfig | None = None) -> None:
        self.config = config or load_guardrails_config()

    def validate_input(self, query: str, *, user_id: str | None = None) -> GuardResult:
        return validate_input(query, config=self.config, user_id=user_id)

    def validate_retrieval(
        self,
        query: str,
        pages: list[RetrievedPage],
        *,
        user_id: str | None = None,
    ) -> GuardResult:
        return validate_retrieval(query, pages, config=self.config, user_id=user_id)

    def validate_response(
        self,
        query: str,
        answer: str,
        pages: list[RetrievedPage],
        *,
        sources: list[str] | None = None,
        user_id: str | None = None,
    ) -> GuardResult:
        return validate_response(
            query,
            answer,
            pages,
            sources=sources,
            config=self.config,
            user_id=user_id,
        )

    def finalize_answer(
        self,
        answer: str,
        *,
        had_context: bool,
        sources: list[str],
        preserve_lines: bool = False,
    ) -> str:
        text = sanitize_answer(answer, had_context=had_context, preserve_lines=preserve_lines)
        text = strip_bracket_citations(text)
        return enforce_grounded_reply(text, sources)


_pipeline: GuardrailsPipeline | None = None


def get_guardrails_pipeline() -> GuardrailsPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GuardrailsPipeline()
    return _pipeline


# ---------------------------------------------------------------------------
# Legacy helpers (backward compatible)
# ---------------------------------------------------------------------------


def validate_query(query: str, *, user_id: str | None = None) -> GuardResult:
    return validate_input(query, user_id=user_id)


def validate_strict_context(has_pages: bool, *, user_id: str | None = None) -> GuardResult:
    if has_pages:
        return GuardResult(True)
    cfg = load_guardrails_config()
    return _fail(
        config=cfg,
        user_id=user_id,
        stage=ValidationStage.RETRIEVAL,
        code=BlockReason.NO_DOCUMENTS,
        message=SAFE_NO_CONTEXT,
        safe_response=SAFE_NO_CONTEXT,
        query="",
    )


def strip_bracket_citations(text: str) -> str:
    return _BRACKET_CITATION_RE.sub("", text or "").strip()


def _clamp_bullet_text(text: str, *, max_lines: int = 2, max_words: int = 28) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    if parts:
        t = " ".join(parts[:max_lines])
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return t


def normalize_bullet_lines(text: str, *, max_lines_per_bullet: int = 2) -> str:
    cleaned = strip_bracket_citations(text)
    cleaned = re.sub(r"\*{2,3}\s*([^*]+?)\s*\*{2,3}", r"\n\1\n", cleaned)
    cleaned = re.sub(r"\s*•\s*", "\n• ", cleaned)
    cleaned = re.sub(r"(?<!\n)\s+\*\s+", "\n• ", cleaned)
    cleaned = re.sub(r"(?<!\n)\s+-\s+", "\n• ", cleaned)
    bullets: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip().lstrip("*").strip()
        if not line:
            continue
        if line.startswith("•"):
            line = line[1:].strip()
        elif line.startswith("-"):
            line = line[1:].strip()
        short = _clamp_bullet_text(line, max_lines=max_lines_per_bullet)
        if short:
            bullets.append("• " + short)
    return "\n".join(bullets)


def sanitize_answer(answer: str, *, had_context: bool, preserve_lines: bool = False) -> str:
    text = (answer or "").strip()
    if not had_context:
        return text
    for pat in _UNGROUNDED_PHRASES:
        text = pat.sub("", text)
    if preserve_lines:
        lines = [" ".join(ln.split()) for ln in text.splitlines()]
        return "\n".join(ln for ln in lines if ln)
    return " ".join(text.split())


def enforce_grounded_reply(answer: str, sources: list[str]) -> str:
    a = (answer or "").strip()
    low = a.lower()
    if sources:
        return a
    if _has_refusal_tone(a):
        return a
    if len(a) > 40:
        return (
            "I do not know — the indexed documents do not contain enough information to answer that question."
        )
    return a
