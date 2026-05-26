"""Smoke check: after `rag ingest sample_docs --user default`, verifies tree retrieval."""

from rag.index_store import build_workspace_forest
from rag.ingest import ingest_directory
from rag.config import PROJECT_ROOT
from rag.vectorless_retrieval import retrieve_pages_keyword


def main() -> None:
    sample = PROJECT_ROOT / "sample_docs"
    if sample.is_dir():
        ingest_directory(sample, user_id="default", reset=False)

    forest = build_workspace_forest("default")
    if forest is None:
        raise SystemExit("no index — run: rag ingest sample_docs")

    pages = retrieve_pages_keyword(
        forest,
        "What is the secret codeword for the dry run?",
        max_pages=5,
    )
    blob = "\n".join(p.text for p in pages)
    if "BLUEBIRD" not in blob:
        raise SystemExit(f"expected codeword in retrieved pages, got: {blob!r}")
    print("smoke_ok: vectorless retrieval contains BLUEBIRD")


if __name__ == "__main__":
    main()
