from __future__ import annotations



import argparse

import sys

from pathlib import Path



from rag.answer import TaskKind, answer_question

from rag.config import DEFAULT_WORKSPACE, RAG_TOP_K

from rag.ingest import clear_user_workspace, ingest_directory





def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(

        prog="rag",

        description="Vectorless PageIndex-style RAG (strict document-only)",

    )

    sub = parser.add_subparsers(dest="command", required=True)



    p_ingest = sub.add_parser("ingest", help="Index .txt and .pdf into PageIndex trees")

    p_ingest.add_argument("path", type=Path, help="Root folder to scan (recursive)")

    p_ingest.add_argument(

        "--user",

        default=DEFAULT_WORKSPACE,

        help="User workspace id (default: default)",

    )

    p_ingest.add_argument("--reset", action="store_true", help="Clear workspace index before ingest")

    p_ingest.add_argument("--collection", default=None, help="Alias for --user (legacy)")



    p_ask = sub.add_parser("ask", help="Ask a question (strict, document-only)")

    p_ask.add_argument("question", help="Natural language question")

    p_ask.add_argument("-m", "--model", default=None)

    p_ask.add_argument("-k", "--top-k", type=int, default=RAG_TOP_K)

    p_ask.add_argument("--user", default=DEFAULT_WORKSPACE)

    p_ask.add_argument("--collection", default=None, help="Alias for --user")

    p_ask.add_argument(

        "--summarize",

        action="store_true",

        help="Summarize from indexed documents instead of Q&A",

    )



    p_serve = sub.add_parser("serve", help="Run web UI (FastAPI + HTML/CSS/JS)")
    p_serve.add_argument("--host", default=None, help="Bind host (default: RAG_API_HOST)")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port (default: RAG_API_PORT)")

    p_clear = sub.add_parser("clear", help="Clear a user's PageIndex workspace")

    p_clear.add_argument("--user", default=DEFAULT_WORKSPACE)

    p_clear.add_argument("--collection", default=None, help="Alias for --user")



    args = parser.parse_args(argv)

    user = (getattr(args, "user", None) or getattr(args, "collection", None) or DEFAULT_WORKSPACE).strip()



    if args.command == "ingest":

        p: Path = args.path

        if not p.is_dir():

            print(f"Not a directory: {p}", file=sys.stderr)

            return 1

        summary = ingest_directory(p, user_id=user, reset=args.reset)

        parts = [f"Indexed {summary.documents_indexed} document(s) from {p}"]

        if summary.files_skipped_unchanged:

            parts.append(f"skipped {summary.files_skipped_unchanged} unchanged")

        if summary.sources_deleted:

            parts.append(f"removed {summary.sources_deleted} stale source(s)")

        print(". ".join(parts) + ".")

        return 0



    if args.command == "ask":

        try:

            result = answer_question(

                args.question,

                top_k=args.top_k,

                model=args.model,

                user_id=user,

                task=TaskKind.SUMMARIZE if args.summarize else TaskKind.ASK,

            )

        except Exception as exc:  # noqa: BLE001

            print(str(exc), file=sys.stderr)

            return 1

        print(result.answer)

        if result.sources:

            print("\nSources:", ", ".join(result.sources))

        if result.retrieval_trace:

            print("\nRetrieval trace:")

            for line in result.retrieval_trace:

                print(f"  • {line}")

        return 0



    if args.command == "serve":
        import uvicorn
        from rag.config import API_HOST, API_PORT

        host = args.host or API_HOST
        port = args.port or API_PORT
        print(f"Open http://{host}:{port}/ in your browser")
        uvicorn.run("rag.api:app", host=host, port=port, reload=False)
        return 0

    if args.command == "clear":

        n = clear_user_workspace(user)

        print(f"Cleared workspace {user!r} ({n} index file(s) removed).")

        return 0



    return 1





if __name__ == "__main__":

    raise SystemExit(main())


