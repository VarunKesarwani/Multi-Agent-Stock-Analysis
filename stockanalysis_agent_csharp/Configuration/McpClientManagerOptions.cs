namespace StockAnalysis.Agent.Api.Configuration;

public sealed class McpClientManagerOptions
{
    public const string SectionName = "McpClientManager";

    public int InitializationTimeoutSeconds { get; init; } = 30;

    public int ToolCallTimeoutSeconds { get; init; } = 60;

    public int ReconnectIntervalSeconds { get; init; } = 30;

    public int MaxParallelConnections { get; init; } = 4;

    public List<McpServerOptions> Servers { get; init; } = [];
}

public sealed class McpServerOptions
{
    public required string Id { get; init; }

    public required string Endpoint { get; init; }

    public bool Enabled { get; init; } = true;

    public bool Required { get; init; } = true;

    public List<string> AllowedTools { get; init; } = [];

    public Dictionary<string, string> Headers { get; init; } = new(StringComparer.OrdinalIgnoreCase);
}
