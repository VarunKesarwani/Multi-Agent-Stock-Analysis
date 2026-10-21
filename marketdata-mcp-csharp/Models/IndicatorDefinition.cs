namespace MarketDataMcpServer.Models;

public sealed record IndicatorDefinition(
    string Name,
    string ToolName,
    string Category,
    string Description,
    int DefaultPeriod,
    bool PythonSupported);