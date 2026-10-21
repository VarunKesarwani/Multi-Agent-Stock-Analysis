using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using StockAnalysis.Agent.Api.Analytics;

namespace StockAnalysis.Agent.Api.Tests;

public class FinancialFactsTests
{
    private const string Tool = "financial__financial_get_statement";
    private static string Statement(string? value = "494540000000", string? unit = "INR", string period = "ANNUAL") =>
        JsonSerializer.Serialize(new { status = "ok", query = new { symbol = "TCS", scope = "CONSOLIDATED", statement = "profit_loss" },
            data = new[] { new { period_end = "2026-03-31", period_type = period,
                metrics = new { net_profit = new { value, unit }, revenue = new { value = "2670210000000", unit = "INR" } } } } });

    [Fact]
    public void ObservedTenfoldErrorIsRejectedAndCorrectFactsRendered()
    {
        var facts = new FinancialFacts();
        Assert.Equal("ok", facts.Capture(Tool, Statement(), null, "ok"));
        Assert.Equal(49454m, facts.Facts[0].DisplayValue);
        Assert.Equal(267021m, facts.Facts[1].DisplayValue);
        Assert.Equal("494540000000", facts.Facts[0].RawValue);
        var claim = new FinancialClaim("net_profit", "SCREENER", "CONSOLIDATED", "2026-03-31", "ANNUAL", "INR", 4945400000000m, "TCS", "profit_loss");
        Assert.False(facts.Verify(claim));
        Assert.True(facts.Verify(claim with { Value = 494540000000m }));
        Assert.True(facts.Verify(claim with { Value = 49454m, Unit = "INR_CRORE" }));
        var answer = facts.Render(JsonSerializer.Serialize(new { commentary = "Profitability is positive.", claims = new[] { claim } }, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        Assert.Contains("Rejected financial claim", answer);
        Assert.Contains("49454", answer);
        Assert.DoesNotContain("4945400000000", answer);
        Assert.DoesNotContain("4945400000000", facts.Render("Net profit is 4945400000000"));
    }

    [Theory]
    [InlineData("INR", "1.25")]
    [InlineData("INR_PER_SHARE", "12500000")]
    [InlineData("PERCENT", "12500000")]
    [InlineData("DAYS", "12500000")]
    [InlineData("INR_CRORE", "12500000")]
    [InlineData("unknown", "12500000")]
    [InlineData(null, "12500000")]
    public void ConversionRequiresExplicitInr(string? unit, string expected)
    {
        var facts = new FinancialFacts();
        facts.Capture(Tool, Statement("12500000", unit), null, "ok");
        Assert.Equal(FinancialFacts.Parse(expected), facts.Facts[0].DisplayValue);
        Assert.Equal(unit, facts.Facts[0].SourceUnit);
    }

    [Fact]
    public void DecimalParsingIsInvariantAndExact()
    {
        var previous = CultureInfo.CurrentCulture;
        try
        {
            CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
            Assert.Equal(12345678901234567890.12345678m, FinancialFacts.Parse("12345678901234567890.12345678"));
            Assert.Equal(-12.5m, FinancialFacts.Parse("-1.25e1"));
            Assert.Null(FinancialFacts.Parse("1,25"));
            Assert.Null(FinancialFacts.Parse("NaN"));
            Assert.Null(FinancialFacts.Parse("1e100"));
        }
        finally { CultureInfo.CurrentCulture = previous; }
    }

    [Theory]
    [InlineData(null, "missing_value")]
    [InlineData("", "invalid_value")]
    [InlineData("not available", "invalid_value")]
    public void MissingValuesAreNotZero(string? raw, string status)
    {
        var facts = new FinancialFacts();
        Assert.Equal("incomplete", facts.Capture(Tool, Statement(raw), null, "ok"));
        Assert.Null(facts.Facts[0].DisplayValue);
        Assert.Contains(facts.Issues, i => i.Status == status);
    }

    [Fact]
    public void AnnualRequestDoesNotAcceptTtmAndClaimsRequireAllDimensions()
    {
        var facts = new FinancialFacts();
        Assert.Equal("incomplete", facts.Capture(Tool, Statement(period: "TTM"), JsonNode.Parse("{\"period_type\":\"ANNUAL\"}")!.AsObject(), "ok"));
        Assert.Empty(facts.Facts);
        facts.Capture(Tool, Statement(), null, "ok");
        var claim = new FinancialClaim("net_profit", "SCREENER", "CONSOLIDATED", "2026-03-31", "ANNUAL", "INR_CRORE", 49454m, "TCS", "profit_loss");
        Assert.True(facts.Verify(claim));
        Assert.False(facts.Verify(claim with { PeriodType = "TTM" }));
        Assert.False(facts.Verify(claim with { PeriodEnd = "2025-03-31" }));
        Assert.False(facts.Verify(claim with { Scope = "STANDALONE" }));
        Assert.False(facts.Verify(claim with { Source = "NSE_XBRL" }));
        Assert.False(facts.Verify(claim with { Unit = "PERCENT" }));
        Assert.False(facts.Verify(claim with { Metric = "revenue" }));
    }

    [Fact]
    public void ExplicitAnnualIntentRejectsTtmEvenWhenModelOmitsPeriodArgument()
    {
        var facts = new FinancialFacts(FinancialFacts.RequestedPeriod("Show annual financials"));
        facts.Capture(Tool, Statement(period: "TTM"), null, "ok");
        Assert.Empty(facts.Facts);
        Assert.Contains(facts.Issues, i => i.Status == "period_mismatch");
    }

    [Fact]
    public void FailedEmptyAndMissingMetricsAreDistinct()
    {
        var facts = new FinancialFacts();
        facts.Capture(Tool, "{}", null, "error");
        facts.Capture(Tool, "{\"status\":\"ok\",\"data\":[]}", JsonNode.Parse("{\"metrics\":[\"eps\"]}")!.AsObject(), "ok");
        Assert.Contains(facts.Issues, i => i.Status == "failed");
        Assert.Contains(facts.Issues, i => i.Status == "empty");
        Assert.Contains(facts.Issues, i => i.Status == "missing_metric" && i.Metric == "eps");
        Assert.Empty(facts.Facts);
    }

    [Fact]
    public void McpStructuredAndTextEnvelopesAreParsedWithoutDuplication()
    {
        foreach (var envelope in new[] {
            JsonSerializer.Serialize(new { structuredContent = JsonNode.Parse(Statement()), content = new[] { new { type = "text", text = Statement() } } }),
            JsonSerializer.Serialize(new { content = new[] { new { type = "text", text = Statement() } } }) })
        {
            var facts = new FinancialFacts();
            facts.Capture(Tool, envelope, null, "ok");
            Assert.Equal(2, facts.Facts.Count);
        }
    }
}
