"""Run the web API + frontend: `python -m rag.server` or `rag serve`."""

from __future__ import annotations

import uvicorn

from rag.config import API_HOST, API_PORT


def main() -> None:
    uvicorn.run(
        "rag.api:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
