from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import Settings
from .repository import FinancialRepository
from .serialization import parse_datetime

settings = Settings.from_env()
repository = FinancialRepository.connect(settings.mongodb_uri, settings.mongodb_database, settings.max_results)
mcp = MCPServer(
    "financialdata-mcp",
    version="0.1.0",
    instructions="Read-only access to normalized current financial facts in MongoDB.",
    log_level=settings.log_level,
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _envelope(tool: str, data: list[dict], **query: object) -> dict:
    return {"status": "ok", "source": "mongodb", "tool": tool, "query": query, "count": len(data), "data": data}


@mcp.tool(title="Get current financial facts", annotations=READ_ONLY)
async def financial_get_current_facts(
    symbol: str,
    source: Literal["SCREENER", "NSE_XBRL"] = "SCREENER",
    scope: Literal["STANDALONE", "CONSOLIDATED"] = "CONSOLIDATED",
    statement: str | None = None,
    metrics: list[str] | None = None,
    period_type: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
    limit: Annotated[int, Field(ge=1, le=500)] = 100,
) -> dict:
    """Fetch current, validated normalized facts. ISO-8601 dates filter on period_end."""
    normalized_symbol = symbol.strip().upper()
    data = await asyncio.to_thread(
        repository.get_current_facts, symbol=normalized_symbol, source=source, scope=scope,
        statement=statement, metrics=metrics, period_type=period_type,
        period_start=parse_datetime(period_start), period_end=parse_datetime(period_end), limit=limit,
    )
    return _envelope("financial_get_current_facts", data, symbol=normalized_symbol, source=source, scope=scope)


@mcp.tool(title="Get financial statement", annotations=READ_ONLY)
async def financial_get_statement(
    symbol: str,
    statement: str,
    scope: Literal["STANDALONE", "CONSOLIDATED"] = "CONSOLIDATED",
    period_type: str | None = None,
    periods: Annotated[int, Field(ge=1, le=20)] = 8,
) -> dict:
    """Return a period-oriented Screener statement with metrics grouped into rows."""
    normalized_symbol = symbol.strip().upper()
    data = await asyncio.to_thread(repository.get_statement, symbol=normalized_symbol, scope=scope,
                                   statement=statement, period_type=period_type, periods=periods)
    return _envelope("financial_get_statement", data, symbol=normalized_symbol, statement=statement, scope=scope)


@mcp.tool(title="Compare financial sources", annotations=READ_ONLY)
async def financial_compare_sources(
    symbol: str,
    scope: Literal["STANDALONE", "CONSOLIDATED"] = "CONSOLIDATED",
    metrics: list[str] | None = None,
    period_end: str | None = None,
    limit: Annotated[int, Field(ge=1, le=250)] = 100,
) -> dict:
    """Compare dimensionless current Screener and NSE XBRL facts by metric and period."""
    normalized_symbol = symbol.strip().upper()
    data = await asyncio.to_thread(repository.compare_sources, symbol=normalized_symbol, scope=scope,
                                   metrics=metrics, period_end=parse_datetime(period_end), limit=limit)
    return _envelope("financial_compare_sources", data, symbol=normalized_symbol, scope=scope)


@mcp.tool(title="List financial metrics", annotations=READ_ONLY)
async def financial_list_metrics(
    symbol: str,
    source: Literal["SCREENER", "NSE_XBRL"] = "SCREENER",
    scope: Literal["STANDALONE", "CONSOLIDATED"] = "CONSOLIDATED",
) -> dict:
    """List metric identifiers, labels, statements, and units available in the current dataset."""
    normalized_symbol = symbol.strip().upper()
    data = await asyncio.to_thread(repository.list_metrics, symbol=normalized_symbol, source=source, scope=scope)
    return _envelope("financial_list_metrics", data, symbol=normalized_symbol, source=source, scope=scope)


@mcp.tool(title="Get ingestion status", annotations=READ_ONLY)
async def financial_get_ingestion_status(
    symbol: str | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict:
    """Return recent financial ingestion runs, optionally filtered by symbol."""
    normalized_symbol = symbol.strip().upper() if symbol else None
    data = await asyncio.to_thread(repository.get_ingestion_status, symbol=normalized_symbol, limit=limit)
    return _envelope("financial_get_ingestion_status", data, symbol=normalized_symbol)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "financialdata-mcp"})


def main() -> None:
    security = TransportSecuritySettings(allowed_hosts=list(settings.allowed_hosts))
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port,
            streamable_http_path=settings.path, stateless_http=True, json_response=True,
            transport_security=security)


if __name__ == "__main__":
    main()

