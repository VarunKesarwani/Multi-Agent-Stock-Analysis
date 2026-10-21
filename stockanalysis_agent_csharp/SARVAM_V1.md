# Sarvam Chat Completions V1

The existing SarvamAgent uses HttpClient (no RestSharp dependency), POST
https://api.sarvam.ai/v1/chat/completions, Bearer authentication, and the
OpenAI-compatible messages / choices / tool_calls schema. MCP allowlists, bounded
tool execution, deterministic portfolio analytics and read-only broker access stay in place.

Official references:
- https://docs.sarvam.ai/api-reference/chat/chat-completions-v1
- https://docs.sarvam.ai/api-reference/authentication

## Configure locally with .NET user secrets

Use user secrets for the API key during local development. They keep the key outside
the repository, but are not encrypted. Use environment variables or a managed secret
store for deployment. Keep only non-secret settings in appsettings.json.
ASP.NET Core does not automatically load .env files.

Run in PowerShell:

```powershell
cd C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp
$env:ASPNETCORE_ENVIRONMENT = 'Development'
$env:Agent__Enabled = 'true'
$env:Agent__Provider = 'sarvam'
$env:Agent__Endpoint = 'https://api.sarvam.ai/'
$env:Agent__ChatPath = 'v1/chat/completions'
$env:Agent__Model = 'sarvam-105b'

# Prompt without printing the key or placing it in command history.
$key = Read-Host 'Sarvam API key' -AsSecureString
$credential = [System.Net.NetworkCredential]::new('', $key)
@{ 'Agent:ApiKey' = $credential.Password } | ConvertTo-Json -Compress | dotnet user-secrets set
Remove-Variable key, credential

# Remove an old environment override, if present; it takes precedence over user secrets.
Remove-Item Env:Agent__ApiKey -ErrorAction SilentlyContinue

dotnet restore
dotnet test .\tests\StockAnalysis.Agent.Api.Tests.csproj
dotnet run --urls http://localhost:8080
```

Alternatively set Agent__ApiKey in the process environment. User secrets load
automatically only in Development. The UserSecretsId is already included in the project;
dotnet user-secrets init is unnecessary. Never paste the key into logs, chat or committed files.

## Validate basic chat, then MCP tools

In a second terminal:

```powershell
$body = @{ mode = 'short_term'; message = 'Say hi in one word. Do not call tools.' } | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/api/agent/chat -Method Post -ContentType 'application/json' -Body $body

Invoke-RestMethod http://localhost:8080/api/mcp/servers
Invoke-RestMethod http://localhost:8080/api/mcp/tools

$body = @{
    mode = 'short_term'
    message = 'Analyze TCS for a 1 to 4 week momentum trade. Use available tools to check EMA 5/13/21/55, MACD, RSI, volume and latest news. Identify missing data.'
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8080/api/agent/chat -Method Post -ContentType 'application/json' -Body $body
```

Confirm status=completed, model=sarvam-105b and successful entries in tools for
analysis that requires data. A completed basic chat does not validate MCP connectivity.
Missing required MCP servers make readiness return 503 but do not prevent basic chat.

A 502 model-provider error can indicate an invalid key, model, endpoint, credit/quota
issue or an upstream failure; inspect the account dashboard without exposing the key.
A 503 agent error can indicate disabled configuration or an invalid response.
V1 does not require V2 beta access. No paid live API call is made by the unit tests.

## Automated validation

SarvamAgentTests exercises the V1 request path, Bearer header, model and token fields,
missing-key rejection, the structured tool loop including tool_call_id, allowlist enforcement,
and recovery from tool JSON returned as text. Tests use an in-memory HTTP handler.
