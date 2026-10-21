"""Entry point for financial document ingestion, search, answers and HTTP API."""

import argparse
import json
from pathlib import Path

from src.utils.helpers import configure_logging
from src.utils.runtime import RuntimeSettings


def main() -> None:
    """Dispatch one configured RAG operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env", type=Path, help="Path to .env (defaults beside main.py)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--type", choices=["annual", "education", "all"], default="all")
    for name in ("search", "ask"):
        cmd = commands.add_parser(name)
        cmd.add_argument("query")
        cmd.add_argument("--limit", type=int)
        cmd.add_argument("--document-type")
        cmd.add_argument("--symbol")
        cmd.add_argument("--year")
        cmd.add_argument("--topic")
        cmd.add_argument("--min-score", type=float)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    settings = RuntimeSettings.from_env(args.env)
    configure_logging(settings.log_file)
    if args.command == "serve":
        import uvicorn

        from src.api.routes import create_app

        uvicorn.run(create_app(args.env), host=args.host, port=args.port)
        return
    if args.command == "ingest":
        from src.ingestion.loader import run_ingestion

        result = run_ingestion(args.type, args.env)
        print(json.dumps(result, indent=2))
        if result["failed_documents"]:
            raise SystemExit(1)
        return
    from src.retrieval.retriever import SearchRequest
    from src.retrieval.service import open_service

    request = SearchRequest(
        query=args.query,
        limit=args.limit if args.limit is not None else settings.top_k,
        document_type=args.document_type,
        symbol=args.symbol,
        year=args.year,
        topic=args.topic,
        min_score=args.min_score,
    )
    with open_service(args.env) as service:
        result = getattr(service, args.command)(request)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
