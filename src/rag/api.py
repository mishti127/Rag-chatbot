"""FastAPI REST API + static frontend."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from rag.answer import AnswerResult, TaskKind, answer_question
from rag.auth import (
    get_profile,
    load_notebook,
    register_user,
    save_notebook,
    save_user_theme,
    verify_login,
)
from rag.chat_store import (
    append_messages,
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
)
from rag.activity_history import (
    append_activity,
    delete_activity_entry,
    list_activity_by_kind,
)
from rag.tool_history import append_tool_run, delete_tool_history_entry, load_tool_history
from rag.upload_log import (
    append_removal,
    append_upload,
    delete_upload_log_entry,
    load_upload_log,
)
from rag.config import (
    FRONTEND_DIR,
    OPENROUTER_MODEL,
    RAG_TOP_K,
    get_hf_token,
    get_openrouter_api_key,
    refresh_env_from_project_dotenv,
)
from rag.stt import transcribe_audio
from rag.tts import synthesize_speech
from rag.hierarchical_summary import ensure_tree_summaries, outline_dict
from rag.index_store import delete_document, list_sources, load_document
from rag.document_compare import compare_documents
from rag.knowledge_map import build_knowledge_map
from rag.notes_export import export_markdown_to_docx, export_markdown_to_pdf
from rag.notes_generator import generate_notes
from rag.timeline_extract import build_timeline
from rag.ingest import ingest_uploaded_bytes
from rag.sessions import create_session, resolve_session, revoke_session
from rag.tool_presets import build_tool_prompt, list_tool_actions

app = FastAPI(title="Vectorless RAG", version="0.4.0")


@app.on_event("startup")
def _on_startup() -> None:
    refresh_env_from_project_dotenv()
    from rag.auth import init_auth_store

    init_auth_store()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

THEMES = [
    {"id": "midnight", "label": "Midnight"},
    {"id": "ocean", "label": "Ocean Blue"},
    {"id": "sunset", "label": "Sunset"},
    {"id": "forest", "label": "Forest"},
    {"id": "lavender", "label": "Lavender"},
    {"id": "ember", "label": "Ember"},
    {"id": "arctic", "label": "Arctic"},
    {"id": "light", "label": "Paper Light"},
]


def _bearer_token(authorization: str | None = None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


def current_user(authorization: str | None = Header(default=None)) -> str:
    token = _bearer_token(authorization)
    user = resolve_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


UserDep = Annotated[str, Depends(current_user)]


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    display_name: str
    email: str
    theme: str


class ThemeRequest(BaseModel):
    theme: str


class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = None
    source: str | None = None
    top_k: int = Field(default=RAG_TOP_K, ge=1, le=12)


class ToolRequest(BaseModel):
    action: str = "summarize"
    custom_prompt: str = ""
    source: str | None = None
    top_k: int = Field(default=RAG_TOP_K, ge=1, le=12)


class NotebookCreateRequest(BaseModel):
    title: str = ""
    body: str
    format: str = "plain"
    sources: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]
    thread_id: str | None = None
    retrieval_explanation: dict | None = None


class NotesGenerateRequest(BaseModel):
    source: str
    scope: str = "chapter"
    style: str = "bullets"
    focus: str = ""


class NotesExportRequest(NotesGenerateRequest):
    format: str = "pdf"


def _result_to_response(
    r: AnswerResult,
    *,
    thread_id: str | None = None,
    include_citations: bool = True,
) -> QueryResponse:
    return QueryResponse(
        answer=r.answer,
        citations=r.sources if include_citations else [],
        thread_id=thread_id,
        retrieval_explanation=r.retrieval_explanation,
    )


def _notebook_notes_only(user: str) -> list[dict]:
    return [e for e in load_notebook(user) if (e.get("kind") or "note") == "note"]


def _delete_notebook_entry(user: str, ts: str) -> bool:
    ts = (ts or "").strip()
    nb = load_notebook(user)
    new: list[dict] = []
    removed = False
    for ent in nb:
        if (
            not removed
            and (ent.get("kind") or "note") == "note"
            and (ent.get("ts") or "").strip() == ts
        ):
            removed = True
            continue
        new.append(ent)
    if not removed:
        return False
    save_notebook(user, new)
    return True


def _reconcile_notebook_storage(user: str) -> None:
    """Keep only user notes in notebook.json; move tool runs to tool_history.json."""
    nb = load_notebook(user)
    if not nb:
        return
    tools = [e for e in nb if e.get("kind") == "tool"]
    notes = [e for e in nb if (e.get("kind") or "note") == "note"]
    if tools or len(notes) != len(nb):
        save_notebook(user, notes)
        for ent in tools:
            append_tool_run(
                user,
                action=ent.get("title") or "tool",
                body=ent.get("body") or "",
                fmt=ent.get("format") or "plain",
                source=(ent.get("sources") or [None])[0] if ent.get("sources") else None,
            )


def _append_notebook(
    user: str,
    *,
    kind: str,
    title: str,
    body: str,
    fmt: str,
    sources: list[str],
) -> None:
    nb = load_notebook(user)
    nb.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "title": title,
            "body": body,
            "format": fmt,
            "sources": sources,
        }
    )
    save_notebook(user, nb)


API_FEATURES = (
    "knowledge_map",
    "timeline",
    "compare",
    "notes",
    "document_outline",
    "retrieval_explain",
    "tts",
    "stt",
)


@app.get("/api/health")
def health() -> dict:
    refresh_env_from_project_dotenv()
    return {
        "ok": True,
        "api_key_set": bool(get_openrouter_api_key()),
        "tts_configured": bool(get_hf_token()),
        "stt_configured": bool(get_hf_token()),
        "version": app.version,
        "features": list(API_FEATURES),
    }


@app.get("/api/meta")
def meta() -> dict:
    return {
        "themes": THEMES,
        "tool_actions": list_tool_actions(),
        "features": list(API_FEATURES),
        "tts_configured": bool(get_hf_token()),
        "stt_configured": bool(get_hf_token()),
    }


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    model: str | None = None


@app.post("/api/tts")
def tts_speak(body: TtsRequest, user: UserDep) -> Response:
    del user  # auth gate only
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")
    try:
        audio_bytes, media_type = synthesize_speech(text, model=body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"Content-Disposition": 'inline; filename="speech.wav"'},
    )


@app.post("/api/stt")
async def stt_transcribe(
    user: UserDep,
    file: UploadFile = File(...),
) -> dict:
    del user
    if not file.filename:
        raise HTTPException(status_code=400, detail="No audio file received.")
    from rag.config import RAG_STT_MAX_BYTES

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(data) > RAG_STT_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Audio too large (max {RAG_STT_MAX_BYTES // (1024 * 1024)} MB).",
        )
    try:
        text = transcribe_audio(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"text": text}


@app.post("/api/auth/register", response_model=LoginResponse)
def register(body: RegisterRequest) -> LoginResponse:
    user = body.username.strip().lower()
    try:
        register_user(user, body.password, body.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not verify_login(user, body.password):
        raise HTTPException(status_code=500, detail="Registration failed")
    sess = create_session(user)
    profile = get_profile(sess.username)
    return LoginResponse(
        token=sess.token,
        username=profile.username,
        display_name=profile.display_name,
        email=profile.email,
        theme=profile.theme,
    )


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    user = body.username.strip().lower()
    if not verify_login(user, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    sess = create_session(user)
    profile = get_profile(user)
    return LoginResponse(
        token=sess.token,
        username=profile.username,
        display_name=profile.display_name,
        email=profile.email,
        theme=profile.theme,
    )


@app.post("/api/auth/logout")
def logout(authorization: str | None = None) -> dict:
    revoke_session(_bearer_token(authorization))
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: UserDep) -> dict:
    p = get_profile(user)
    return {
        "username": p.username,
        "display_name": p.display_name,
        "email": p.email,
        "theme": p.theme,
    }


@app.patch("/api/auth/theme")
def set_theme(body: ThemeRequest, user: UserDep) -> dict:
    save_user_theme(user, body.theme)
    return {"theme": body.theme}


@app.get("/api/chats")
def chats_list(user: UserDep) -> dict:
    return {"threads": list_threads(user)}


@app.post("/api/chats")
def chats_create(user: UserDep) -> dict:
    t = create_thread(user)
    return {"thread": t}


@app.get("/api/chats/{thread_id}")
def chats_get(thread_id: str, user: UserDep) -> dict:
    t = get_thread(user, thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"thread": t}


@app.delete("/api/chats/{thread_id}")
def chats_delete(thread_id: str, user: UserDep) -> dict:
    if delete_thread(user, thread_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Chat not found")


@app.post("/api/chat", response_model=QueryResponse)
def chat(body: ChatRequest, user: UserDep) -> QueryResponse:
    refresh_env_from_project_dotenv()
    thread_id = body.thread_id
    if not thread_id:
        thread_id = create_thread(user)["id"]
    try:
        result = answer_question(
            body.question,
            top_k=body.top_k,
            model=OPENROUTER_MODEL,
            user_id=user,
            task=TaskKind.ASK,
            source_filter=(body.source or "").strip() or None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    append_messages(
        user,
        thread_id,
        user_content=body.question,
        assistant_content=result.answer,
        citations=result.sources,
    )
    return _result_to_response(result, thread_id=thread_id, include_citations=False)


@app.post("/api/tools/run", response_model=QueryResponse)
def tools_run(body: ToolRequest, user: UserDep) -> QueryResponse:
    refresh_env_from_project_dotenv()
    prompt = build_tool_prompt(body.action, body.custom_prompt)
    try:
        result = answer_question(
            prompt,
            top_k=body.top_k,
            model=OPENROUTER_MODEL,
            user_id=user,
            task=TaskKind.SUMMARIZE,
            source_filter=body.source,
            tool_action=body.action,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    fmt = body.action if body.action in ("bullet_points", "headings", "index") else "plain"
    append_tool_run(
        user,
        action=body.action,
        body=result.answer,
        fmt=fmt,
        source=body.source,
    )
    return _result_to_response(result, include_citations=False)


@app.get("/api/documents")
def documents(user: UserDep) -> dict:
    return {"sources": list_sources(user)}


@app.post("/api/documents/upload")
async def upload_documents(
    user: UserDep,
    files: list[UploadFile] = File(...),
) -> dict:
    indexed: list[str] = []
    errors: list[str] = []
    for f in files:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if suffix not in {".pdf", ".txt"}:
            errors.append(f"{f.filename}: only PDF and TXT allowed")
            continue
        try:
            data = await f.read()
            ingest_uploaded_bytes(user, f.filename, data)
            indexed.append(f.filename)
            append_upload(user, f.filename)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.filename}: {exc}")
    return {"indexed": indexed, "errors": errors}


@app.post("/api/notes/generate")
def notes_generate(body: NotesGenerateRequest, user: UserDep) -> dict:
    refresh_env_from_project_dotenv()
    try:
        result = generate_notes(
            user,
            body.source,
            scope=body.scope,
            style=body.style,
            focus=body.focus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    append_activity(
        user,
        "notes",
        title=f"Notes: {result.source}",
        summary=f"{result.scope} · {result.style}"
        + (f" · {len(result.sections)} section(s)" if result.sections else ""),
        body=result.markdown,
        meta={
            "source": result.source,
            "scope": result.scope,
            "style": result.style,
            "focus": body.focus or "",
        },
    )
    return {
        "source": result.source,
        "scope": result.scope,
        "style": result.style,
        "markdown": result.markdown,
        "sections": [
            {
                "node_id": s.node_id,
                "title": s.title,
                "kind": s.kind,
                "path": s.path,
            }
            for s in result.sections
        ],
    }


@app.post("/api/notes/export")
def notes_export(body: NotesExportRequest, user: UserDep) -> Response:
    refresh_env_from_project_dotenv()
    export_fmt = (body.format or "pdf").strip().lower()
    try:
        result = generate_notes(
            user,
            body.source,
            scope=body.scope,
            style=body.style,
            focus=body.focus,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    safe_name = Path(body.source).stem.replace(" ", "_")[:60] or "notes"
    if export_fmt == "docx":
        data = export_markdown_to_docx(result.markdown, title=f"Notes — {body.source}")
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_notes.docx"'},
        )
    if export_fmt in {"pdf", ""}:
        data = export_markdown_to_pdf(result.markdown, title=f"Notes — {body.source}")
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_notes.pdf"'},
        )
    raise HTTPException(status_code=400, detail="format must be pdf or docx")


@app.get("/api/knowledge-map")
def knowledge_map(user: UserDep, source: str = "") -> dict:
    src = (source or "").strip()
    try:
        data = build_knowledge_map(user, source_filter=src or None).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats = data.get("stats") or {}
    node_n = stats.get("node_count", 0)
    edge_n = stats.get("edge_count", 0)
    label = src or "All indexed documents"
    append_activity(
        user,
        "map",
        title=f"Map: {label}",
        summary=f"{node_n} nodes, {edge_n} edges",
        body=data.get("explanation") or "",
        meta={"source": src, "truncated": bool(data.get("truncated"))},
    )
    return data


@app.get("/api/timeline")
def timeline_api(user: UserDep, source: str = "") -> dict:
    src = (source or "").strip()
    try:
        data = build_timeline(user, source_filter=src or None).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stats = data.get("stats") or {}
    event_n = stats.get("event_count", 0)
    label = src or "All indexed documents"
    preview = ""
    events = data.get("events") or []
    if events:
        preview = ". ".join(
            f"{e.get('date_display', '')}: {e.get('title', '')}" for e in events[:8]
        )
    append_activity(
        user,
        "timeline",
        title=f"Timeline: {label}",
        summary=f"{event_n} event(s)",
        body=preview or (data.get("explanation") or ""),
        meta={"source": src},
    )
    return data


@app.get("/api/documents/{source:path}/outline")
def document_outline(source: str, user: UserDep) -> dict:
    src = unquote(source)
    rec = load_document(user, src)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")
    tree = ensure_tree_summaries(rec.tree)
    return {
        "source": src,
        "outline": outline_dict(tree),
        "node_count": len(tree.walk()),
        "leaf_count": len(tree.iter_leaves()),
    }


@app.get("/api/documents/{source:path}/nodes/{node_id}")
def document_node(source: str, node_id: str, user: UserDep) -> dict:
    src = unquote(source)
    rec = load_document(user, src)
    if not rec:
        raise HTTPException(status_code=404, detail="Document not found")
    tree = ensure_tree_summaries(rec.tree)
    node = tree.find_node(unquote(node_id))
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    from rag.hierarchical_summary import infer_node_kind
    from rag.page_tree import NodeKind

    is_root = node.node_id == tree.node_id
    kind = node.kind if node.kind != NodeKind.NODE else infer_node_kind(
        node, depth=0, is_document_root=is_root
    )
    return {
        "source": src,
        "node_id": node.node_id,
        "title": node.title,
        "summary": node.summary,
        "kind": kind.value,
        "has_content": bool((node.content or "").strip()),
        "content_preview": (node.content or "")[:2000],
    }


@app.delete("/api/documents/{source:path}")
def remove_document(source: str, user: UserDep) -> dict:
    if delete_document(user, source):
        append_removal(user, source)
        return {"deleted": source}
    raise HTTPException(status_code=404, detail="Document not found")


@app.post("/api/compare")
async def compare_documents_api(
    user: UserDep,
    file_a: UploadFile | None = File(None),
    file_b: UploadFile | None = File(None),
    source_a: str = Form(""),
    source_b: str = Form(""),
) -> dict:
    name_a = (source_a or "").strip() or (file_a.filename if file_a else "")
    name_b = (source_b or "").strip() or (file_b.filename if file_b else "")
    if not name_a or not name_b:
        raise HTTPException(
            status_code=400,
            detail="Provide two documents (upload files and/or indexed source names).",
        )
    data_a: bytes | None = None
    data_b: bytes | None = None
    if file_a and file_a.filename:
        data_a = await file_a.read()
        name_a = file_a.filename
    elif not (source_a or "").strip():
        raise HTTPException(status_code=400, detail="Document A is missing.")
    if file_b and file_b.filename:
        data_b = await file_b.read()
        name_b = file_b.filename
    elif not (source_b or "").strip():
        raise HTTPException(status_code=400, detail="Document B is missing.")
    try:
        result = compare_documents(
            user,
            name_a=name_a,
            name_b=name_b,
            data_a=data_a,
            data_b=data_b,
        )
        append_activity(
            user,
            "compare",
            title=f"{result.doc_a} vs {result.doc_b}",
            summary=(
                f"{len(result.similarities)} similar, {len(result.differences)} different, "
                f"{len(result.rows)} section(s)"
            ),
            body=result.report_markdown,
            meta={"doc_a": result.doc_a, "doc_b": result.doc_b},
        )
        return result.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/notebook")
def notebook(user: UserDep) -> dict:
    _reconcile_notebook_storage(user)
    entries = sorted(_notebook_notes_only(user), key=lambda e: e.get("ts") or "")
    return {"entries": entries}


@app.get("/api/tools/history")
def tools_history(user: UserDep) -> dict:
    _reconcile_notebook_storage(user)
    entries = list(reversed(load_tool_history(user)))
    return {"entries": entries}


@app.get("/api/history")
def history(user: UserDep) -> dict:
    _reconcile_notebook_storage(user)
    chats = []
    for t in list_threads(user):
        chats.append(
            {
                "id": t.get("id"),
                "title": t.get("title") or "New chat",
                "updated": t.get("updated"),
            }
        )
    return {
        "chats": chats,
        "notebook": list(reversed(_notebook_notes_only(user))),
        "tools": list(reversed(load_tool_history(user))),
        "documents": list(reversed(load_upload_log(user))),
        "compare": list(reversed(list_activity_by_kind(user, "compare"))),
        "notes": list(reversed(list_activity_by_kind(user, "notes"))),
        "map": list(reversed(list_activity_by_kind(user, "map"))),
        "timeline": list(reversed(list_activity_by_kind(user, "timeline"))),
    }


@app.post("/api/notebook")
def notebook_create(body: NotebookCreateRequest, user: UserDep) -> dict:
    _reconcile_notebook_storage(user)
    _append_notebook(
        user,
        kind="note",
        title=body.title or "Note",
        body=body.body,
        fmt=body.format,
        sources=body.sources,
    )
    return {"ok": True}


@app.delete("/api/notebook/entries/{entry_ts:path}")
def notebook_delete_entry(entry_ts: str, user: UserDep) -> dict:
    _reconcile_notebook_storage(user)
    ts = unquote(entry_ts)
    if _delete_notebook_entry(user, ts):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Note not found")


@app.delete("/api/notebook")
def clear_notebook(user: UserDep) -> dict:
    save_notebook(user, [])
    return {"ok": True}


@app.delete("/api/tools/history/entries/{entry_ts:path}")
def tools_history_delete_entry(entry_ts: str, user: UserDep) -> dict:
    ts = unquote(entry_ts)
    if delete_tool_history_entry(user, ts):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Tool run not found")


@app.delete("/api/history/documents/entries/{entry_ts:path}")
def history_documents_delete_entry(entry_ts: str, user: UserDep) -> dict:
    ts = unquote(entry_ts)
    if delete_upload_log_entry(user, ts):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Entry not found")


@app.delete("/api/history/activity/{kind}/entries/{entry_ts:path}")
def history_activity_delete_entry(kind: str, entry_ts: str, user: UserDep) -> dict:
    ts = unquote(entry_ts)
    if delete_activity_entry(user, kind, ts):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Entry not found")


def _mount_frontend() -> None:
    if not FRONTEND_DIR.is_dir():
        return

    css_dir = FRONTEND_DIR / "css"
    js_dir = FRONTEND_DIR / "js"
    media_dir = FRONTEND_DIR / "media"

    @app.get("/css/main.css", include_in_schema=False)
    def main_css() -> FileResponse:
        return FileResponse(css_dir / "main.css", media_type="text/css")

    @app.get("/js/{path:path}", include_in_schema=False)
    def js_files(path: str) -> FileResponse:
        target = js_dir / path
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, media_type="application/javascript")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    if css_dir.is_dir():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.is_dir():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    if media_dir.is_dir():
        app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")


_mount_frontend()
