# Incremental Python market MCP — stage one

Approved scope: Python 3.14, parallel operation before cutover, EQ prices, EMA/RSI/MACD with explicit calculation conventions. C# MCP and agent configuration remain intact.

Four tool names match the current C# market manager allowlist:
- list_available_indicators
- get_latest_price
- get_historical_prices
- calculate_indicators

IMPORTANT: the current C# input schema uses indicator OBJECTS, not an array of strings. Example:
```json
{"symbol":"TCS","indicators":[{"name":"ema","period":5},{"name":"ema","period":13},{"name":"ema","period":21},{"name":"ema","period":55},{"name":"rsi","period":14},{"name":"macd"}],"timeframe":"daily","limit":250}
```

Stage one advertises only implemented EMA, RSI, MACD. Unsupported requests fail before accessing PostgreSQL. No historical TechIndicator.py, pandas, NumPy, subprocess, or temporary JSON file is needed.

## Install and unit tests (PowerShell)
```powershell
cd C:\Repo\StockAnalysis_AI\marketdata_mcp_python
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

## PostgreSQL connection and read validation

Use the existing database and credentials. These example values match your current local C# database configuration; change them to the instance being validated.
```powershell
$env:PGHOST = 'localhost'
$env:PGPORT = '5432'
$env:PGDATABASE = 'StockAnalysis_Bhavcopy'
$credential = Get-Credential -UserName postgres -Message 'Enter PostgreSQL credentials'
$env:PGUSER = $credential.UserName
$env:PGPASSWORD = $credential.GetNetworkCredential().Password
$env:MARKET_SERIES = 'EQ'
Test-NetConnection $env:PGHOST -Port ([int]$env:PGPORT)
.\.venv\Scripts\marketdata-validate.exe --symbol TCS --limit 250
```

A dedicated SELECT-only database role can be used instead. libpq PG* variables (or an existing PGPASSFILE) are supported; Npgsql's semicolon-delimited C# connection string is not accepted. .env.example is documentation and is not automatically loaded.

Validation queries the real equity_bhavcopy table, requires non-null OHLC and unique dates in the selected symbol/series, calculates all approved indicators, and verifies strict JSON serialization. Exit code 0 means enough rows were available for EMA55 and full MACD signal warm-up. On failure it prints the error type and PostgreSQL SQLSTATE without credentials. No DDL or writes occur.

Existing quoted column contract:
DATE1, SYMBOL, SERIES, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, TTL_TRD_QNTY.
The table resolves through the connection's search_path, matching the existing C# implementation.
Connection timeout: 10 seconds; statement timeout: 10 seconds; read-only transactions.

## Start beside C# (port 5000)
```powershell
$env:MCP_PORT = '8004'
.\.venv\Scripts\marketdata-mcp.exe
```

Keep the terminal open. In another terminal:
```powershell
Invoke-RestMethod http://127.0.0.1:8004/health
Invoke-RestMethod http://127.0.0.1:8004/health/ready
cd C:\Repo\StockAnalysis_AI\marketdata_mcp_python
.\.venv\Scripts\python.exe -m marketdata_mcp.smoke --symbol TCS
```

Set the same PG* variables in every terminal that performs direct DB validation; the MCP client smoke terminal needs none. /health is liveness; /health/ready checks query access/columns, not sufficient TCS history. The DB validation command is the data-readiness check.

## Explicit optional agent cutover after validation

Stop the agent with Ctrl+C in its existing terminal, preserving its Agent__* LLM configuration:
```powershell
$env:McpClientManager__Servers__0__Endpoint = 'http://localhost:8004/mcp'
dotnet run --project C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp\StockAnalysis.Agent.Api.csproj --urls http://localhost:8080
```

From another terminal:
```powershell
Invoke-RestMethod http://localhost:8080/api/mcp/servers | ConvertTo-Json -Depth 10
$body = @{
  arguments = @{
    symbol = 'TCS'; timeframe = 'daily'; limit = 250
    indicators = @(
      @{name='ema';period=5}, @{name='ema';period=13},
      @{name='ema';period=21}, @{name='ema';period=55},
      @{name='rsi';period=14}, @{name='macd'}
    )
  }
} | ConvertTo-Json -Depth 10
Invoke-RestMethod http://localhost:8080/api/mcp/tools/market__calculate_indicators/invoke -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 20
```

Confirm isError is false and inspect actual values. Use short_term in DevUI and ensure the audit footer reports real tool attempts. Model tool-calling behavior is independent of this migration.

Rollback: stop the agent, set the same endpoint variable to http://localhost:5000/mcp, and restart it. Keep C# running during parallel validation.

## Numerical conventions and intentional differences

- Candles: EQ only by default, chronological output. C# previously selected all series. Series can be set through MARKET_SERIES. Duplicate dates fail rather than silently merge.
- EMA: SMA seed of the first N closes, then alpha=2/(N+1); first N-1 outputs are null.
- RSI: Wilder smoothing seeded from N price changes; first N outputs are null. All-up=100, all-down=0, flat=50.
- MACD: fixed 12/26 EMA difference, 9-period SMA-seeded EMA signal. Line starts at candle 26; signal/histogram at candle 34. A legacy period=14 is accepted for schema compatibility but does not control MACD.
- Warm-up and insufficient history: null values, explicit requiredCandles/status. Input limit controls both calculation history and output. Seed-dependent results can differ when the lookback changes.
- Numeric calculations use binary floats; JSON contains no NaN/Infinity. These formulas are newly tested conventions, not historical TechIndicator parity.
- Price basis: stored daily bhavcopy OHLCV; no corporate-action adjustment is applied.
- Latest snapshot returns OHLCV, date, symbol and series; C# supplementary last_price/avg_price/turnover_lacs fields are not migrated in stage one.
- No live quotes, F&O, other indicators, container deployment, or removal of C# in this increment.

Next increment: validate on your real stored data, compare the selected calculation conventions, then extend the catalog and decide a permanent cutover.

Automated tests cover reference calculations, warm-up, edge cases, request validation, read-only SQL parameters, duplicates, and SDK tool discovery. Live user PostgreSQL data cannot be accessed from the execution workspace.
