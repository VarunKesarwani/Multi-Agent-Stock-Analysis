using System.Globalization;
using System.Text.Json.Nodes;
using System.Text;

namespace StockAnalysis.Agent.Api.Analytics;

public sealed record FinancialFact(string Metric, string? RawValue, string? SourceUnit,
    decimal? DisplayValue, string? DisplayUnit, string Source, string? Scope,
    string? PeriodEnd, string? PeriodType, string? Symbol, string? Statement);
public sealed record FinancialClaim(string Metric, string Source, string? Scope, string? PeriodEnd,
    string? PeriodType, string? Unit, decimal Value, string? Symbol, string? Statement);
public sealed record FinancialIssue(string Tool, string Status, string? Metric = null);

/// <summary>Request-local financial evidence. No numeric inference or fallback periods.</summary>
public sealed class FinancialFacts(string? requestedPeriodType = null, IReadOnlySet<string>? requestedMetrics = null)
{
    public List<FinancialFact> Facts { get; } = [];
    public List<FinancialIssue> Issues { get; } = [];
    public bool Active { get; private set; }
    public const string ResponseInstruction = "For the financialFacts section return JSON with commentary (qualitative only, no numeric figures) and claims (array). Each claim must contain metric, source, scope, periodEnd, periodType, unit, value, symbol and statement matching the authoritative financial facts. Code renders all financial figures. Never substitute TTM for ANNUAL. Commentary is not numerically verified.";

    // Request intent only; this does not verify prose or numeric claims.
    public static string? RequestedPeriod(string message)
    {
        static bool Match(string text, string pattern) => System.Text.RegularExpressions.Regex.IsMatch(text, pattern,
            System.Text.RegularExpressions.RegexOptions.IgnoreCase | System.Text.RegularExpressions.RegexOptions.CultureInvariant);
        var annual = Match(message, @"\bannual\b(?![ -]+reports?\b)");
        var quarterly = Match(message, @"\bquarterly\b");
        var ttm = Match(message, @"\bTTM\b");
        // Annual-report retrieval is not itself a request for annual statement figures.
        if ((annual ? 1 : 0) + (quarterly ? 1 : 0) + (ttm ? 1 : 0) != 1) return null;
        return annual ? "ANNUAL" : quarterly ? "QUARTERLY" : "TTM";
    }

    public static decimal? Parse(string? raw) => decimal.TryParse(raw,
        NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint | NumberStyles.AllowExponent,
        CultureInfo.InvariantCulture, out var value) ? value : null;

    private static string? Text(JsonNode? node) => node is JsonValue v && v.TryGetValue<string>(out var s) ? s : node?.ToJsonString();

    public string Capture(string tool, string result, JsonObject? arguments, string status)
    {
        if (!tool.Contains("financial_get_statement", StringComparison.Ordinal) &&
            !tool.Contains("financial_get_current_facts", StringComparison.Ordinal) &&
            !tool.Contains("financial_compare_sources", StringComparison.Ordinal)) return status;
        Active = true;
        var issueStart = Issues.Count;
        var factStart = Facts.Count;
        if (status != "ok") { Issues.Add(new(tool, "failed")); return status; }
        try
        {
            JsonNode? root = JsonNode.Parse(result);
            if (root is JsonValue) root = JsonNode.Parse(Text(root)!);
            if (root?["isError"]?.GetValue<bool>() == true) { Issues.Add(new(tool, "failed")); return "error"; }
            if (root?["structuredContent"] is JsonObject structured) root = structured;
            else if (root?["content"] is JsonArray blocks)
            {
                var texts = blocks.Where(b => Text(b?["type"]) == "text").ToArray();
                if (texts.Length != 1) throw new FormatException();
                root = JsonNode.Parse(Text(texts[0]?["text"])!);
            }
            if (Text(root?["status"]) != "ok" || root?["error"] is not null)
            { Issues.Add(new(tool, "failed")); return "error"; }
            if (root?["data"] is not JsonArray rows) throw new FormatException();
            if (rows.Count == 0) Issues.Add(new(tool, "empty"));
            var query = root["query"];
            var start = Facts.Count;
            var wanted = requestedMetrics ?? (arguments?["metrics"] as JsonArray)?.Select(Text).OfType<string>().ToHashSet(StringComparer.Ordinal);
            foreach (var node in rows)
            {
                if (node is not JsonObject row) { Issues.Add(new(tool, "missing_data")); continue; }
                if (row["metrics"] is JsonObject { Count: 0 }) Issues.Add(new(tool, "missing_data"));
                void Add(string metric, JsonNode? value, JsonNode? unit, string? source)
                {
                    if (wanted is { Count: > 0 } && !wanted.Contains(metric)) return;
                    var raw = Text(value);
                    var sourceUnit = Text(unit);
                    var number = Parse(raw);
                    var inr = sourceUnit == "INR";
                    var fact = new FinancialFact(metric, raw, sourceUnit, inr ? number / 10000000m : number,
                        inr ? "INR_CRORE" : sourceUnit, source ?? "unknown", Text(row["scope"] ?? query?["scope"]),
                        Text(row["period_end"]), Text(row["period_type"]), Text(row["symbol"] ?? query?["symbol"]),
                        Text(row["statement"] ?? query?["statement"]));
                    var requested = requestedPeriodType ?? Text(arguments?["period_type"]);
                    if (requested is not null && requested != fact.PeriodType)
                    { Issues.Add(new(tool, "period_mismatch", metric)); return; }
                    Facts.Add(fact);
                    if (number is null) Issues.Add(new(tool, raw is null ? "missing_value" : "invalid_value", metric));
                }
                if (row["metrics"] is JsonObject metrics)
                    foreach (var metric in metrics) Add(metric.Key, metric.Value?["value"], metric.Value?["unit"], "SCREENER");
                else if (row["sources"] is JsonObject sources)
                    foreach (var source in sources) Add(Text(row["metric"]) ?? "unknown", source.Value, row["unit"], source.Key);
                else if (row["metric"] is not null)
                    Add(Text(row["metric"])!, row["value"], row["unit"], Text(row["source"] ?? query?["source"]));
                else if (row["metrics"] is null && row["sources"] is null) Issues.Add(new(tool, "missing_data"));
            }
            if (requestedMetrics is null && wanted is not null)
                foreach (var metric in wanted)
                    if (!Facts.Skip(start).Any(f => f.Metric == metric)) Issues.Add(new(tool, "missing_metric", metric));
            return Issues.Count > issueStart ? "incomplete" : "ok";
        }
        catch (Exception e) when (e is System.Text.Json.JsonException or InvalidOperationException or FormatException or ArgumentException)
        { Facts.RemoveRange(factStart, Facts.Count - factStart); Issues.Add(new(tool, "invalid_result")); return "error"; }
    }

    public bool Verify(FinancialClaim claim) => Facts.Any(f => f.Metric == claim.Metric && f.Source == claim.Source &&
        f.Scope == claim.Scope && f.PeriodEnd == claim.PeriodEnd && f.PeriodType == claim.PeriodType &&
        f.Symbol == claim.Symbol && f.Statement == claim.Statement &&
        ((f.DisplayUnit == claim.Unit && f.DisplayValue == claim.Value) ||
         (f.SourceUnit == claim.Unit && Parse(f.RawValue) == claim.Value)));

    public string Render(string content)
    {
        if (!Active) return content;
        var answer = new StringBuilder();
        if (requestedMetrics is not null)
            foreach (var metric in requestedMetrics)
                if (!Facts.Any(f => f.Metric == metric) && !Issues.Any(i => i.Status == "missing_metric" && i.Metric == metric))
                    Issues.Add(new("financial", "missing_metric", metric));
        // Accept only the structured response contract. Never label arbitrary prose verified.
        try
        {
            var response = JsonNode.Parse(content) as JsonObject;
            var commentary = Text(response?["commentary"]);
            if (commentary is not null && !commentary.Any(char.IsNumber))
                answer.AppendLine("Model commentary (unverified): " + commentary);
            if (response?["claims"] is JsonArray claims)
                foreach (var node in claims)
                {
                    // One malformed claim must not suppress later claims or independent sections.
                    try
                    {
                        var value = Parse(Text(node?["value"]));
                        var claim = new FinancialClaim(Text(node?["metric"]) ?? "", Text(node?["source"]) ?? "",
                            Text(node?["scope"]), Text(node?["periodEnd"]), Text(node?["periodType"]),
                            Text(node?["unit"]), value ?? 0, Text(node?["symbol"]), Text(node?["statement"]));
                        if (value is not null && Verify(claim)) continue;
                        Issues.Add(new("model", "claim_mismatch", claim.Metric));
                    }
                    catch (InvalidOperationException) { Issues.Add(new("model", "invalid_claim")); }
                    answer.AppendLine("Rejected financial claim; use the authoritative facts below.");
                }
        }
        catch (Exception e) when (e is System.Text.Json.JsonException or InvalidOperationException)
        { answer.AppendLine("Financial commentary unavailable; financial figures are rendered from tool facts."); }
        answer.AppendLine("Authoritative financial facts:");
        answer.AppendLine("| Metric | Raw value | Source unit | Display value | Display unit | Source | Scope | Period | Type | Symbol | Statement |");
        answer.AppendLine("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |");
        static string Cell(string? s) => (s ?? "missing").Replace("|", "\\|").Replace("\r", " ").Replace("\n", " ");
        foreach (var f in Facts.OrderBy(f => f.Symbol, StringComparer.Ordinal)
            .ThenBy(f => f.Statement, StringComparer.Ordinal).ThenBy(f => f.PeriodEnd, StringComparer.Ordinal)
            .ThenBy(f => f.PeriodType, StringComparer.Ordinal).ThenBy(f => f.Scope, StringComparer.Ordinal)
            .ThenBy(f => f.Source, StringComparer.Ordinal).ThenBy(f => f.Metric, StringComparer.Ordinal))
            answer.AppendLine("| " + string.Join(" | ", new[] { f.Metric, f.RawValue, f.SourceUnit,
                f.DisplayValue?.ToString(CultureInfo.InvariantCulture), f.DisplayUnit, f.Source, f.Scope,
                f.PeriodEnd, f.PeriodType, f.Symbol, f.Statement }.Select(Cell)) + " |");
        foreach (var issue in Issues) answer.AppendLine($"Data availability: {Cell(issue.Tool)}: {issue.Status} ({Cell(issue.Metric)}).");
        return answer.ToString();
    }
}
