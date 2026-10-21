using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace StockAnalysis.Agent.Api.Agent;

/// <summary>Loads required instructions and strategy rules once; missing/invalid files fail startup.</summary>
public sealed class AgentPolicy
{
    public static readonly string[] Modes = ["short_term", "long_term", "portfolio", "tax"];
    private readonly string instructions;
    private readonly string rules;
    public string Version { get; }

    public AgentPolicy(IHostEnvironment environment)
    {
        instructions = File.ReadAllText(Path.Combine(environment.ContentRootPath, "Instructions", "agent-system.md"));
        rules = File.ReadAllText(Path.Combine(environment.ContentRootPath, "Instructions", "strategy-rules.json"));
        using var parsed = JsonDocument.Parse(rules);
        if (string.IsNullOrWhiteSpace(instructions) || !parsed.RootElement.TryGetProperty("version", out _))
            throw new InvalidOperationException("Agent instructions and versioned strategy rules are required.");
        Version = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(instructions + rules)))[..16];
    }

    public string ForMode(string mode) => $"{instructions}\nMode: {mode}\nUTC date: {DateTimeOffset.UtcNow:yyyy-MM-dd}\nPolicy hash: {Version}\nStrategy configuration (starter rules, unvalidated):\n{rules}";
}
