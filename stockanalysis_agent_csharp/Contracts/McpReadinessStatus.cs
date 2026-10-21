namespace StockAnalysis.Agent.Api.Contracts;

public sealed record McpReadinessStatus(
    bool IsReady,
    int ConnectedServers,
    int EnabledServers,
    IReadOnlyList<string> UnavailableRequiredServers);
