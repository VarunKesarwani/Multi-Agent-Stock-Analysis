namespace MarketDataMcpServer.Models;

public sealed record OhlcvCandle(
    DateTime Date,
    decimal? Open,
    decimal? High,
    decimal? Low,
    decimal? Close,
    long? Volume,
    string? CompanyId = null);