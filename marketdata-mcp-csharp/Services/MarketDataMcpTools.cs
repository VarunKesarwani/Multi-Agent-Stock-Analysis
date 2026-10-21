using System.ComponentModel;
using MarketDataMcpServer.Models;
using ModelContextProtocol.Server;

namespace MarketDataMcpServer.Services;

[McpServerToolType]
public sealed class MarketDataMcpTools
{
    private readonly IndicatorCatalog _indicatorCatalog;
    private readonly MarketDataService _marketDataService;
    private readonly PythonIndicatorService _pythonIndicatorService;

    public MarketDataMcpTools(
        IndicatorCatalog indicatorCatalog,
        MarketDataService marketDataService,
        PythonIndicatorService pythonIndicatorService)
    {
        _indicatorCatalog = indicatorCatalog;
        _marketDataService = marketDataService;
        _pythonIndicatorService = pythonIndicatorService;
    }

    [McpServerTool(Name = "list_available_indicators", ReadOnly = true, Idempotent = true)]
    [Description("List the 35 supported technical indicators, categories, descriptions, and default periods.")]
    public object ListAvailableIndicators()
    {
        return new { indicators = _indicatorCatalog.GetAll() };
    }

    [McpServerTool(Name = "get_latest_price", ReadOnly = true, Idempotent = true)]
    [Description("Get the latest available OHLCV snapshot for one stock symbol.")]
    public async Task<object?> GetLatestPrice(string symbol, CancellationToken cancellationToken = default)
    {
        return await _marketDataService.GetLatestEquitySnapshotAsync(NormalizeSymbol(symbol), cancellationToken);
    }

    [McpServerTool(Name = "get_historical_prices", ReadOnly = true, Idempotent = true)]
    [Description("Get bounded daily OHLCV history for one stock symbol.")]
    public async Task<object> GetHistoricalPrices(
        string symbol,
        int limit = 250,
        CancellationToken cancellationToken = default)
    {
        return new
        {
            symbol = NormalizeSymbol(symbol),
            timeframe = "daily",
            candles = await _marketDataService.GetOhlcvHistoryAsync(
                NormalizeSymbol(symbol), NormalizeLimit(limit), cancellationToken)
        };
    }

    [McpServerTool(Name = "calculate_indicators", ReadOnly = true, Idempotent = true)]
    [Description("Calculate one or more of the supported technical indicators using PostgreSQL OHLCV data and the Python indicator runner.")]
    public async Task<object> CalculateIndicators(
        string symbol,
        IReadOnlyList<IndicatorRequest> indicators,
        string timeframe = "daily",
        int limit = 250,
        CancellationToken cancellationToken = default)
    {
        var normalizedSymbol = NormalizeSymbol(symbol);
        var normalizedLimit = NormalizeLimit(limit);
        if (!string.Equals(timeframe, "daily", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("Only the daily timeframe is currently supported.", nameof(timeframe));
        }

        if (indicators is null || indicators.Count == 0)
        {
            throw new ArgumentException("At least one indicator is required.", nameof(indicators));
        }

        var results = new List<object>();
        foreach (var requested in indicators)
        {
            var definition = _indicatorCatalog.FindByIndicatorOrToolName(requested.Name)
                ?? throw new ArgumentException($"Unknown indicator '{requested.Name}'.", nameof(indicators));
            var period = requested.Period ?? definition.DefaultPeriod;
            if (period <= 0 || period > normalizedLimit)
            {
                throw new ArgumentException($"Period for '{definition.Name}' must be greater than zero and no greater than the candle limit.", nameof(indicators));
            }

            results.Add(await _pythonIndicatorService.CalculateAsync(
                definition.Name, normalizedSymbol, period, normalizedLimit, cancellationToken));
        }

        return new
        {
            symbol = normalizedSymbol,
            timeframe = "daily",
            results
        };
    }

    private static string NormalizeSymbol(string symbol)
    {
        if (string.IsNullOrWhiteSpace(symbol))
        {
            throw new ArgumentException("Symbol is required.", nameof(symbol));
        }

        return symbol.Trim().ToUpperInvariant();
    }

    private static int NormalizeLimit(int limit)
    {
        return limit is > 0 and <= 5000
            ? limit
            : throw new ArgumentException("Limit must be between 1 and 5000.", nameof(limit));
    }
}