using System.Text.Json.Serialization;

namespace StockAnalysis.Agent.Api.Analytics;

/// <summary>Arithmetic scenario on already reconciled taxable gains, not a tax-return computation.</summary>
public static class TaxScenario
{
    /// <summary>Applies explicitly supplied effective rates without inferring legal eligibility or loss setoff.</summary>
    public static object Estimate(TaxScenarioRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (string.IsNullOrWhiteSpace(request.Jurisdiction) || string.IsNullOrWhiteSpace(request.FinancialYear) ||
            string.IsNullOrWhiteSpace(request.RuleVersion) || !Uri.TryCreate(request.RuleSource, UriKind.Absolute, out var source) ||
            source.Scheme != "https" || !request.TaxableBasesReconciled ||
            request.ShortTermTaxableGain < 0 || request.LongTermTaxableGain < 0 ||
            request.ShortTermRate is < 0 or > 1 || request.LongTermRate is < 0 or > 1 ||
            request.SurchargeRate is < 0 or > 1 || request.CessRate is < 0 or > 1)
            throw new ArgumentException("Supply jurisdiction, financial year, verified HTTPS rule source/version, reconciled nonnegative taxable bases after exemptions/setoffs and explicit decimal tax rates.");
        var baseTax = request.ShortTermTaxableGain * request.ShortTermRate + request.LongTermTaxableGain * request.LongTermRate;
        var surcharge = baseTax * request.SurchargeRate;
        var cess = (baseTax + surcharge) * request.CessRate;
        return new { estimate = decimal.Round(baseTax + surcharge + cess, 2), baseTax, surcharge, cess,
            request.Jurisdiction, request.FinancialYear, request.RuleVersion, request.RuleSource,
            status = "scenario_only",
            exclusions = "No FIFO reconciliation, exemptions, loss setoff, slab income, marginal relief, rebate, residency treaty, grandfathering or instrument eligibility calculations. Rates/bases supplied by caller, not verified by this calculator. Not a filing liability." };
    }
}

/// <summary>Verified taxable bases and caller-supplied policy inputs; no statutory rates are defaulted.</summary>
public sealed record TaxScenarioRequest([property: JsonRequired] string Jurisdiction, [property: JsonRequired] string FinancialYear, [property: JsonRequired] string RuleVersion, [property: JsonRequired] string RuleSource,
    [property: JsonRequired] decimal ShortTermTaxableGain, [property: JsonRequired] decimal LongTermTaxableGain, [property: JsonRequired] decimal ShortTermRate, [property: JsonRequired] decimal LongTermRate,
    [property: JsonRequired] decimal SurchargeRate, [property: JsonRequired] decimal CessRate, [property: JsonRequired] bool TaxableBasesReconciled);
