namespace StockAnalysis.Agent.Api.Agent;

/// <summary>One stateless analysis request. Modes: short_term, long_term, portfolio, tax.</summary>
public sealed record AgentRequest(string Message, string Mode = "short_term");
/// <summary>Audit entry, excludes arguments and private tool output.</summary>
public sealed record AgentToolTrace(string Name, string Status);
/// <summary>Response text plus tools actually attempted, model and policy identity.</summary>
public sealed record AgentResponse(string Answer, string Mode, string Model, string PolicyVersion,
    IReadOnlyList<AgentToolTrace> Tools, string Status);
