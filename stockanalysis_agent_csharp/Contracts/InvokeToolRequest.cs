using System.Text.Json;

namespace StockAnalysis.Agent.Api.Contracts;

public sealed record InvokeToolRequest(Dictionary<string, JsonElement>? Arguments)
{
    public IReadOnlyDictionary<string, object?> ToArguments()
    {
        if (Arguments is null)
        {
            return new Dictionary<string, object?>();
        }

        return Arguments.ToDictionary(
            pair => pair.Key,
            pair => JsonSerializer.Deserialize<object?>(pair.Value.GetRawText()));
    }
}

