using MarketDataMcpServer.Services;
using MarketDataMcpServer.Models;
using System.Text.Json;

var useStdio = args.Any(argument => string.Equals(argument, "--stdio", StringComparison.OrdinalIgnoreCase));

if (useStdio)
{
    await RunStdioAsync(args);
    return;
}

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();
ConfigureCoreServices(builder.Services, builder.Configuration);
builder.Services.AddMcpServer()
    .WithHttpTransport()
    .WithToolsFromAssembly();

var app = builder.Build();

app.UseSwagger();
app.UseSwaggerUI();
app.MapMcp("/mcp");

app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "marketdata-mcp-csharp" }));

app.MapGet("/mcp/tools", () => Results.Ok(new
{
    server = "marketdata-mcp-csharp",
    tools = GetToolList(app.Services.GetRequiredService<IndicatorCatalog>())
}));

app.MapGet("/mcp/indicators", (IndicatorCatalog indicatorCatalog) => Results.Ok(indicatorCatalog.GetAll()));

app.MapPost("/mcp/indicators/calculate", async (
    CalculateIndicatorRequest request,
    PythonIndicatorService indicatorService,
    CancellationToken cancellationToken) =>
{
    try
    {
        var result = await indicatorService.CalculateAsync(
            request.Indicator,
            request.Symbol,
            request.Period,
            request.Limit,
            cancellationToken);
        return Results.Ok(result);
    }
    catch (ArgumentException ex)
    {
        return Results.BadRequest(new { message = ex.Message });
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.MapPost("/mcp/call", async (
    McpToolCallRequest request,
    IndicatorCatalog indicatorCatalog,
    PythonIndicatorService indicatorService,
    CancellationToken cancellationToken) =>
{
    try
    {
        if (string.Equals(request.Name, "list_available_indicators", StringComparison.OrdinalIgnoreCase))
        {
            return Results.Ok(indicatorCatalog.GetAll());
        }

        var indicator = indicatorCatalog.FindByIndicatorOrToolName(request.Name);
        if (indicator is null)
        {
            return Results.BadRequest(new { message = $"Unknown MCP tool '{request.Name}'." });
        }

        var symbol = GetStringArgument(request.Arguments, "symbol");
        if (string.IsNullOrWhiteSpace(symbol))
        {
            return Results.BadRequest(new { message = "Argument 'symbol' is required." });
        }

        var period = GetIntArgument(request.Arguments, "period", indicator.DefaultPeriod);
        var limit = GetIntArgument(request.Arguments, "limit", 250);
        var result = await indicatorService.CalculateAsync(indicator.Name, symbol, period, limit, cancellationToken);
        return Results.Ok(result);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.MapGet("/api/company/{symbol}", async (string symbol, MarketDataService marketDataService) =>
{
    try
    {
        var company = await marketDataService.GetCompanyAsync(symbol);
        return company is null ? Results.NotFound(new { message = $"Company '{symbol}' not found" }) : Results.Ok(company);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 500);
    }
});

app.MapGet("/api/equity/history/{symbol}", async (string symbol, int? limit, MarketDataService marketDataService) =>
{
    try
    {
        var history = await marketDataService.GetEquityHistoryAsync(symbol, limit ?? 100);
        return Results.Ok(history);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 500);
    }
});

app.MapGet("/api/fo/history/{symbol}", async (string symbol, int? limit, MarketDataService marketDataService) =>
{
    try
    {
        var history = await marketDataService.GetFoHistoryAsync(symbol, limit ?? 100);
        return Results.Ok(history);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 500);
    }
});

app.MapGet("/api/latest/{symbol}", async (string symbol, MarketDataService marketDataService) =>
{
    try
    {
        var snapshot = await marketDataService.GetLatestEquitySnapshotAsync(symbol);
        return snapshot is null ? Results.NotFound(new { message = $"Snapshot for '{symbol}' not found" }) : Results.Ok(snapshot);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 500);
    }
});

app.MapGet("/api/price/{symbol}", async (string symbol, PriceMovementProxyService priceMovementService) =>
{
    try
    {
        var result = await priceMovementService.GetLatestPriceAsync(symbol);
        return Results.Ok(result);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.MapGet("/api/ohlc/{symbol}", async (string symbol, int? limit, PriceMovementProxyService priceMovementService) =>
{
    try
    {
        var result = await priceMovementService.GetOhlcHistoryAsync(symbol, limit ?? 100);
        return Results.Ok(result);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.MapGet("/api/indicator/{indicator}/{symbol}", async (
    string indicator,
    string symbol,
    int? period,
    int? limit,
    PythonIndicatorService indicatorService,
    CancellationToken cancellationToken) =>
{
    try
    {
        var result = await indicatorService.CalculateAsync(indicator, symbol, period ?? 14, limit ?? 250, cancellationToken);
        return Results.Ok(result);
    }
    catch (Exception ex)
    {
        return Results.Problem(ex.Message, statusCode: 502);
    }
});

app.Run();

static object[] GetToolList(IndicatorCatalog indicatorCatalog)
{
    var marketDataTools = new object[]
    {
        new { name = "get_company", category = "company" },
        new { name = "search_company", category = "company" },
        new { name = "get_equity_history", category = "equity" },
        new { name = "get_latest_snapshot", category = "equity" },
        new { name = "get_top_volume", category = "equity" },
        new { name = "get_fo_history", category = "fo" },
        new { name = "get_open_interest", category = "fo" },
        new { name = "get_expiry_chain", category = "fo" },
        new { name = "list_available_indicators", category = "indicator" }
    };

    return marketDataTools
        .Concat(indicatorCatalog.GetAll().Select(indicator => new
        {
            name = indicator.ToolName,
            category = indicator.Category,
            indicator = indicator.Name,
            pythonSupported = indicator.PythonSupported
        }))
        .Cast<object>()
        .ToArray();
}

static string? GetStringArgument(Dictionary<string, object?> arguments, string name)
{
    if (!arguments.TryGetValue(name, out var value) || value is null)
    {
        return null;
    }

    return value is JsonElement element ? element.GetString() : value.ToString();
}

static int GetIntArgument(Dictionary<string, object?> arguments, string name, int defaultValue)
{
    if (!arguments.TryGetValue(name, out var value) || value is null)
    {
        return defaultValue;
    }

    if (value is JsonElement element)
    {
        return element.ValueKind == JsonValueKind.Number && element.TryGetInt32(out var number)
            ? number
            : defaultValue;
    }

    return int.TryParse(value.ToString(), out var parsed) ? parsed : defaultValue;
}

static void ConfigureCoreServices(IServiceCollection services, IConfiguration configuration)
{
    var connectionString = configuration.GetConnectionString("DefaultConnection")
        ?? Environment.GetEnvironmentVariable("PG_CONNECTION_STRING")
        ?? "Host=localhost;Port=5432;Database=StockAnalysis_Bhavcopy;Username=postgres;Password=postgres";

    services.AddSingleton<MarketDataService>(_ => new MarketDataService(connectionString));
    services.AddSingleton<IndicatorCatalog>();
    services.AddSingleton<PythonIndicatorService>();
    services.AddHttpClient<PriceMovementProxyService>(client =>
    {
        var priceServiceBaseUrl = configuration["PriceMovementService:BaseUrl"]
            ?? Environment.GetEnvironmentVariable("PRICE_MOVEMENT_SERVICE_URL")
            ?? "http://localhost:5260";

        client.BaseAddress = new Uri(priceServiceBaseUrl);
    });
}

static async Task RunStdioAsync(string[] args)
{
    var builder = Host.CreateApplicationBuilder(args);
    builder.Logging.ClearProviders();
    builder.Logging.AddConsole(options => options.LogToStandardErrorThreshold = LogLevel.Trace);
    ConfigureCoreServices(builder.Services, builder.Configuration);
    builder.Services.AddMcpServer()
        .WithStdioServerTransport()
        .WithToolsFromAssembly();

    using var host = builder.Build();
    await host.RunAsync();
}
