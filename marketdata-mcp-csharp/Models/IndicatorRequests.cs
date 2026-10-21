namespace MarketDataMcpServer.Models;

public sealed record CalculateIndicatorRequest(
    string Symbol,
    string Indicator,
    int Period = 14,
    int Limit = 250);

public sealed record McpToolCallRequest(
    string Name,
    Dictionary<string, object?> Arguments);

public sealed record IndicatorRequest(
    string Name,
    int? Period = null);

public sealed record CalculateIndicatorsRequest(
    string Symbol,
    IReadOnlyList<IndicatorRequest> Indicators,
    string Timeframe = "daily",
    int Limit = 250);