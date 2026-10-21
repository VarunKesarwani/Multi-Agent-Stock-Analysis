using System.Text.Json;

namespace StockAnalysis.Agent.Api.Contracts;

public sealed record McpToolDescriptor(
    string QualifiedName,
    string ServerId,
    string OriginalName,
    string? Title,
    string Description,
    JsonElement InputSchema);

