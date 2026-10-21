# Market Data MCP Server

This project is a .NET 8 ASP.NET Core MCP server using the official MCP C# SDK. It supports stdio for VS Code MCP Inspector and optional Streamable HTTP MCP at `/mcp`, while retaining HTTP diagnostics endpoints.

Technical indicators are orchestrated by the .NET service but calculated by the selected initial Python subprocess bridge in `Python/indicator_runner.py`, which calls the existing functions in `BhavanCopyIngestion/TechIndicator.py`. The public baseline is the current 35-name indicator catalog.

## Endpoints

- `GET /health`
- `POST/GET /mcp` (optional Streamable HTTP MCP transport)
- `GET /mcp/tools`
- `GET /api/company/{symbol}`
- `GET /api/equity/history/{symbol}`
- `GET /api/fo/history/{symbol}`
- `GET /api/latest/{symbol}`
- `GET /api/indicator/{indicator}/{symbol}?period=14&limit=250`
- `GET /mcp/indicators`
- `POST /mcp/indicators/calculate`
- `POST /mcp/call`

## VS Code MCP Inspector

Launch the server through stdio:

```bash
dotnet run --project marketdata-mcp-csharp/marketdata-mcp-csharp.csproj --no-build -- --stdio
```

The stdio MCP tools are:

- `list_available_indicators`
- `get_latest_price`
- `get_historical_prices`
- `calculate_indicators`

`calculate_indicators` accepts `symbol`, an `indicators` array containing the current 35 catalog names, `timeframe` (currently `daily`), and a bounded `limit`.

## MCP-Style Tool Calls

List available indicators:

```bash
curl http://localhost:5000/mcp/indicators
```

Calculate an indicator directly:

```bash
curl -X POST http://localhost:5000/mcp/indicators/calculate \
  -H "Content-Type: application/json" \
  -d '{"symbol":"RELIANCE","indicator":"rsi","period":14,"limit":250}'
```

Call by MCP tool name:

```bash
curl -X POST http://localhost:5000/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"name":"calculate_rsi","arguments":{"symbol":"RELIANCE","period":14,"limit":250}}'
```

Discovery tool:

```bash
curl -X POST http://localhost:5000/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"name":"list_available_indicators","arguments":{}}'
```

## Project Structure

```text
marketdata-mcp-csharp/
├── Program.cs
├── Models/
│   ├── IndicatorDefinition.cs
│   ├── IndicatorRequests.cs
│   └── OhlcvCandle.cs
├── Python/
│   └── indicator_runner.py
└── Services/
    ├── IndicatorCatalog.cs
    ├── MarketDataService.cs
    ├── PriceMovementProxyService.cs
    └── PythonIndicatorService.cs
```

## Configuration

Set `PG_CONNECTION_STRING` or `ConnectionStrings:DefaultConnection` for PostgreSQL access.
Set `PYTHON_EXECUTABLE` or `PythonIndicators:Executable` for the Python executable.
Set `PYTHON_INDICATOR_RUNNER` or `PythonIndicators:RunnerPath` to override the bundled runner path.

The Python environment must include:

```text
pandas
numpy
statsmodels
stocktrends
```

The PostgreSQL schema must match `PostgressScript/001_create_schema_merged.sql`, including quoted uppercase columns such as `"SYMBOL"`, `"DATE1"`, `"TTL_TRD_QNTY"`, `"ISIN_NUMBER"`, and `"FACE_VALUE"`.
