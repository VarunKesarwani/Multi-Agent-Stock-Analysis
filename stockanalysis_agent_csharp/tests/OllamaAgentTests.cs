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

public class OllamaAgentTests
{
    [Fact]
    public async Task ToolLoopInvokesOnlyAllowedFunctionsAndReturnsTrace()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            """{"message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"market__read","arguments":{}}}]}}""",
            """{"message":{"role":"assistant","content":"Evidence reviewed"}}""");
        var result = await Create(manager, handler).RunAsync(new("Analyze TCS"), default);
        Assert.Equal(1, manager.Calls);
        Assert.Equal("completed", result.Status);
        Assert.Single(result.Tools);
        Assert.Equal("ok", result.Tools[0].Status);
        Assert.Contains("tool_name", handler.Requests[1]);
        Assert.DoesNotContain("place_order", handler.Requests[0]);
    }

    [Fact]
    public async Task ModelCannotInvokeAnUnlistedTool()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            """{"message":{"role":"assistant","tool_calls":[{"function":{"name":"kite__place_order","arguments":{}}}]}}""",
            """{"message":{"role":"assistant","content":"Unavailable"}}""");
        var result = await Create(manager, handler).RunAsync(new("Place order"), default);
        Assert.Equal(0, manager.Calls);
        Assert.Equal("error", result.Tools[0].Status);
    }

    [Fact]
    public async Task ToolRoundsAreBounded()
    {
        const string call = """{"message":{"role":"assistant","tool_calls":[{"function":{"name":"market__read","arguments":{}}}]}}""";
        var manager = new FakeManager();
        var result = await Create(manager, new FakeHandler(call, call), 1).RunAsync(new("Analyze"), default);
        Assert.Equal("tool_limit", result.Status);
        Assert.Equal(1, manager.Calls);
    }

    [Fact]
    public async Task PortfolioToolUsesTypedArgumentsAndDeterministicCalculator()
    {
        var handler = new FakeHandler(
            """{"message":{"role":"assistant","tool_calls":[{"function":{"name":"portfolio_cagr","arguments":{"request":{"startValue":100,"endValue":110,"start":"2025-01-01","end":"2026-01-01","hasExternalCashFlows":false}}}}]}}""",
            """{"message":{"role":"assistant","content":"Calculated"}}""");
        var result = await Create(new FakeManager(), handler).RunAsync(new("Calculate supplied growth", "portfolio"), default);
        Assert.Equal("ok", result.Tools[0].Status);
        Assert.Contains("cagr", handler.Requests[1]);
    }


    [Fact]
    public async Task ExactTcsTextProposalRetriesWithoutExecutingText()
    {
        const string proposal = """{"name": "market__calculate_indicators", "arguments": {"symbol": "TCS", "indicators": [{"name": "rsi", "period": 14}], "limit": 250}}""";
        var manager = new FakeManager();
        var handler = new FakeHandler(TextReply(proposal),
            """{"message":{"role":"assistant","tool_calls":[{"function":{"name":"market__read","arguments":{}}}]}}""",
            TextReply("Evidence reviewed"));
        // One repair request must not consume the configured single tool round.
        var result = await Create(manager, handler, 1).RunAsync(new("Analyze TCS"), default);
        Assert.Equal("completed", result.Status);
        Assert.Equal(1, manager.Calls);
        Assert.Single(result.Tools);
        Assert.Equal("ok", result.Tools[0].Status);
        Assert.Equal(3, handler.Requests.Count);
        Assert.Contains("it was not executed", handler.Requests[1]);
    }

    [Theory]
    [InlineData("{\"name\":\"market__read\",\"arguments\":{}}")]
    [InlineData("Call this:\n```json\n{\"name\":\"market__read\",\"arguments\":{}}\n```")]
    [InlineData("[{\"name\":\"market__read\",\"arguments\":{}}]")]
    [InlineData("{\"name\":\"market__read\",\"arguments\":{}}\n{\"name\":\"news__read\",\"arguments\":{}}")]
    [InlineData("{\"function\":{\"name\":\"market__read\",\"arguments\":{}}}")]
    [InlineData("{\"tool_calls\":[{\"function\":{\"name\":\"market__read\",\"arguments\":{}}}]}")]
    public async Task RepeatedTextProposalsFailAfterOneRetry(string proposal)
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(TextReply(proposal), TextReply(proposal));
        var result = await Create(manager, handler).RunAsync(new("Analyze TCS"), default);
        Assert.Equal("tool_call_failed", result.Status);
        Assert.Empty(result.Tools);
        Assert.Equal(0, manager.Calls);
        Assert.Equal(2, handler.Requests.Count);
        Assert.DoesNotContain(proposal, result.Answer);
    }

    [Fact]
    public async Task RetryCannotClaimCompletionWithoutStructuredCall()
    {
        var handler = new FakeHandler(
            TextReply("""{"name":"market__read","arguments":{}}"""),
            TextReply("RSI is 65; analysis complete."));
        var result = await Create(new FakeManager(), handler).RunAsync(new("Analyze"), default);
        Assert.Equal("tool_call_failed", result.Status);
        Assert.Empty(result.Tools);
        Assert.DoesNotContain("65", result.Answer);
    }

    [Theory]
    [InlineData("Please provide the observation dates.")]
    [InlineData("{\"name\":\"TCS\",\"price\":100}")]
    public async Task OrdinaryAnswersDoNotRetry(string answer)
    {
        var handler = new FakeHandler(TextReply(answer));
        var result = await Create(new FakeManager(), handler).RunAsync(new("Explain inputs"), default);
        Assert.Equal("completed", result.Status);
        Assert.Equal(answer, result.Answer);
        Assert.Empty(result.Tools);
        Assert.Single(handler.Requests);
    }

    [Fact]
    public async Task RepairPreservesAllowlist()
    {
        var manager = new FakeManager();
        var handler = new FakeHandler(
            TextReply("""{"name":"kite__place_order","arguments":{}}"""),
            """{"message":{"role":"assistant","tool_calls":[{"function":{"name":"kite__place_order","arguments":{}}}]}}""",
            TextReply("Unavailable"));
        var result = await Create(manager, handler).RunAsync(new("Analyze"), default);
        Assert.Equal(0, manager.Calls);
        Assert.Single(result.Tools);
        Assert.Equal("error", result.Tools[0].Status);
    }

    private static string TextReply(string content) =>
        JsonSerializer.Serialize(new { message = new { role = "assistant", content } });

    private static OllamaAgent Create(FakeManager manager, FakeHandler handler, int rounds = 2)
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../"));
        var policy = new AgentPolicy(new FakeEnvironment { ContentRootPath = root });
        return new(new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") }, manager, policy,
            Options.Create(new AgentOptions { Enabled = true, Model = "test", MaxToolRounds = rounds, AllowedMcpTools = ["market__read", "financial__financial_get_statement"] }),
            NullLogger<OllamaAgent>.Instance);
    }

    [Fact]
    public async Task FinancialAnswerUsesCodeRenderedFactsInsteadOfModelDigits()
    {
        var manager = new FakeManager { ToolName = "financial__financial_get_statement", Output = JsonSerializer.Deserialize<JsonElement>(
            """{"status":"ok","query":{"scope":"CONSOLIDATED"},"data":[{"period_end":"2026-03-31","period_type":"ANNUAL","metrics":{"net_profit":{"value":"494540000000","unit":"INR"},"revenue":{"value":"2670210000000","unit":"INR"}}}]}""") };
        var handler = new FakeHandler("""{"message":{"role":"assistant","tool_calls":[{"function":{"name":"financial__financial_get_statement","arguments":{}}}]}}""", """{"message":{"role":"assistant","content":"Net profit is 4945400000000 INR"}}""");
        var result = await Create(manager, handler).RunAsync(new("Analyze annual financials", "long_term"), default);
        Assert.Contains("49454 | INR_CRORE", result.Answer);
        Assert.Contains("267021 | INR_CRORE", result.Answer);
        Assert.DoesNotContain("4945400000000", result.Answer);
        Assert.Contains("authoritative financial facts", handler.Requests[1]);
    }

    private sealed class FakeHandler(params string[] responses) : HttpMessageHandler
    {
        private int index;
        public List<string> Requests { get; } = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
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
