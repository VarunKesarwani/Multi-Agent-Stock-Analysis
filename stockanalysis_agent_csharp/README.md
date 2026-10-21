# Stock Analysis Agent API — MCP Client Manager

This is the first layer of the C# Agent API. It connects to independent MCP servers, discovers their
tools, gives each tool a collision-safe agent-facing name, and invokes the original server tool.
Chat orchestration now runs above this layer; database and vector-store clients do not
belong in this project. See REQUIREMENTS_VALIDATION.md for implementation boundaries.

## Data boundaries

| Server id | MCP responsibility | Backing store |
|---|---|---|
| `market` | Prices and indicators | PostgreSQL / TimescaleDB |
| `financial` | Normalized financial statements and facts | MongoDB |
| `news` | News search and tone | Elasticsearch |
| `annual_reports` | Query embedding, vector retrieval, filters and citations | Ollama embeddings + Qdrant |
| `kite` | Live market, portfolio, account and order-history reads | Zerodha Kite hosted MCP |

Annual Report RAG is deliberately represented as an MCP server. That server must use the same
embedding model and vector settings used when the Qdrant collection was populated.

## Tool naming

The manager exposes tools to the agent as:

```text
{server-id}__{original-tool-name}
```

For example, `financial__financial_get_statement`. `McpClientTool.WithName` changes only the
model-facing name. This manager instead exposes a policy wrapper with that qualified name; the
wrapper routes execution back to the original MCP tool through the manager.

Configured allowlists currently expose:

| Server | Allowed tools |
|---|---|
| `market` | `list_available_indicators`, `get_latest_price`, `get_historical_prices`, `calculate_indicators` |
| `financial` | Five `financial_*` read tools from the MongoDB MCP server |
| `news` | Five `news_*` read tools from the Elasticsearch MCP server |
| `annual_reports` | `reports_search_annual_report`, `reports_get_report_section` when its server is enabled |
| `kite` | Login plus read-only market data, portfolio, account, order-history, trades and GTT tools |

Kite is connected directly over Streamable HTTP at `https://mcp.kite.trade/mcp`; the `npx
mcp-remote` bridge is only needed by clients that require a local stdio command. The explicit Kite
allowlist excludes `place_order`, `modify_order`, `cancel_order`, and every GTT mutation even if the
hosted server advertises them in the future. Kite is non-required so an external outage or pending
user login does not fail local readiness.

## Behavior

- Uses the official `ModelContextProtocol` 2.2.0 client package.
- Connects through Streamable HTTP.
- Discovers tool definitions from all enabled servers.
- Does not fail Agent API startup when one MCP server is unavailable.
- Retries unavailable servers on a configurable interval and supports manual refresh.
- Applies configurable initialization and tool-call timeouts.
- Serializes calls within one MCP server so reconnect cannot dispose an active client; calls to different servers remain parallel.
- Supports an optional per-server tool allowlist before tools are exposed to the model.
- Supports optional per-server headers through configuration.
- Provides `AIFunction` objects for the agent loop.
- Wraps model-facing functions so agent-triggered calls use the same timeout, logging, and reconnect-safe execution path as direct calls.
- Does not expose raw database, Elasticsearch, Qdrant, or Ollama embedding clients.

## Local endpoints

- `GET /health`
- `GET /health/ready`
- `GET /api/mcp/servers`
- `GET /api/mcp/tools`
- `POST /api/mcp/servers/{serverId}/refresh`
- `POST /api/mcp/tools/{qualifiedName}/invoke`

The invoke endpoint is intended for local integration testing. Protect or remove it before exposing
the Agent API outside the trusted local network; the normal chat flow will invoke tools internally.

Example:

```bash
curl -X POST http://localhost:8080/api/mcp/tools/financial__financial_get_statement/invoke \
  -H "Content-Type: application/json" \
  -d '{"arguments":{"symbol":"TCS","statement":"profit_loss","periods":5}}'
```

## Configuration

Configuration lives under `McpClientManager`. Environment variables can override every value using
ASP.NET Core's double-underscore convention:

```text
McpClientManager__Servers__0__Endpoint=http://127.0.0.1:8004/mcp
McpClientManager__Servers__1__Endpoint=http://financialdata-mcp:8001/mcp
McpClientManager__Servers__2__Endpoint=http://newsdata-mcp:8002/mcp
McpClientManager__Servers__3__Endpoint=http://annualreport-rag-mcp:8003/mcp
McpClientManager__Servers__3__Enabled=true
McpClientManager__Servers__4__Endpoint=https://mcp.kite.trade/mcp
```

Do not commit bearer tokens. Supply optional headers through environment variables or a secret store.

To authorize Kite, invoke the qualified `kite__login` tool and open the returned Zerodha login URL.
After authorization, use the remaining `kite__*` read tools. Credentials are entered only on
Zerodha's authorization page and are not stored in this configuration.

## Run

```bash
dotnet restore
dotnet run
```

For local development, start the Python Market Data MCP at `http://127.0.0.1:8004/mcp` before validating market tools. The local MCP servers may start independently. A missing server appears as `Degraded` in
`GET /api/mcp/servers`; the API continues running and reconnects automatically. Readiness returns
HTTP 503 while any enabled, required server is unavailable. Annual Report RAG remains opt-in through
configuration. Kite is enabled by default but remains non-required because it depends on an external
service and an interactive user authorization flow.

## AI analysis agent

`POST /api/agent/chat` accepts `message` and `mode`: `short_term`, `long_term`,
`portfolio`, or `tax`. Requests are stateless. The agent calls the existing manager
in-process through `GetAgentFunctionsAsync`; an HTTP hop back into its own API is unnecessary.
Two providers are implemented and selected with `Agent:Provider`: `ollama` (local, native
`/api/chat` protocol) and `sarvam` (Sarvam AI OpenAI-compatible chat completions). Neither
requires a new SDK dependency.

```powershell
cd C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp
$env:Agent__Enabled = 'true'
$env:Agent__Provider = 'ollama'
$env:Agent__Model = '<your-installed-tool-capable-model>'
$env:Agent__Endpoint = 'http://localhost:11434/'
dotnet run --urls http://localhost:8080
```

### Sarvam AI provider

Set `Agent:Provider=sarvam`. The endpoint becomes `https://api.sarvam.ai/`, the path
`v1/chat/completions`, and the model `sarvam-105b` (128K context, native tool calling). The API key
is read from .NET user secrets (`Agent:ApiKey`) or `Agent__ApiKey` and sent as the
`Authorization: Bearer` header; never commit it. See [Sarvam V1 setup](SARVAM_V1.md)
for secure configuration and incremental validation. Sarvam's
protocol differs from Ollama in four places: the request path and auth header, moving `temperature`
out of `options` (plus `max_tokens`), reading the reply from `choices[0].message`, and sending tool
results as `{ role:"tool", tool_call_id, content }` where `function.arguments` is a JSON string.
`SarvamAgent` handles all four.

```powershell
cd C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp
$env:Agent__Enabled = 'true'
$env:Agent__Provider = 'sarvam'
$env:Agent__Model = 'sarvam-105b'
$env:Agent__Endpoint = 'https://api.sarvam.ai/'
$env:Agent__ApiKey = '<sarvam-api-subscription-key>'
dotnet run --urls http://localhost:8080
```

From a second terminal:

```powershell
$body = @{ mode = 'short_term'; message = 'Analyze TCS momentum for a 1 to 4 week holding period. Check MACD, EMA 5/13/21/55, volume, RSI and latest news.' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/api/agent/chat -Method Post -ContentType 'application/json' -Body $body
```

Other examples: long_term: 'Assess TCS financial quality and annual-report risks';
portfolio: 'What inputs do you need to compute my Sharpe ratio and XIRR?';
tax: 'What records do you need for an Indian equity capital-gains estimate?'.
Missing data produces a request for inputs, not an invented result.

`Instructions/agent-system.md` defines behavior. `Instructions/strategy-rules.json`
contains editable starter rules. Restart after editing; each response includes their hash.
The JSON is injected as model guidance, not executed as a deterministic signal engine.
Numeric calculations run in C#, through local tools or these direct endpoints:

- `/api/analytics/cagr`: `startValue`, `endValue`, `start`, `end`, `hasExternalCashFlows`.
- `/api/analytics/performance`: `returns` (decimal rates), `periodsPerYear` (12/52/252),
  `annualRiskFreeRate`, `start`, `end`, `cashFlowAdjusted`, `includesDividendsAndFees`.
- `/api/analytics/xirr`: `flows` array of `{date, amount}`; negative investment,
  positive withdrawal and terminal valuation. Only conventional flows supported.
- `/api/analytics/tax-scenario`: jurisdiction, financialYear, ruleVersion, ruleSource,
  shortTermTaxableGain, longTermTaxableGain, shortTermRate, longTermRate,
  surchargeRate, cessRate, taxableBasesReconciled. Taxable bases must already account
  for applicable exemptions/setoffs. This is scenario arithmetic, not tax filing liability.

All endpoints accept POST JSON. Dates are ISO yyyy-MM-dd. All rate inputs/outputs are
decimal fractions (0.10 = 10%); values must use one currency. Performance data must be
regular observations over the stated dates; the caller is responsible for exchange-calendar
completeness. Sharpe assumes square-root annualization of regular returns. Benchmark
comparison and historical NAV reconstruction are not implemented yet.

Example deterministic request:

```powershell
$body = @{ startValue = 100000; endValue = 121000; start = '2024-01-01'; end = '2026-01-01'; hasExternalCashFlows = $false } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/api/analytics/cagr -Method Post -ContentType 'application/json' -Body $body
```

Keep this API loopback-only: it is a single-user development service without authentication.
Do not expose its chat, analytics or existing MCP invoke endpoints to a shared network.
Set `McpClientManager__Servers__3__Enabled=true` when annual-report RAG is ready.
Kite login does not guarantee access to complete historical broker ledgers.

### Financial number handling

Both agent providers build a request-local financial facts table from successful
financial MCP statement, current-fact and source-comparison envelopes (structured
content or JSON text content). Monetary values use invariant `decimal`; explicit
`INR` alone converts to `INR_CRORE` by division by `10000000m`. Raw values/units
remain in the rendered table. Other and absent units are never inferred or converted.
Statement source is SCREENER per the MCP statement contract, rather than its
transport/storage source `mongodb`. Symbol and statement are retained to prevent
claims matching unrelated company facts.

The public request/response shape is unchanged. Both agents use a shared
`CombinedResponse` renderer. The internal model response is JSON:

```json
{
  "price": { "evidenceIds": ["e1"] },
  "news": { "evidenceIds": ["e2"] },
  "financialFacts": { "claims": [], "commentary": "Qualitative interpretation." },
  "annualReport": { "evidenceIds": ["e3"] },
  "commentary": "Qualitative overall interpretation."
}
```

Evidence IDs are assigned by code to actual captured results. Price, headlines,
news links, report excerpts and citation metadata are rendered from those results;
model-generated IDs are validated within their section. Missing or invalid sections
fall back to available captured evidence without reconstructing arbitrary prose.
Malformed/empty model output returns a nonempty evidence fallback with status
`incomplete`, rather than claiming successful completion. Missing news explicitly
means unknown sentiment. Report source, page and section are shown only when
returned in citation/metadata fields. Retrieved passages and returned news analysis
are source evidence, not numerically verified financial claims.

Financial claims use `metric`, `source`, `scope`, `periodEnd`, `periodType`, `unit`,
`value`, `symbol`, and `statement`. Matching source/display decimal values and
all identity fields are required. Each invalid claim is rejected independently;
other sections and the authoritative financial table remain. Numeric/cited model
commentary is omitted locally, while valid qualitative commentary is explicitly
unverified. Arbitrary prose (including spelled-out numbers) is not fully verified.
Explicit requested metric names/aliases filter the facts in C#; revenue/net-profit
requests exclude expenses, EPS and other statement rows. Requests for general
financial statements without named metrics retain the broader statement view.

Tool traces can additionally have `incomplete` status, and completed analysis can
return response status `incomplete` when data or structured claims fail checks.
Availability diagnostics distinguish failed tools, empty data, missing requested
metrics, missing/invalid values and period-type mismatches. Request `period_type`
explicitly; mismatching rows are excluded with a diagnostic, never used as a
fallback. Missing fields remain missing rather than becoming zero.

### Validate a combined answer in PowerShell

After restarting the API with the changed code, this manual request uses the
configured model provider (a paid provider may incur a charge). It was not run
as part of automated validation. Use your local Ollama configuration for a local
model check. All four read-only tools must be enabled in both allowlists.

```powershell
$body = @{
    mode = 'long_term'
    message = 'For TCS, retrieve the latest available price snapshot, recent company news, consolidated ANNUAL revenue and net profit for the latest annual reporting period, and annual-report business risks with returned citations. Show only revenue and net_profit in the financial table. Keep separate Price, News, Financial facts, Annual-report evidence and Commentary sections. If a source is missing or fails, disclose it; missing news means unknown sentiment. Never substitute TTM for annual data.'
} | ConvertTo-Json
$result = Invoke-RestMethod -Uri 'http://localhost:8080/api/agent/chat' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 240
$result.answer
$result.status
$result.tools | Format-Table name, status
```
