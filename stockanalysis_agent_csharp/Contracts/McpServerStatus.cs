namespace StockAnalysis.Agent.Api.Contracts;

public enum McpConnectionState
{
    Disabled,
    Disconnected,
    Connecting,
    Connected,
    Degraded
}

public sealed record McpServerStatus(
    string ServerId,
    string Endpoint,
    bool Required,
    McpConnectionState State,
    int ToolCount,
    DateTimeOffset? LastAttemptAt,
    DateTimeOffset? LastConnectedAt,
    string? LastError);
