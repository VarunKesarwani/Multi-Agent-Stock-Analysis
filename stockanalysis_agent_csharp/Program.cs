using StockAnalysis.Agent.Api.Agent;
using StockAnalysis.Agent.Api.Analytics;
using Microsoft.Extensions.Options;
using StockAnalysis.Agent.Api.Configuration;
using StockAnalysis.Agent.Api.Contracts;
using StockAnalysis.Agent.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services
    .AddOptions<McpClientManagerOptions>()
    .Bind(builder.Configuration.GetSection(McpClientManagerOptions.SectionName))
    .ValidateOnStart();
builder.Services.AddSingleton<IValidateOptions<McpClientManagerOptions>, McpClientManagerOptionsValidator>();

builder.Services.AddHttpClient(McpClientManager.HttpClientName, client =>
{
    client.Timeout = Timeout.InfiniteTimeSpan;
});
builder.Services.AddSingleton<IMcpClientManager, McpClientManager>();
builder.Services.AddHostedService<McpClientWarmupService>();
builder.Services.AddHostedService<McpReconnectService>();

builder.Services.AddOptions<AgentOptions>()
    .Bind(builder.Configuration.GetSection(AgentOptions.SectionName))
    .Validate(o => Uri.TryCreate(o.Endpoint, UriKind.Absolute, out var uri) &&
        (uri.Scheme == "http" || uri.Scheme == "https"), "Agent endpoint must be an absolute HTTP(S) URL.")
    .Validate(o => o.Provider is "ollama" or "sarvam", "Agent:Provider must be 'ollama' or 'sarvam'.")
    .Validate(o => !o.Enabled || !string.IsNullOrWhiteSpace(o.Model), "Configure Agent:Model when enabling the agent.")
    .Validate(o => !o.Enabled || o.Provider != "sarvam" || !string.IsNullOrWhiteSpace(o.ApiKey), "Configure Agent:ApiKey for the Sarvam provider.")
    .Validate(o => o.TimeoutSeconds is >= 1 and <= 600 && o.MaxToolRounds is >= 1 and <= 12 &&
        o.MaxToolCalls is >= 1 and <= 50 && o.MaxMessageCharacters is >= 1 and <= 50000 &&
        o.MaxToolResultCharacters is >= 100 and <= 100000 && o.MaxCompletionTokens is >= 1 and <= 100000 &&
        o.AllowedMcpTools is not null,
        "Invalid agent limits.").ValidateOnStart();
builder.Services.AddSingleton<AgentPolicy>();

// Local Ollama provider (native /api/chat).
builder.Services.AddHttpClient<OllamaAgent>((services, client) =>
{
    var settings = services.GetRequiredService<IOptions<AgentOptions>>().Value;
    client.BaseAddress = new Uri(settings.Endpoint.TrimEnd('/') + "/");
    client.Timeout = Timeout.InfiniteTimeSpan;
});

// Sarvam AI provider (OpenAI-compatible chat completions).
builder.Services.AddHttpClient<SarvamAgent>((services, client) =>
{
    var settings = services.GetRequiredService<IOptions<AgentOptions>>().Value;
    client.BaseAddress = new Uri(settings.Endpoint.TrimEnd('/') + "/");
    client.Timeout = Timeout.InfiniteTimeSpan;
});

var app = builder.Build();
_ = app.Services.GetRequiredService<AgentPolicy>();

app.MapPost("/api/agent/chat", async (AgentRequest request, IOptions<AgentOptions> options,
    OllamaAgent ollama, SarvamAgent sarvam, CancellationToken ct) =>
{
    try
    {
        var response = options.Value.Provider == "sarvam"
            ? await sarvam.RunAsync(request, ct)
            : await ollama.RunAsync(request, ct);
        return Results.Ok(response);
    }
    catch (ArgumentException ex) { return Results.BadRequest(new { error = ex.Message }); }
    catch (OperationCanceledException) when (!ct.IsCancellationRequested)
    { return Results.Problem("Agent request timed out.", statusCode: 504); }
    catch (HttpRequestException) { return Results.Problem("Model provider unavailable; check the configured endpoint, key and model.", statusCode: 502); }
    catch (InvalidOperationException) { return Results.Problem("Agent unavailable; check configuration and model response.", statusCode: 503); }
    catch (System.Text.Json.JsonException) { return Results.Problem("Invalid model response.", statusCode: 502); }
});

// Deterministic endpoints also permit direct validation without running an LLM.
app.MapPost("/api/analytics/cagr", (CagrRequest request) => Calculate(() => PortfolioAnalytics.Cagr(request)));
app.MapPost("/api/analytics/performance", (PerformanceRequest request) => Calculate(() => PortfolioAnalytics.Performance(request)));
app.MapPost("/api/analytics/xirr", (XirrRequest request) => Calculate(() => PortfolioAnalytics.Xirr(request)));
app.MapPost("/api/analytics/tax-scenario", (TaxScenarioRequest request) => Calculate(() => TaxScenario.Estimate(request)));


app.MapGet("/health", () => Results.Ok(new
{
    status = "ok",
    service = "stockanalysis-agent-api"
}));

app.MapGet("/health/ready", (IMcpClientManager manager) =>
{
    var readiness = manager.GetReadiness();
    return readiness.IsReady
        ? Results.Ok(readiness)
        : Results.Json(readiness, statusCode: StatusCodes.Status503ServiceUnavailable);
});

app.MapGet("/api/mcp/servers", (IMcpClientManager manager) =>
    Results.Ok(manager.GetServerStatuses()));

app.MapGet("/api/mcp/tools", async (IMcpClientManager manager, CancellationToken cancellationToken) =>
    Results.Ok(await manager.ListToolsAsync(cancellationToken)));

app.MapPost(
    "/api/mcp/servers/{serverId}/refresh",
    async (string serverId, IMcpClientManager manager, CancellationToken cancellationToken) =>
    {
        try
        {
            await manager.RefreshServerAsync(serverId, cancellationToken);
            var status = manager.GetServerStatuses()
                .Single(item => string.Equals(item.ServerId, serverId, StringComparison.OrdinalIgnoreCase));
            return Results.Ok(status);
        }
        catch (KeyNotFoundException exception)
        {
            return Results.NotFound(new { error = exception.Message });
        }
    });

app.MapPost(
    "/api/mcp/tools/{qualifiedName}/invoke",
    async (string qualifiedName, InvokeToolRequest request, IMcpClientManager manager, CancellationToken cancellationToken) =>
    {
        try
        {
            var result = await manager.InvokeToolAsync(
                qualifiedName,
                request.ToArguments(),
                cancellationToken);
            return Results.Ok(result);
        }
        catch (KeyNotFoundException exception)
        {
            return Results.NotFound(new { error = exception.Message });
        }
        catch (TimeoutException exception)
        {
            return Results.Problem(exception.Message, statusCode: StatusCodes.Status504GatewayTimeout);
        }
    });

app.Run();

static IResult Calculate(Func<object> calculate)
{
    try { return Results.Ok(calculate()); }
    catch (ArgumentException ex) { return Results.BadRequest(new { error = ex.Message }); }
    catch (OverflowException) { return Results.BadRequest(new { error = "Inputs exceed supported numeric range." }); }
}

public partial class Program;
