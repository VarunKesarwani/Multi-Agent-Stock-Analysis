# StockAnalysis Agent DevUI

A separate .NET 8 ASP.NET Core project hosting Microsoft's Agent Framework DevUI at http://127.0.0.1:8081/devui.

Browser → DevUI / OpenAI protocol adapter → existing agent on port 8080 → existing MCP client manager → market, financial, news, annual_reports and Kite.

There is one manager with five configured MCP connections, not five duplicate managers. The UI has no LLM keys, broker tokens or direct MCP connections. Existing tool allowlists, limits, deterministic analytics and instructions remain authoritative.

## Run from PowerShell

Start the existing agent in one terminal (replace the model with an installed tool-capable Ollama model):

```powershell
cd C:\Repo\StockAnalysis_AI
$env:Agent__Enabled = "true"
$env:Agent__Model = "<your-installed-model>"
dotnet run --project .\stockanalysis_agent_csharp\StockAnalysis.Agent.Api.csproj -- --urls http://127.0.0.1:8080
```

In another terminal:

```powershell
cd C:\Repo\StockAnalysis_AI
dotnet restore .\stockanalysis_devui_csharp\StockAnalysis.DevUI.csproj
dotnet run --project .\stockanalysis_devui_csharp\StockAnalysis.DevUI.csproj --launch-profile DevUI
```

Open http://127.0.0.1:8081/devui and select short_term, long_term, portfolio or tax. These map exactly to the backend mode field. For example, select short_term and ask for a momentum analysis of TCS with a 1–4 week horizon.

Optional backend origin override: `$env:AgentApi__BaseUrl = "http://127.0.0.1:8080/"`. Only loopback origins are accepted. Both services must run on the same machine.

## MCP readiness

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/mcp/servers
Invoke-RestMethod http://127.0.0.1:8080/health/ready
```

The backend currently enables market, financial, news and Kite; annual_reports is configured but disabled. Enable it in the backend only after its endpoint and tool names are verified. Kite authentication stays in the backend: ask the agent to use its allowed Kite login tool and open the returned broker login URL yourself. DevUI does not implement OAuth or store broker credentials.

## Behavior and limitations

- Each request is independent. The adapter forwards only the latest user message, matching the existing backend contract. Include symbols, dates, amounts and other necessary context in every request; visible chat history is not agent memory.
- Text only; attachments and non-user terminal messages are rejected.
- The agent backend returns a complete response. DevUI receives a single completed update, not live tokens or live MCP trace events.
- Answers include backend mode, status (including tool_limit), model, policy identity and tool names/statuses. Raw tool payloads are not exposed as DevUI tool events.
- Backend HTTP failures surface as errors without forwarding sensitive backend response bodies. Cancellation propagates to the backend HTTP request.
- DevUI requires no separate LLM configuration. It cannot answer unless the existing agent is enabled and its configured Ollama model is available.
- This is a single-user development UI, not an authenticated production frontend. All routes reject non-loopback callers and cross-origin browser requests. Conversation state is in memory and is lost on restart.
- Packages are pinned to the 1.20.0 release family (DevUI/Hosting preview.260831.1; Hosting.OpenAI alpha.260831.1). Upgrade the three hosting packages together after validation.

## Validation

```powershell
dotnet test .\stockanalysis_devui_csharp\tests\StockAnalysis.DevUI.Tests.csproj
dotnet test .\stockanalysis_agent_csharp\tests\StockAnalysis.Agent.Api.Tests.csproj
```

CI builds and runs the adapter tests with a fake HTTP backend. For a live smoke test, start the backend and DevUI, select each mode, submit a self-contained request and verify the response mode and audit footer. Verify unavailable backends show an error. No live broker request is part of automated tests.

Official reference: https://github.com/microsoft/agent-framework/tree/main/dotnet/src/Microsoft.Agents.AI.DevUI
