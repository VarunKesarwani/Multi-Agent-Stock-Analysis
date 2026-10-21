using System.Text.Json;
using StockAnalysis.Agent.Api.Analytics;

namespace StockAnalysis.Agent.Api.Tests;

public class PortfolioAnalyticsTests
{
    private static JsonElement Result(object value) => JsonSerializer.SerializeToElement(value);

    [Fact]
    public void MissingTaxRatesAreRejectedRatherThanDefaultingToZero()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<TaxScenarioRequest>("{}"));
    }

    [Fact]
    public void CagrUsesDatesAndRejectsExternalFlows()
    {
        var request = new CagrRequest(100, 121, new(2020, 1, 1), new(2022, 1, 1), false);
        var expected = Math.Pow(1.21, 365.25 / 731) - 1;
        Assert.Equal(expected, Result(PortfolioAnalytics.Cagr(request)).GetProperty("cagr").GetDouble(), 10);
        Assert.Throws<ArgumentException>(() => PortfolioAnalytics.Cagr(request with { HasExternalCashFlows = true }));
    }

    [Fact]
    public void FlatReturnsHaveUndefinedSharpe()
    {
        var result = Result(PortfolioAnalytics.Performance(new([0, 0, 0], 12, 0, new(2025, 1, 1), new(2025, 4, 1), true, true)));
        Assert.Equal(JsonValueKind.Null, result.GetProperty("sharpeRatio").ValueKind);
        Assert.Equal(0, result.GetProperty("maximumDrawdown").GetDouble());
    }

    [Fact]
    public void DrawdownIncludesInitialCapitalAndCompounding()
    {
        var result = Result(PortfolioAnalytics.Performance(new([-0.1, -0.1, 0.25], 12, 0, new(2025, 1, 1), new(2025, 4, 1), true, true)));
        Assert.Equal(0.19, result.GetProperty("maximumDrawdown").GetDouble(), 10);
        Assert.Equal(0.0125, result.GetProperty("timeWeightedReturn").GetDouble(), 10);
    }

    [Fact]
    public void SharpeUsesSampleDeviationAndPeriodicRiskFreeRate()
    {
        var result = Result(PortfolioAnalytics.Performance(new([0.01, 0.03], 12, 0.06, new(2025, 1, 1), new(2025, 3, 1), true, true)));
        var expected = (0.02 - (Math.Pow(1.06, 1.0 / 12) - 1)) / Math.Sqrt(0.0002) * Math.Sqrt(12);
        Assert.Equal(expected, result.GetProperty("sharpeRatio").GetDouble(), 10);
    }

    [Fact]
    public void UnadjustedReturnsAreRejected()
    {
        Assert.Throws<ArgumentException>(() => PortfolioAnalytics.Performance(new([0.01, 0.02], 252, 0.06, new(2025, 1, 1), new(2025, 1, 3), false, true)));
    }

    [Fact]
    public void XirrRecoversKnownAnnualReturn()
    {
        var result = Result(PortfolioAnalytics.Xirr(new([new(new(2025, 1, 1), -1000), new(new(2026, 1, 1), 1100)])));
        Assert.Equal(0.1, result.GetProperty("xirr").GetDouble(), 8);
    }

    [Fact]
    public void XirrRejectsPotentiallyMultipleRoots()
    {
        Assert.Throws<ArgumentException>(() => PortfolioAnalytics.Xirr(new([
            new(new(2023, 1, 1), -100), new(new(2024, 1, 1), 230), new(new(2025, 1, 1), -132), new(new(2026, 1, 1), 1)])));
    }

    [Fact]
    public void TaxScenarioUsesCallerRatesAndRequiresReconciledBases()
    {
        var request = new TaxScenarioRequest("test", "2025-26", "example-only", "https://example.com/rules", 100, 200, 0.2m, 0.1m, 0, 0.04m, true);
        Assert.Equal(41.60m, Result(TaxScenario.Estimate(request)).GetProperty("estimate").GetDecimal());
        Assert.Throws<ArgumentException>(() => TaxScenario.Estimate(request with { TaxableBasesReconciled = false }));
    }
}
