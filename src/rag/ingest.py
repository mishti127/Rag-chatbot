from __future__ import annotations


import shutil

from pathlib import Path



from pypdf import PdfReader

from pypdf.errors import PdfReadError



from rag.index_store import delete_document, hash_text, list_sources, load_document, save_document

from rag.hierarchical_summary import enrich_tree_summaries
from rag.page_tree import build_tree_from_pdf_pages, build_tree_from_text, file_content_hash



_SKIP_DIR_NAMES = frozenset({

    ".git",

    ".venv",

    "venv",

    "__pycache__",

    ".mypy_cache",

    ".pytest_cache",

    ".tox",

    "node_modules",

    "dist",

    "build",

    ".eggs",

    "data",

})





def _is_under_skipped_dir(path: Path, root: Path) -> bool:

    try:

        rel = path.relative_to(root)

    except ValueError:

        return True

    for part in rel.parts[:-1]:

        if part in _SKIP_DIR_NAMES or part.endswith(".egg-info"):

            return True

    return False





def _read_txt(path: Path) -> str:

    return path.read_text(encoding="utf-8", errors="replace")





def _read_pdf(path: Path) -> tuple[str, list[str]]:

    reader = PdfReader(str(path))

    page_texts: list[str] = []

    for page in reader.pages:

        page_texts.append(page.extract_text() or "")

    full = "\n\n".join(page_texts)

    return full, page_texts





def extract_text(path: Path) -> str:

    suffix = path.suffix.lower()

    if suffix == ".txt":

        return _read_txt(path)

    if suffix == ".pdf":

        return _read_pdf(path)[0]

    raise ValueError(f"Unsupported file type: {path}")





def iter_document_files(root: Path) -> list[Path]:

    root = root.resolve()

    files: list[Path] = []

    for p in root.rglob("*"):

        if not p.is_file():

            continue

        if p.suffix.lower() not in {".txt", ".pdf"}:

            continue

        if _is_under_skipped_dir(p, root):

            continue

        files.append(p)

    return sorted(files)





def _should_skip(user_id: str, rel: str, content_hash: str) -> bool:

    rec = load_document(user_id, rel)

    return rec is not None and rec.file_hash == content_hash





class IngestSummary:

    __slots__ = ("documents_indexed", "files_skipped_unchanged", "sources_deleted")



    def __init__(self, docs: int, skipped: int, deleted_sources: int) -> None:

        self.documents_indexed = docs

        self.files_skipped_unchanged = skipped

        self.sources_deleted = deleted_sources





def ingest_file(

    user_id: str,

    path: Path,

    *,

    source_name: str | None = None,

) -> str:

    """Index a single file into the user's PageIndex workspace. Returns source key."""

    path = path.resolve()

    rel = source_name or path.name

    suffix = path.suffix.lower()

    if suffix == ".txt":

        raw = _read_txt(path)

        tree = build_tree_from_text(rel, raw)

    elif suffix == ".pdf":

        raw, pages = _read_pdf(path)

        tree = build_tree_from_pdf_pages(rel, pages)
    else:
        raise ValueError(f"Unsupported file type: {path}")

    enrich_tree_summaries(tree)
    content_hash = file_content_hash(raw)

    save_document(user_id, rel, tree, file_hash=content_hash)

    return rel





def ingest_directory(

    root: Path,

    *,

    user_id: str = "default",

    reset: bool = False,

    collection_name: str | None = None,  # noqa: ARG001 — legacy CLI compat

) -> IngestSummary:

    """Ingest .txt/.pdf under root into vectorless PageIndex trees."""

    uid = (user_id or collection_name or "default").strip() or "default"

    root = root.resolve()

    files = iter_document_files(root)



    if reset:

        for src in list_sources(uid):

            delete_document(uid, src)



    if not files:

        deleted = 0

        for src in list_sources(uid):

            if delete_document(uid, src):

                deleted += 1

        return IngestSummary(0, 0, deleted)



    desired = {str(p.relative_to(root)).replace("\\", "/") for p in files}

    skipped = 0

    indexed = 0



    for path in files:

        rel = str(path.relative_to(root)).replace("\\", "/")

        try:

            if path.suffix.lower() == ".pdf":

                raw, page_texts = _read_pdf(path)

                content_hash = hash_text(raw)

                if not reset and _should_skip(uid, rel, content_hash):

                    skipped += 1

                    continue

                tree = build_tree_from_pdf_pages(rel, page_texts)
                enrich_tree_summaries(tree)
            else:

                raw = _read_txt(path)

                content_hash = hash_text(raw)

                if not reset and _should_skip(uid, rel, content_hash):

                    skipped += 1

                    continue

                tree = build_tree_from_text(rel, raw)

            enrich_tree_summaries(tree)
            save_document(uid, rel, tree, file_hash=content_hash)

            indexed += 1

        except (OSError, UnicodeError, ValueError, PdfReadError) as exc:

            print(f"skip {rel}: {exc}")

            delete_document(uid, rel)



    deleted_sources = 0

    for src in list_sources(uid):

        if src not in desired:

            if delete_document(uid, src):

                deleted_sources += 1



    return IngestSummary(indexed, skipped, deleted_sources)





def ingest_uploaded_bytes(

    user_id: str,

    filename: str,

    data: bytes,

) -> str:

    """Save upload to workspace and build PageIndex tree."""

    from rag.index_store import user_workspace



    ws = user_workspace(user_id)

    dest = ws / "documents" / Path(filename).name

    dest.write_bytes(data)

    tmp = dest

    return ingest_file(user_id, tmp, source_name=dest.name)





def clear_user_workspace(user_id: str) -> int:

    from rag.index_store import clear_user_index, user_workspace



    n = clear_user_index(user_id)

    docs_dir = user_workspace(user_id) / "documents"

    if docs_dir.is_dir():

        shutil.rmtree(docs_dir, ignore_errors=True)

        docs_dir.mkdir(parents=True, exist_ok=True)

    return n


