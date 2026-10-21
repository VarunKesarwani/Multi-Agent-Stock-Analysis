from __future__ import annotations

from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Settings
from .repository import NewsRepository

settings = Settings.from_env()
repository = NewsRepository.connect(
    url=settings.elasticsearch_url, index=settings.index, username=settings.username,
    password=settings.password, api_key=settings.api_key, verify_certs=settings.verify_certs,
    max_results=settings.max_results,
)
mcp = MCPServer(
    "newsdata-mcp", version="0.1.0",
    instructions="Read-only search and tone analysis over enriched financial news in Elasticsearch.",
    log_level=settings.log_level,
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _date(value: str | None):
    if value is None:
        return None
    from datetime import datetime, timezone
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _envelope(tool: str, data: object, **query: object) -> dict:
    return {"status": "ok", "source": "elasticsearch", "index": settings.index,
            "tool": tool, "query": query, "data": data}


@mcp.tool(title="Search enriched news", annotations=READ_ONLY)
async def news_search(
    query: str | None = None,
    categories: list[str] | None = None,
    sources: list[str] | None = None,
    tones: list[Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]] | None = None,
    symbol: str | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> dict:
    """Search completed enriched news using text and bounded metadata filters."""
    normalized_symbol = symbol.strip().upper() if symbol else None
    data = await repository.search_news(
        query=query, categories=categories, sources=sources, tones=tones, symbol=normalized_symbol,
        published_after=_date(published_after), published_before=_date(published_before), limit=limit,
    )
    return _envelope("news_search", data, query=query, symbol=normalized_symbol, categories=categories)


@mcp.tool(title="Get company news", annotations=READ_ONLY)
async def news_get_company_news(
    symbol: str,
    query: str | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
) -> dict:
    """Fetch enriched articles whose company-tone analysis contains the ticker symbol."""
    normalized_symbol = symbol.strip().upper()
    data = await repository.search_news(
        query=query, categories=None, sources=None, tones=None, symbol=normalized_symbol,
        published_after=_date(published_after), published_before=_date(published_before), limit=limit,
    )
    return _envelope("news_get_company_news", data, symbol=normalized_symbol, query=query)


@mcp.tool(title="Summarize news tone", annotations=READ_ONLY)
async def news_get_tone_summary(
    symbol: str | None = None,
    categories: list[str] | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
) -> dict:
    """Count tone and average confidence overall or for one company symbol."""
    normalized_symbol = symbol.strip().upper() if symbol else None
    data = await repository.tone_summary(
        symbol=normalized_symbol, categories=categories,
        published_after=_date(published_after), published_before=_date(published_before),
    )
    return _envelope("news_get_tone_summary", data, symbol=normalized_symbol, categories=categories)


@mcp.tool(title="Get news timeline", annotations=READ_ONLY)
async def news_get_timeline(
    symbol: str | None = None,
    categories: list[str] | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    interval: Literal["hour", "day", "week", "month"] = "day",
) -> dict:
    """Aggregate enriched article counts and overall tone counts over time."""
    normalized_symbol = symbol.strip().upper() if symbol else None
    data = await repository.timeline(
        symbol=normalized_symbol, categories=categories, published_after=_date(published_after),
        published_before=_date(published_before), interval=interval,
    )
    return _envelope("news_get_timeline", data, symbol=normalized_symbol, interval=interval)


@mcp.tool(title="List news categories", annotations=READ_ONLY)
async def news_list_categories() -> dict:
    """List categories present in completed enriched news documents."""
    data = await repository.list_categories()
    return _envelope("news_list_categories", data)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "newsdata-mcp"})


def main() -> None:
    security = TransportSecuritySettings(allowed_hosts=list(settings.allowed_hosts))
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port,
            streamable_http_path=settings.path, stateless_http=True, json_response=True,
            transport_security=security)


if __name__ == "__main__":
    main()

