using System.Net.Http.Json;
using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;

namespace StockAnalysis.DevUI;

/// <summary>Protocol adapter only. The remote agent owns inference, policy and all MCP calls.</summary>
public sealed class AgentApiChatClient(HttpClient http, string mode) : IChatClient
{
    private static readonly HashSet<string> Modes = ["short_term", "long_term", "portfolio", "tax"];

    public async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages,
        ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        if (!Modes.Contains(mode)) throw new ArgumentException("Unsupported analysis mode.");
        var latest = messages.LastOrDefault();
        if (latest is null || latest.Role != ChatRole.User ||
            latest.Contents.Any(content => content is not TextContent) ||
            string.IsNullOrWhiteSpace(latest.Text) || latest.Text.Length > 12000)
            throw new ArgumentException("Send a text-only user message of 1–12000 characters. Include all context in each request.");

        using var response = await http.PostAsJsonAsync("api/agent/chat",
            new { message = latest.Text, mode }, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException(
                $"Agent API returned HTTP {(int)response.StatusCode}. Check backend availability, Agent__Enabled and Agent__Model.",
                null, response.StatusCode);
        var result = await response.Content.ReadFromJsonAsync<AgentReply>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Agent API returned no response.");
        if (result.Answer is null || result.Mode != mode || string.IsNullOrWhiteSpace(result.Status))
            throw new InvalidOperationException("Agent API returned an invalid response contract.");

        var trace = string.Join(", ", (result.Tools ?? []).Select(tool => $"{tool.Name} ({tool.Status})"));
        var text = $"{result.Answer}\n\n---\nMode: {result.Mode} | Status: {result.Status}\nModel: {result.Model}\nPolicy: {result.PolicyVersion}\nTools attempted: {(trace.Length == 0 ? "none" : trace)}";
        return new ChatResponse(new ChatMessage(ChatRole.Assistant, text))
        {
            ResponseId = Guid.NewGuid().ToString("N"),
            ModelId = result.Model,
            FinishReason = ChatFinishReason.Stop
        };
    }

    // The backend is non-streaming. Emit one completed update; do not simulate token streaming.
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var response = await GetResponseAsync(messages, options, cancellationToken);
        foreach (var update in response.ToChatResponseUpdates())
            yield return update;
    }

    public object? GetService(Type serviceType, object? serviceKey = null)
    {
        ArgumentNullException.ThrowIfNull(serviceType);
        return serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;
    }

    public void Dispose() => http.Dispose();

    private sealed record ToolTrace(string Name, string Status);
    private sealed record AgentReply(string? Answer, string Mode, string Model,
        string PolicyVersion, ToolTrace[]? Tools, string Status);
}
