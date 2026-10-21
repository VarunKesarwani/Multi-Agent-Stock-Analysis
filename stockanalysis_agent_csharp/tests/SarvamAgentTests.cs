using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using ModelContextProtocol.Protocol;
using StockAnalysis.Agent.Api.Agent;
using StockAnalysis.Agent.Api.Contracts;
using StockAnalysis.Agent.Api.Services;

namespace StockAnalysis.Agent.Api.Tests;

public class SarvamAgentTests
{
    [Fact]
    public async Task V1ChatUsesBearerAuthenticationAndCompletionSchema()
    {
        var handler = new FakeHandler(TextReply("Hi"));
        var result = await Create(new FakeManager(), handler).RunAsync(new("Say hi in one word"), default);
        Assert.Equal("completed", result.Status);
        Assert.Equal("Bearer test-key", handler.Authorization);
        Assert.Equal("http://localhost/v1/chat/completions", handler.RequestUri);
        using var payload = JsonDocument.Parse(handler.Requests[0]);
        Assert.Equal("sarvam-105b", payload.RootElement.GetProperty("model").GetString());
        Assert.False(payload.RootElement.GetProperty("stream").GetBoolean());
        Assert.Equal(4096, payload.RootElement.GetProperty("max_tokens").GetInt32());
        Assert.False(payload.RootElement.TryGetProperty("options", out _));
    }

    [Fact]
    public async Task MissingKeyDoesNotSendARequest()
    {
        var handler = new FakeHandler(TextReply("Hi"));
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            Create(new FakeManager(), handler, apiKey: "").RunAsync(new("Hi"), default));
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task ToolLoopExecutesAllowedToolAndSendsToolCallId()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            ToolCall("call-1", "market__read"),
            TextReply("Evidence reviewed"));
        var result = await Create(manager, handler).RunAsync(new("Analyze TCS"), default);
        Assert.Equal(1, manager.Calls);
        Assert.Equal("completed", result.Status);
        Assert.Single(result.Tools);
        Assert.Equal("ok", result.Tools[0].Status);
        // OpenAI-compatible protocol: the tool result must carry the assistant call id.
        Assert.Contains("tool_call_id", handler.Requests[1]);
        Assert.Contains("call-1", handler.Requests[1]);
        // OpenAI-compatible request shape and allowlist.
        Assert.Contains("\"tool_choice\":\"auto\"", handler.Requests[0]);
        Assert.DoesNotContain("place_order", handler.Requests[0]);
    }

    [Fact]
    public async Task ModelCannotInvokeAnUnlistedTool()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            ToolCall("call-1", "kite__place_order"),
            TextReply("Unavailable"));
        var result = await Create(manager, handler).RunAsync(new("Place order"), default);
        Assert.Equal(0, manager.Calls);
        Assert.Equal("error", result.Tools[0].Status);
    }

    [Fact]
    public async Task TextProposalRetriesWithoutExecutingText()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            TextReply("{\"name\":\"market__read\",\"arguments\":{}}"),
            ToolCall("call-1", "market__read"),
            TextReply("Evidence reviewed"));
        var result = await Create(manager, handler).RunAsync(new("Analyze TCS"), default);
        Assert.Equal("completed", result.Status);
        Assert.Equal(1, manager.Calls);
        Assert.Equal(3, handler.Requests.Count);
        Assert.Contains("it was not executed", handler.Requests[1]);
    }

    private static string TextReply(string content) =>
        JsonSerializer.Serialize(new { choices = new[] { new { message = new { role = "assistant", content } } } });

    private static string ToolCall(string id, string name) =>
        JsonSerializer.Serialize(new
        {
            choices = new[]
            {
                new
                {
                    message = new
                    {
                        role = "assistant",
                        content = (string?)null,
                        tool_calls = new[]
                        {
                            new { id, type = "function", function = new { name, arguments = "{}" } }
                        }
                    }
                }
            }
        });

    private static SarvamAgent Create(FakeManager manager, FakeHandler handler, int rounds = 2, string apiKey = "test-key")
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../"));
        var policy = new AgentPolicy(new FakeEnvironment { ContentRootPath = root });
        return new(new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") }, manager, policy,
            Options.Create(new AgentOptions
            {
                Enabled = true,
                Provider = "sarvam",
                ApiKey = apiKey,
                Model = "sarvam-105b",
                MaxToolRounds = rounds,
                AllowedMcpTools = ["market__read", "financial__financial_get_statement"]
            }),
            NullLogger<SarvamAgent>.Instance);
    }

    [Fact]
    public async Task FinancialAnswerUsesCodeRenderedFactsInsteadOfModelDigits()
    {
        var manager = new FakeManager { ToolName = "financial__financial_get_statement", Output = JsonSerializer.Deserialize<JsonElement>(
            """{"status":"ok","query":{"scope":"CONSOLIDATED"},"data":[{"period_end":"2026-03-31","period_type":"ANNUAL","metrics":{"net_profit":{"value":"494540000000","unit":"INR"},"revenue":{"value":"2670210000000","unit":"INR"}}}]}""") };
        var handler = new FakeHandler(ToolCall("f1", "financial__financial_get_statement"), TextReply("Net profit is 4945400000000 INR"));
        var result = await Create(manager, handler).RunAsync(new("Analyze annual financials", "long_term"), default);
        Assert.Contains("49454 | INR_CRORE", result.Answer);
        Assert.Contains("267021 | INR_CRORE", result.Answer);
        Assert.DoesNotContain("4945400000000", result.Answer);
        Assert.Contains("authoritative financial facts", handler.Requests[1]);
    }

    private sealed class FakeHandler(params string[] responses) : HttpMessageHandler
    {
        private int index;
        public string? Authorization { get; private set; }
        public string? RequestUri { get; private set; }
        public List<string> Requests { get; } = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Authorization = request.Headers.Authorization?.ToString();
            RequestUri = request.RequestUri?.ToString();
            Requests.Add(await request.Content!.ReadAsStringAsync(ct));
            return new(HttpStatusCode.OK) { Content = new StringContent(responses[index++], Encoding.UTF8, "application/json") };
        }
    }

    private sealed class FakeEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = "Testing";
        public string ApplicationName { get; set; } = "Tests";
        public string ContentRootPath { get; set; } = "";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class FakeManager : IMcpClientManager
    {
        public int Calls { get; private set; }
        public object Output { get; set; } = "evidence";
        public string ToolName { get; set; } = "market__read";
        public Task<IReadOnlyList<AIFunction>> GetAgentFunctionsAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<AIFunction>>([AIFunctionFactory.Create(() => { Calls++; return Output; }, ToolName)]);
        public Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task RefreshServerAsync(string serverId, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task RefreshUnavailableServersAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<McpToolDescriptor>>([]);
        public Task<CallToolResult> InvokeToolAsync(string qualifiedName, IReadOnlyDictionary<string, object?>? arguments = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public IReadOnlyList<McpServerStatus> GetServerStatuses() => [];
        public McpReadinessStatus GetReadiness() => throw new NotSupportedException();
    }
}
