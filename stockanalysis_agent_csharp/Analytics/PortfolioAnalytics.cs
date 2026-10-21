using System.Text.Json.Serialization;

namespace StockAnalysis.Agent.Api.Analytics;

/// <summary>Deterministic returns calculated from validated, supplied data; all rates are decimals.</summary>
public static class PortfolioAnalytics
{
    /// <summary>CAGR is valid only when no external contributions or withdrawals occurred.</summary>
    public static object Cagr(CagrRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.HasExternalCashFlows || request.StartValue <= 0 || request.EndValue < 0 || request.End <= request.Start)
            throw new ArgumentException("CAGR requires positive starting value, nonnegative ending value, increasing dates and no external cash flows. Use XIRR for cash flows.");
        var years = (request.End.DayNumber - request.Start.DayNumber) / 365.25;
        var rate = Math.Pow((double)(request.EndValue / request.StartValue), 1 / years) - 1;
        if (!double.IsFinite(rate)) throw new ArgumentException("CAGR exceeds supported numeric range.");
        return new { cagr = rate, totalReturn = request.EndValue / request.StartValue - 1, years,
            convention = "ACT/365.25; decimal rates; no external cash flows", annualizedShortPeriod = years < 1 };
    }

    /// <summary>Uses a regular series of cash-flow-adjusted, net-of-fee total returns.</summary>
    public static object Performance(PerformanceRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.Returns is null || request.Returns.Length < 2 || request.Returns.Length > 10000 ||
            request.PeriodsPerYear is not (12 or 52 or 252) || request.End <= request.Start ||
            !request.CashFlowAdjusted || !request.IncludesDividendsAndFees ||
            !double.IsFinite(request.AnnualRiskFreeRate) || request.AnnualRiskFreeRate <= -1 ||
            request.Returns.Any(r => !double.IsFinite(r) || r <= -1))
            throw new ArgumentException("Supply 2–10000 regular net total returns > -1, increasing dates, periodsPerYear 12/52/252, explicit risk-free rate and confirmed cash-flow/dividend/fee adjustments.");
        var returns = request.Returns;
        var rf = Math.Pow(1 + request.AnnualRiskFreeRate, 1.0 / request.PeriodsPerYear) - 1;
        var mean = returns.Average();
        var variance = returns.Sum(r => Math.Pow(r - mean, 2)) / (returns.Length - 1);
        var deviation = Math.Sqrt(variance);
        double wealth = 1, peak = 1, maxDrawdown = 0;
        foreach (var r in returns)
        {
            wealth *= 1 + r;
            peak = Math.Max(peak, wealth);
            maxDrawdown = Math.Max(maxDrawdown, 1 - wealth / peak);
        }
        var volatility = deviation * Math.Sqrt(request.PeriodsPerYear);
        double? sharpe = deviation < 1e-12 ? null : (mean - rf) / deviation * Math.Sqrt(request.PeriodsPerYear);
        if (!double.IsFinite(wealth) || !double.IsFinite(volatility) || (sharpe.HasValue && !double.IsFinite(sharpe.Value)))
            throw new ArgumentException("Returns exceed supported numeric range.");
        return new { timeWeightedReturn = wealth - 1, annualizedVolatility = volatility, sharpeRatio = sharpe,
            maximumDrawdown = maxDrawdown, observations = returns.Length, request.PeriodsPerYear,
            request.AnnualRiskFreeRate, request.Start, request.End,
            convention = "Arithmetic excess returns / sample standard deviation, sqrt annualization; drawdown from compounded adjusted returns",
            warning = returns.Length < request.PeriodsPerYear ? "Less than one year of observations; annualized risk statistics are unstable." : null };
    }

    /// <summary>Investor-perspective XIRR, with negative investments and positive receipts including terminal valuation.</summary>
    public static object Xirr(XirrRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.Flows is null || request.Flows.Length < 2 || request.Flows.Length > 10000)
            throw new ArgumentException("Supply dated investments, withdrawals and a terminal valuation as cash flows.");
        var flows = request.Flows.GroupBy(x => x.Date).Select(g => new CashFlow(g.Key, g.Sum(x => x.Amount)))
            .Where(x => x.Amount != 0).OrderBy(x => x.Date).ToArray();
        if (flows.Length < 2 || flows[0].Amount >= 0 || flows[^1].Amount <= 0)
            throw new ArgumentException("Require an initial investment (negative) and later proceeds including terminal value (positive).");
        // Restrict the initial implementation to conventional cash flows so uniqueness is defensible.
        if (flows.Zip(flows.Skip(1), (a,b) => Math.Sign(a.Amount) != Math.Sign(b.Amount)).Count(x => x) != 1)
            throw new ArgumentException("Nonconventional cash flows can have multiple XIRRs; this calculator refuses an ambiguous result.");
        var scale = (double)flows.Max(x => Math.Abs(x.Amount));
        double Npv(double rate) => flows.Sum(x => (double)x.Amount / scale / Math.Pow(1 + rate, (x.Date.DayNumber - flows[0].Date.DayNumber) / 365.0));
        double low = -0.9999, high = 1;
        while (Npv(high) > 0 && high < 1e6) high *= 2;
        if (Npv(low) <= 0 || Npv(high) >= 0) throw new ArgumentException("No XIRR root within supported range (-99.99% to approximately 100000000%).");
        for (var i = 0; i < 200; i++)
        {
            var middle = (low + high) / 2;
            if (Npv(middle) > 0) low = middle; else high = middle;
        }
        return new { xirr = (low + high) / 2, convention = "ACT/365, investor perspective, conventional cash flows only", observations = flows.Length };
    }
}

/// <summary>No-flow investment growth input.</summary>
public sealed record CagrRequest([property: JsonRequired] decimal StartValue, [property: JsonRequired] decimal EndValue, [property: JsonRequired] DateOnly Start, [property: JsonRequired] DateOnly End, [property: JsonRequired] bool HasExternalCashFlows);
/// <summary>Regular decimal total returns, after fees, with external flows removed.</summary>
public sealed record PerformanceRequest([property: JsonRequired] double[] Returns, [property: JsonRequired] int PeriodsPerYear, [property: JsonRequired] double AnnualRiskFreeRate,
    [property: JsonRequired] DateOnly Start, [property: JsonRequired] DateOnly End, [property: JsonRequired] bool CashFlowAdjusted, [property: JsonRequired] bool IncludesDividendsAndFees);
/// <summary>Dated cash flow; negative is money invested.</summary>
public sealed record CashFlow([property: JsonRequired] DateOnly Date, [property: JsonRequired] decimal Amount);
/// <summary>Cash flows must include current terminal portfolio value.</summary>
public sealed record XirrRequest([property: JsonRequired] CashFlow[] Flows);
