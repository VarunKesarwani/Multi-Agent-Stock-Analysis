using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
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

public class CombinedResponseTests
{
    private const string Request = "TCS latest price, news, annual revenue and net profit, and annual-report risks with citations";
    private const string Financial = """{"status":"ok","query":{"symbol":"TCS","scope":"CONSOLIDATED","statement":"profit_loss"},"data":[{"period_end":"2026-03-31","period_type":"ANNUAL","metrics":{"revenue":{"value":"2670210000000","unit":"INR"},"net_profit":{"value":"494540000000","unit":"INR"},"expenses":{"value":"1230000000","unit":"INR"},"eps":{"value":"123.45","unit":"INR_PER_SHARE"}}}]}""";
    private const string Price = """{"symbol":"TCS","close_price":"3210.25","date1":"2026-10-05","currency":"INR"}""";
    private const string News = """{"status":"ok","data":{"total":1,"items":[{"title":"TCS announces customer deal","summary":"A new customer deal was announced.","source":"Exchange filing","published_at":"2026-10-05","link":"https://example.test/news/tcs"}]}}""";
    private const string Rag = """{"status":"ok","data":[{"text":"Customer concentration is a business risk.","citation":{"id":"tcs.pdf#chunk-7","source_file":"tcs.pdf","page":42,"section":"Risks"},"metadata":{"page":42}}]}""";
    private const string Good = """{"price":{"evidenceIds":["e1"]},"news":{"evidenceIds":["e2"]},"annualReport":{"evidenceIds":["e3"]},"financialFacts":{"claims":[],"commentary":"Profitability remains positive."},"commentary":"Consider the cited risks alongside reported results."}""";
    private const string Bad = """{"price":{"evidenceIds":["e1"]},"news":{"evidenceIds":["e2"]},"annualReport":{"evidenceIds":["e3"]},"financialFacts":{"claims":[{"metric":"net_profit","source":"SCREENER","scope":"CONSOLIDATED","periodEnd":"2026-03-31","periodType":"ANNUAL","unit":"INR_CRORE","value":"494540","symbol":"TCS","statement":"profit_loss"}],"commentary":"Net profit is 494540 crore."}}""";
    private static readonly Dictionary<string, string> Outputs = new()
    {
        ["market__get_latest_price"] = Price,
        ["news__news_get_company_news"] = News,
        ["financial__financial_get_statement"] = Financial,
        ["annual_reports__reports_search_annual_report"] = Rag
    };

    private static CombinedResponse CaptureAll()
    {
        var combined = new CombinedResponse(Request);
        foreach (var output in Outputs) Assert.Equal("ok", combined.Capture(output.Key, output.Value, new(), "ok"));
        return combined;
    }

    private static void AssertAll(string answer)
    {
        Assert.Contains("Price", answer);
        Assert.Contains("3210.25", answer);
        Assert.Contains("TCS announces customer deal", answer);
        Assert.Contains("https://example.test/news/tcs", answer);
        Assert.Contains("267021 | INR_CRORE", answer);
        Assert.Contains("49454 | INR_CRORE", answer);
        Assert.Contains("Customer concentration", answer);
        Assert.Contains("tcs.pdf#chunk-7", answer);
        Assert.Contains("\"page\":42", answer);
        Assert.DoesNotContain("| expenses |", answer);
        Assert.DoesNotContain("| eps |", answer);
    }

    [Theory]
    [InlineData(Good, false)]
    [InlineData(Bad, true)]
    [InlineData("Malformed model prose", true)]
    [InlineData("", true)]
    [InlineData("{}", true)]
    [InlineData("[]", true)]
    [InlineData("{\"unrelated\":\"value\"}", true)]
    public void AllGroupsSurviveIndependentFinancialFailuresAndFallbacks(string content, bool incomplete)
    {
        var combined = CaptureAll();
        var answer = combined.Render(content);
        AssertAll(answer);
        Assert.Equal(incomplete, combined.Incomplete);
        Assert.DoesNotContain("494540 crore", answer);
        if (content == Bad) Assert.Contains("Rejected financial claim", answer);
    }

    [Fact]
    public void EmptyNewsAndFailedRagAreExplicitAndDoNotEraseOtherSections()
    {
        var combined = new CombinedResponse(Request);
        combined.Capture("market__get_latest_price", Price, new(), "ok");
        combined.Capture("financial__financial_get_statement", Financial, new(), "ok");
        Assert.Equal("incomplete", combined.Capture("news__news_get_company_news", """{"status":"ok","data":{"items":[]}}""", new(), "ok"));
        Assert.Equal("error", combined.Capture("annual_reports__reports_search_annual_report", "{}", new(), "error"));
        var answer = combined.Render("malformed");
        Assert.Contains("sentiment unknown", answer);
        Assert.DoesNotContain("neutral", answer);
        Assert.Contains("news: empty_result", answer);
        Assert.Contains("annualReport: tool_error", answer);
        Assert.Contains("3210.25", answer);
        Assert.Contains("49454 | INR_CRORE", answer);
        Assert.True(combined.Incomplete);
    }

    [Fact]
    public void UnknownReferencesCannotInventPriceNewsOrCitations()
    {
        var combined = CaptureAll();
        var model = JsonNode.Parse(Good)!.AsObject();
        model["annualReport"] = JsonNode.Parse("""{"evidenceIds":["invented.pdf#page-999"]}""");
        var answer = combined.Render(model.ToJsonString());
        AssertAll(answer);
        Assert.DoesNotContain("999", answer);
        Assert.Contains("unknown_evidence_reference", answer);
    }

    [Fact]
    public void MissingCitationDoesNotInventPageOrSource()
    {
        var combined = new CombinedResponse("annual-report risks");
        combined.Capture("annual_reports__reports_search_annual_report", """{"status":"ok","data":[{"text":"Business risk","metadata":{}}]}""", new(), "ok");
        var answer = combined.Render("""{"annualReport":{"evidenceIds":["e1"]}}""");
        Assert.Contains("Citation metadata missing", answer);
        Assert.DoesNotContain("42", answer);
    }

    [Fact]
    public void MalformedAndScopeMismatchedClaimsAreLocal()
    {
        var combined = new CombinedResponse("TCS price news annual revenue net profit EPS annual-report risks");
        foreach (var output in Outputs) combined.Capture(output.Key, output.Value, new(), "ok");
        var model = JsonNode.Parse(Good)!.AsObject();
        model["financialFacts"] = JsonNode.Parse("""{"claims":[17,{"metric":"net_profit","source":"SCREENER","scope":"STANDALONE","periodEnd":"2026-03-31","periodType":"ANNUAL","unit":"INR_CRORE","value":"49454","symbol":"TCS","statement":"profit_loss"}]}""");
        var answer = combined.Render(model.ToJsonString());
        Assert.Contains("3210.25", answer);
        Assert.Contains("Customer concentration", answer);
        Assert.Contains("Rejected financial claim", answer);
        Assert.Contains("| eps |", answer);
        Assert.DoesNotContain("| expenses |", answer);
    }

    [Theory]
    [InlineData("quarterly revenue and annual-report risks", "QUARTERLY")]
    [InlineData("TTM revenue and annual report risks", "TTM")]
    [InlineData("annual revenue and annual-report risks", "ANNUAL")]
    [InlineData("annual and quarterly revenue", null)]
    public void ReportingPeriodIntentIsSeparateFromRagIntent(string request, string? expected)
    {
        Assert.Equal(expected, StockAnalysis.Agent.Api.Analytics.FinancialFacts.RequestedPeriod(request));
    }

    [Fact]
    public void MissingRequestedMetricIsDisclosedWithoutDumpingOtherMetrics()
    {
        var combined = new CombinedResponse("TCS annual revenue net profit");
        var envelope = JsonNode.Parse(Financial)!.AsObject();
        envelope["data"]![0]!["metrics"]!.AsObject().Remove("net_profit");
        combined.Capture("financial__financial_get_statement", envelope.ToJsonString(), new(), "ok");
        var answer = combined.Render("""{"financialFacts":{"claims":[]}}""");
        Assert.Contains("267021 | INR_CRORE", answer);
        Assert.Contains("missing_metric (net_profit)", answer);
        Assert.DoesNotContain("| expenses |", answer);
        Assert.DoesNotContain("| eps |", answer);
        Assert.True(combined.Incomplete);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void AllToolGroupsSupportMcpTextAndStructuredContent(bool structured)
    {
        var combined = new CombinedResponse(Request);
        foreach (var output in Outputs)
        {
            var envelope = new JsonObject { ["content"] = new JsonArray(new JsonObject { ["type"] = "text", ["text"] = output.Value }) };
            if (structured) envelope["structuredContent"] = JsonNode.Parse(output.Value);
            Assert.Equal("ok", combined.Capture(output.Key, envelope.ToJsonString(), new(), "ok"));
        }
        AssertAll(combined.Render(Good));
        Assert.False(combined.Incomplete);
    }

    [Fact]
    public void McpErrorFlagAndMissingPriceAreNotSuccessfulEvidence()
    {
        var combined = new CombinedResponse("price annual-report risks");
        Assert.Equal("error", combined.Capture("annual_reports__reports_search_annual_report", """{"isError":true,"content":[{"type":"text","text":"not evidence"}]}""", new(), "ok"));
        Assert.Equal("incomplete", combined.Capture("market__get_latest_price", "null", new(), "ok"));
        var answer = combined.Render("{}");
        Assert.Contains("annualReport: tool_error", answer);
        Assert.Contains("price: empty_result", answer);
        Assert.True(combined.Incomplete);
    }

    [Fact]
    public void MetadataOnlyCitationUsesReturnedLocatorAndMissingPageStaysMissing()
    {
        var combined = new CombinedResponse("annual-report risks");
        combined.Capture("annual_reports__reports_search_annual_report", """{"status":"ok","data":[{"text":"A business risk.","metadata":{"source_pdf":"actual.pdf","section":"Governance"}}]}""", new(), "ok");
        var answer = combined.Render("""{"annualReport":{"evidenceIds":["e1"]}}""");
        Assert.Contains("actual.pdf", answer);
        Assert.Contains("Governance", answer);
        Assert.DoesNotContain("\"page\"", answer);
        Assert.False(combined.Incomplete);
    }

    [Fact]
    public void NoToolsAndEmptyModelNeverCompleteSuccessfully()
    {
        var combined = new CombinedResponse("Hello");
        Assert.Contains("Analysis is incomplete", combined.Render(""));
        Assert.True(combined.Incomplete);
        var missing = new CombinedResponse("price news revenue annual-report");
        Assert.Contains("missing_data", missing.Render("{}"));
        Assert.True(missing.Incomplete);
    }

    [Theory]
    [InlineData("sarvam", Good, "completed")]
    [InlineData("ollama", Good, "completed")]
    [InlineData("sarvam", Bad, "incomplete")]
    [InlineData("ollama", Bad, "incomplete")]
    [InlineData("sarvam", "Malformed model prose", "incomplete")]
    [InlineData("ollama", "", "incomplete")]
    public async Task BothAgentPipelinesRenderAllFourToolGroups(string provider, string content, string status)
    {
        var calls = Outputs.Keys.Select((name, i) => new JsonObject
        {
            ["id"] = $"call-{i}", ["type"] = "function",
            ["function"] = new JsonObject { ["name"] = name, ["arguments"] = provider == "sarvam" ? JsonValue.Create("{}") : new JsonObject() }
        }).ToArray();
        var first = new JsonObject { ["role"] = "assistant", ["content"] = "", ["tool_calls"] = new JsonArray(calls) };
        var last = new JsonObject { ["role"] = "assistant", ["content"] = content };
        static string Wrap(JsonObject message, string provider) => provider == "sarvam"
            ? new JsonObject { ["choices"] = new JsonArray(new JsonObject { ["message"] = message }) }.ToJsonString()
            : new JsonObject { ["message"] = message }.ToJsonString();
        var handler = new Handler(Wrap(first, provider), Wrap(last, provider));
        var http = new HttpClient(handler) { BaseAddress = new Uri("http://localhost/") };
        var manager = new Manager();
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../"));
        var policy = new AgentPolicy(new Environment { ContentRootPath = root });
        var settings = Options.Create(new AgentOptions { Enabled = true, ApiKey = "fake", Model = "test", AllowedMcpTools = Outputs.Keys.ToArray() });
        var response = provider == "sarvam"
            ? await new SarvamAgent(http, manager, policy, settings, NullLogger<SarvamAgent>.Instance).RunAsync(new(Request, "long_term"), default)
            : await new OllamaAgent(http, manager, policy, settings, NullLogger<OllamaAgent>.Instance).RunAsync(new(Request, "long_term"), default);
        AssertAll(response.Answer);
        Assert.Equal(status, response.Status);
        Assert.Equal(4, response.Tools.Count);
        Assert.All(response.Tools, tool => Assert.Equal("ok", tool.Status));
    }

    private sealed class Handler(params string[] responses) : HttpMessageHandler
    {
        private int index;
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct) =>
            Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(responses[index++], Encoding.UTF8, "application/json") });
    }
    private sealed class Environment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = "Testing";
        public string ApplicationName { get; set; } = "Tests";
        public string ContentRootPath { get; set; } = "";
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
    private sealed class Manager : IMcpClientManager
    {
        public Task<IReadOnlyList<AIFunction>> GetAgentFunctionsAsync(CancellationToken cancellationToken = default) =>
            Task.FromResult<IReadOnlyList<AIFunction>>(Outputs.Select(output => AIFunctionFactory.Create(() => JsonSerializer.Deserialize<JsonElement>(output.Value), output.Key)).ToArray());
        public Task InitializeAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task RefreshServerAsync(string serverId, CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task RefreshUnavailableServersAsync(CancellationToken cancellationToken = default) => Task.CompletedTask;
        public Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken = default) => Task.FromResult<IReadOnlyList<McpToolDescriptor>>([]);
        public Task<CallToolResult> InvokeToolAsync(string qualifiedName, IReadOnlyDictionary<string, object?>? arguments = null, CancellationToken cancellationToken = default) => throw new NotSupportedException();
        public IReadOnlyList<McpServerStatus> GetServerStatuses() => [];
        public McpReadinessStatus GetReadiness() => throw new NotSupportedException();
    }
}
