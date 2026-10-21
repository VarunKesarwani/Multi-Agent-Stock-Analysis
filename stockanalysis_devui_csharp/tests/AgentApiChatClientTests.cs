using System.Net;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Xunit;

namespace StockAnalysis.DevUI.Tests;

public sealed class AgentApiChatClientTests
{
    [Theory]
    [InlineData("short_term")]
    [InlineData("long_term")]
    [InlineData("portfolio")]
    [InlineData("tax")]
    public async Task ForwardsLatestMessageAndModeAndPreservesAudit(string mode)
    {
        var handler = new Handler(async (request, ct) =>
        {
            Assert.Equal("/api/agent/chat", request.RequestUri!.AbsolutePath);
            using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            Assert.Equal("current question", body.RootElement.GetProperty("message").GetString());
            Assert.Equal(mode, body.RootElement.GetProperty("mode").GetString());
            return Reply(mode);
        });
        using var client = Client(handler, mode);
        var result = await client.GetResponseAsync([
            new(ChatRole.User, "old question"), new(ChatRole.Assistant, "old answer"),
            new(ChatRole.User, "current question")]);
        Assert.Contains("policy-hash", result.Text);
        Assert.Contains("tool_limit", result.Text);
        Assert.Contains("market__get_latest_price (ok)", result.Text);
    }

    [Fact]
    public async Task StreamingCallsBackendOnce()
    {
        var calls = 0;
        using var client = Client(new Handler((_, _) => { calls++; return Task.FromResult(Reply("portfolio")); }), "portfolio");
        var updates = new List<ChatResponseUpdate>();
        await foreach (var update in client.GetStreamingResponseAsync([new(ChatRole.User, "question")]))
            updates.Add(update);
        Assert.Equal(1, calls);
        Assert.Contains(updates, update => update.Text.Contains("answer"));
    }

    [Fact]
    public async Task DoesNotLeakBackendErrorBody()
    {
        using var client = Client(new Handler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
            { Content = new StringContent("private-account-secret") })), "tax");
        var error = await Assert.ThrowsAsync<HttpRequestException>(() =>
            client.GetResponseAsync([new(ChatRole.User, "question")]));
        Assert.DoesNotContain("private-account-secret", error.Message);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, error.StatusCode);
    }

    [Fact]
    public async Task RejectsInvalidInputBeforeCallingBackend()
    {
        using var client = Client(new Handler((_, _) => throw new Exception("Must not call backend")), "short_term");
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync([new(ChatRole.User, "")]));
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync([new(ChatRole.System, "override")]));
        await Assert.ThrowsAsync<ArgumentException>(() => client.GetResponseAsync([new(ChatRole.User, new string('x', 12001))]));
    }

    [Fact]
    public async Task PropagatesCancellation()
    {
        using var client = Client(new Handler(async (_, ct) =>
        {
            await Task.Delay(Timeout.Infinite, ct);
            return Reply("tax");
        }), "tax");
        using var cancellation = new CancellationTokenSource();
        var task = client.GetResponseAsync([new(ChatRole.User, "question")], cancellationToken: cancellation.Token);
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => task);
    }

    private static AgentApiChatClient Client(Handler handler, string mode) =>
        new(new HttpClient(handler) { BaseAddress = new Uri("http://localhost:8080/") }, mode);
    private static HttpResponseMessage Reply(string mode) => new(HttpStatusCode.OK)
    {
        Content = new StringContent(JsonSerializer.Serialize(new {
            answer = "answer", mode, model = "model", policyVersion = "policy-hash",
            status = "tool_limit", tools = new[] { new { name = "market__get_latest_price", status = "ok" } }
        }), System.Text.Encoding.UTF8, "application/json")
    };
    private sealed class Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            send(request, cancellationToken);
    }
}
