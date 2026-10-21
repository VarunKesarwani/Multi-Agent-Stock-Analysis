"""Live Streamable HTTP tool validation against a running server."""
import argparse
import asyncio
import json
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(endpoint, symbol):
    async with streamable_http_client(endpoint) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            required = {"list_available_indicators", "get_latest_price",
                        "get_historical_prices", "calculate_indicators"}
            if not required.issubset(names):
                raise RuntimeError("Missing expected market tool names")
            for name, arguments in [
                ("list_available_indicators", {}),
                ("get_latest_price", {"symbol": symbol}),
                ("get_historical_prices", {"symbol": symbol, "limit": 5}),
                ("calculate_indicators", {"symbol": symbol, "limit": 250,
                    "indicators": [{"name": "ema", "period": p} for p in (5, 13, 21, 55)]
                    + [{"name": "rsi", "period": 14}, {"name": "macd"}]}),
            ]:
                result = await session.call_tool(name, arguments)
                if result.is_error:
                    raise RuntimeError(f"{name} returned an MCP tool error")
                print(json.dumps({"tool": name, "result": result.model_dump(mode="json", by_alias=True)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:8004/mcp")
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args()
    asyncio.run(run(args.endpoint, args.symbol))


if __name__ == "__main__":
    main()
