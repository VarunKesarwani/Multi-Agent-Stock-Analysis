using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using StockAnalysis.Agent.Api.Analytics;
using StockAnalysis.Agent.Api.Services;

namespace StockAnalysis.Agent.Api.Agent;

/// <summary>Bounded Ollama tool-calling loop over the existing manager's policy wrappers.</summary>
public sealed class OllamaAgent(HttpClient http, IMcpClientManager manager, AgentPolicy policy,
    IOptions<AgentOptions> options, ILogger<OllamaAgent> logger)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    /// <summary>Runs isolated request history; never accepts caller-supplied system or tool messages.</summary>
    public async Task<AgentResponse> RunAsync(AgentRequest request, CancellationToken cancellationToken)
    {
        var settings = options.Value;
        if (!settings.Enabled) throw new InvalidOperationException("Agent is disabled. Configure Agent__Enabled and Agent__Model.");
        if (string.IsNullOrWhiteSpace(request.Message) || request.Message.Length > settings.MaxMessageCharacters || !AgentPolicy.Modes.Contains(request.Mode))
            throw new ArgumentException("Provide a bounded message and mode short_term, long_term, portfolio or tax.");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(settings.TimeoutSeconds));
        var functions = (await manager.GetAgentFunctionsAsync(timeout.Token))
            .Where(x => settings.AllowedMcpTools.Contains(x.Name, StringComparer.Ordinal)).ToList();
        if (request.Mode == "portfolio")
        {
            functions.Add(AIFunctionFactory.Create((Func<CagrRequest, object>)PortfolioAnalytics.Cagr,
                "portfolio_cagr", "Compute CAGR only for confirmed no-external-cash-flow investment; never invent inputs."));
            functions.Add(AIFunctionFactory.Create((Func<PerformanceRequest, object>)PortfolioAnalytics.Performance,
                "portfolio_performance", "Compute Sharpe, volatility, TWR and drawdown from supplied regular adjusted net total returns; never invent inputs."));
            functions.Add(AIFunctionFactory.Create((Func<XirrRequest, object>)PortfolioAnalytics.Xirr,
                "portfolio_xirr", "Compute investor XIRR from actual conventional dated cash flows including terminal value."));
        }
        if (request.Mode == "tax") functions.Add(AIFunctionFactory.Create((Func<TaxScenarioRequest, object>)TaxScenario.Estimate,
            "tax_scenario", "Arithmetic scenario only, using user-supplied verified rates and reconciled taxable gains; no default tax rates."));
        var byName = functions.ToDictionary(f => f.Name, StringComparer.Ordinal);
        var tools = functions.Select(f => new { type = "function", function = new { name = f.Name, description = f.Description, parameters = f.JsonSchema } }).ToArray();
        var messages = new List<JsonNode>
        {
            new JsonObject { ["role"] = "system", ["content"] = policy.ForMode(request.Mode) },
            new JsonObject { ["role"] = "user", ["content"] = request.Message }
        };
        var trace = new List<AgentToolTrace>();
        var combined = new CombinedResponse(request.Message);
        var retriedTextProposal = false;
        var awaitingStructuredCall = false;
        var round = 0;
        while (true)
        {
            if (combined.Active) messages.Add(new JsonObject { ["role"] = "system",
                ["content"] = CombinedResponse.Instruction + "\nAuthoritative financial facts: " + JsonSerializer.Serialize(combined.Financial.Facts, Json) + "\nCaptured evidence: " + JsonSerializer.Serialize(combined.Evidence, Json) });
            using var response = await http.PostAsJsonAsync("api/chat", new
            {
                model = settings.Model, stream = false, messages, tools,
                options = new { temperature = 0 }
            }, Json, timeout.Token);
            response.EnsureSuccessStatusCode();
            var body = await response.Content.ReadFromJsonAsync<JsonObject>(Json, timeout.Token)
                ?? throw new InvalidOperationException("Ollama returned an empty response.");
            var message = body["message"] as JsonObject ?? throw new InvalidOperationException("Ollama returned no message.");
            messages.Add(message.DeepClone());
            var calls = message["tool_calls"] as JsonArray;
            if (calls is null || calls.Count == 0)
            {
                var content = message["content"]?.GetValue<string>() ?? "";
                if (awaitingStructuredCall || ContainsToolProposal(content))
                {
                    if (retriedTextProposal)
                        return new AgentResponse(combined.Render("The model did not produce a structured tool call. Analysis is incomplete; check the configured model's tool-calling support."),
                            request.Mode, settings.Model, policy.Version, trace, "tool_call_failed");
                    retriedTextProposal = true;
                    awaitingStructuredCall = true;
                    messages.Add(new JsonObject
                    {
                        ["role"] = "system",
                        ["content"] = "Your previous response described a tool call as text; it was not executed. Use the supplied tool-calling interface and return message.tool_calls with function.name and function.arguments. Do not print tool-call JSON in message.content. Only call available tools under the current policy."
                    });
                    continue;
                }
                return new AgentResponse(combined.Render(content), request.Mode,
                    settings.Model, policy.Version, trace, combined.Incomplete ? "incomplete" : "completed");
            }
            awaitingStructuredCall = false;
            if (round == settings.MaxToolRounds || trace.Count + calls.Count > settings.MaxToolCalls)
                return new AgentResponse(combined.Render("Analysis stopped at the configured tool limit. Narrow the request; no complete conclusion was produced."),
                    request.Mode, settings.Model, policy.Version, trace, "tool_limit");
            round++;
            foreach (var call in calls)
            {
                var name = call?["function"]?["name"]?.GetValue<string>() ?? "";
                string result;
                var status = "ok";
                JsonObject? raw = null;
                try
                {
                    if (!byName.TryGetValue(name, out var function)) throw new ArgumentException("Tool is not available under the current policy.");
                    raw = call?["function"]?["arguments"] as JsonObject ?? throw new ArgumentException("Tool arguments must be an object.");
                    var arguments = JsonSerializer.Deserialize<Dictionary<string, object?>>(raw.ToJsonString(), Json)!;
                    var output = await function.InvokeAsync(new AIFunctionArguments(arguments), timeout.Token);
                    result = JsonSerializer.Serialize(output, Json);
                    if (output is ModelContextProtocol.Protocol.CallToolResult mcp && mcp.IsError == true) status = "error";
                    if (result.Length > settings.MaxToolResultCharacters)
                    {
                        result = "{\"error\":\"Tool result too large; request fewer records. No partial result supplied.\"}";
                        status = "error";
                    }
                }
                catch (OperationCanceledException) when (timeout.IsCancellationRequested) { throw; }
                catch (Exception exception)
                {
                    status = "error";
                    // Avoid credentials, raw arguments and backend errors in logs or model context.
                    logger.LogWarning("Agent tool {ToolName} failed with {ErrorType}", name, exception.GetType().Name);
                    result = JsonSerializer.Serialize(new { error = exception is ArgumentException ? exception.Message : "Tool unavailable or invalid input; do not infer missing data." }, Json);
                }
                status = combined.Capture(name, result, raw, status);
                trace.Add(new AgentToolTrace(name, status));
                messages.Add(new JsonObject { ["role"] = "tool", ["tool_name"] = name, ["content"] = result });
            }
        }
    }

    // Inspect JSON objects embedded in prose, fences or adjacent proposals. Text is never executed.
    private static bool ContainsToolProposal(string content)
    {
        for (var index = 0; index < content.Length; index++)
        {
            if (content[index] != '{') continue;
            try
            {
                var reader = new Utf8JsonReader(System.Text.Encoding.UTF8.GetBytes(content[index..]));
                if (JsonDocument.TryParseValue(ref reader, out var document))
                {
                    using (document)
                    {
                        var root = document!.RootElement;
                        if (root.TryGetProperty("tool_calls", out var calls) &&
                            calls.ValueKind == JsonValueKind.Array && calls.GetArrayLength() > 0)
                            return true;
                        if (root.TryGetProperty("name", out var name) &&
                            name.ValueKind == JsonValueKind.String &&
                            root.TryGetProperty("arguments", out _))
                            return true;
                    }
                }
            }
            catch (JsonException) { /* Ordinary prose or malformed JSON is not a parsed proposal. */ }
        }
        return false;
    }
}
