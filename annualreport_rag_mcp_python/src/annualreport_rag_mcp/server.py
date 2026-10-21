from __future__ import annotations

import asyncio
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Settings
from .repository import AnnualReportRepository

settings = Settings.from_env()
repository = AnnualReportRepository.connect(
    qdrant_url=settings.qdrant_url,
    qdrant_api_key=settings.qdrant_api_key,
    collection=settings.collection,
    ollama_url=settings.ollama_url,
    embedding_model=settings.embedding_model,
    timeout_seconds=settings.request_timeout_seconds,
    max_results=settings.max_results,
)
mcp = MCPServer(
    "annualreport-rag-mcp",
    version="0.1.0",
    instructions=(
        "Read-only semantic retrieval over annual-report chunks in Qdrant. "
        "Use returned citation objects to attribute every factual claim."
    ),
    log_level=settings.log_level,
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _symbol(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be blank")
    return normalized


def _envelope(tool: str, data: list[dict], **query: object) -> dict:
    return {
        "status": "ok",
        "source": "qdrant",
        "collection": settings.collection,
        "tool": tool,
        "query": query,
        "count": len(data),
        "data": data,
    }


@mcp.tool(title="Search an annual report", annotations=READ_ONLY)
async def reports_search_annual_report(
    query: Annotated[str, Field(min_length=1, max_length=2_000)],
    symbol: Annotated[str, Field(min_length=1, max_length=32)],
    year: int | str | None = None,
    document_type: str | None = None,
    top_k: Annotated[int, Field(ge=1, le=20)] = 8,
    min_score: Annotated[float | None, Field(ge=0, le=1)] = None,
) -> dict:
    """Find cited annual-report passages using semantic similarity and bounded metadata filters."""
    normalized_symbol = _symbol(symbol)
    data = await asyncio.to_thread(
        repository.search,
        query=query,
        symbol=normalized_symbol,
        year=year,
        document_type=document_type,
        limit=top_k,
        min_score=min_score,
    )
    return _envelope(
        "reports_search_annual_report",
        data,
        query=query,
        symbol=normalized_symbol,
        year=year,
        document_type=document_type,
    )


@mcp.tool(title="Get an annual-report section", annotations=READ_ONLY)
async def reports_get_report_section(
    symbol: Annotated[str, Field(min_length=1, max_length=32)],
    year: int | str,
    section: Annotated[str, Field(min_length=1, max_length=500)],
    document_type: str | None = None,
    top_k: Annotated[int, Field(ge=1, le=20)] = 12,
) -> dict:
    """Retrieve the passages most relevant to a named section within one company's report year."""
    normalized_symbol = _symbol(symbol)
    data = await asyncio.to_thread(
        repository.search,
        query=section,
        symbol=normalized_symbol,
        year=year,
        document_type=document_type,
        limit=top_k,
        min_score=None,
    )
    return _envelope(
        "reports_get_report_section",
        data,
        symbol=normalized_symbol,
        year=year,
        section=section,
        document_type=document_type,
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    dependencies = await asyncio.to_thread(repository.health)
    ready = all(dependencies.values())
    return JSONResponse(
        {"status": "ok" if ready else "degraded", "service": "annualreport-rag-mcp", "dependencies": dependencies},
        status_code=200 if ready else 503,
    )


def main() -> None:
    security = TransportSecuritySettings(allowed_hosts=list(settings.allowed_hosts))
    mcp.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.path,
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )


if __name__ == "__main__":
    main()

