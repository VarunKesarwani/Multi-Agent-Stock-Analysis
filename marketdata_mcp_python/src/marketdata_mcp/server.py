import asyncio
import os
from typing import Annotated, Literal
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from . import repository
from .indicators import calculate

mcp = MCPServer("marketdata-mcp", version="0.1.0",
                instructions="Read-only daily EQ prices; EMA, RSI and MACD only. Discover tool schemas before calling.")
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
Limit = Annotated[int, Field(ge=1, le=5000)]


class IndicatorRequest(BaseModel):
    name: str
    period: int | None = Field(default=None, ge=1, le=5000)


def symbol_value(symbol):
    value = symbol.strip().upper()
    if not value or ":" in value:
        raise ValueError("Use a plain local symbol such as TCS, not NSE:TCS")
    return value


def normalize_requests(indicators):
    if not 1 <= len(indicators) <= 20:
        raise ValueError("Request between 1 and 20 indicators")
    output = []
    for item in indicators:
        name = item.name.strip().lower().removeprefix("calculate_")
        if name not in {"ema", "rsi", "macd"}:
            raise ValueError(f"Unsupported indicator '{name}'; discover the stage-one catalog")
        if name == "macd" and item.period not in (None, 14):
            raise ValueError("MACD uses fixed 12/26/9 parameters; omit period")
        output.append({"name": name, "period": item.period or 14})
    return output


@mcp.tool(annotations=READ_ONLY)
def list_available_indicators() -> dict:
    """List only implemented stage-one indicators. EMA/RSI support per-request periods."""
    return {"indicators": [
        {"name": name, "toolName": f"calculate_{name}", "defaultPeriod": 14,
         "description": description, "pythonSupported": True}
        for name, description in [
            ("ema", "SMA-seeded exponential moving average"),
            ("rsi", "Wilder RSI; flat history returns 50"),
            ("macd", "MACD 12/26/9 with SMA-seeded EMA signal"),
        ]
    ]}


@mcp.tool(annotations=READ_ONLY)
async def get_historical_prices(symbol: str, limit: Limit = 250) -> dict:
    """Daily candles, ascending by date; selected series defaults to EQ."""
    normalized = symbol_value(symbol)
    rows = await asyncio.to_thread(repository.candles, normalized, limit)
    return {"symbol": normalized, "timeframe": "daily", "candles": rows,
            "series": os.getenv("MARKET_SERIES", "EQ")}


@mcp.tool(annotations=READ_ONLY)
async def get_latest_price(symbol: str) -> dict | None:
    """Latest available daily OHLCV price snapshot, not a live quote."""
    normalized = symbol_value(symbol)
    rows = await asyncio.to_thread(repository.candles, normalized, 1)
    if not rows:
        return None
    row = rows[0]
    return {"date1": row["date"], "symbol": normalized,
            "series": os.getenv("MARKET_SERIES", "EQ"),
            "open_price": row["open"], "high_price": row["high"],
            "low_price": row["low"], "close_price": row["close"],
            "ttl_trd_qnty": row["volume"]}


@mcp.tool(annotations=READ_ONLY)
async def calculate_indicators(
    symbol: str, indicators: list[IndicatorRequest],
    timeframe: Literal["daily"] = "daily", limit: Limit = 250,
) -> dict:
    """Calculate EMA/RSI/MACD. Pass objects like {"name":"ema","period":55}.
    Warm-up values are null; limit is the history used, not just the output count.
    """
    normalized = symbol_value(symbol)
    requests = normalize_requests(indicators)
    rows = await asyncio.to_thread(repository.candles, normalized, limit)
    return {"symbol": normalized, "timeframe": timeframe, "results": calculate(rows, requests),
            "series": os.getenv("MARKET_SERIES", "EQ"),
            "priceBasis": "stored_unadjusted", "conventions": "sma-seeded-ema_wilder-rsi_macd-12-26-9"}


@mcp.custom_route("/health", methods=["GET"])
async def health(_):
    return JSONResponse({"status": "ok", "service": "marketdata-mcp"})


@mcp.custom_route("/health/ready", methods=["GET"])
async def ready(_):
    try:
        await asyncio.to_thread(repository.candles, "TCS", 1)
        return JSONResponse({"status": "ok", "dependency": "postgresql"})
    except Exception:
        return JSONResponse({"status": "unavailable", "dependency": "postgresql"}, status_code=503)


def main():
    host = os.getenv("MCP_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Stage-one server must bind to loopback")
    mcp.run(transport="streamable-http", host=host, port=int(os.getenv("MCP_PORT", "8004")),
            streamable_http_path="/mcp", stateless_http=True, json_response=True,
            transport_security=TransportSecuritySettings(
                allowed_hosts=["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]", "[::1]:*"]))


if __name__ == "__main__":
    main()
