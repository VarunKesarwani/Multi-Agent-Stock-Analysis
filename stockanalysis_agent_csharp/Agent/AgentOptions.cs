namespace StockAnalysis.Agent.Api.Agent;

/// <summary>Agent model configuration. Override with Agent__* environment variables.</summary>
public sealed class AgentOptions
{
    public const string SectionName = "Agent";
    public bool Enabled { get; set; }
    /// <summary>Model provider: "ollama" (local, native /api/chat) or "sarvam" (Sarvam AI chat completions).</summary>
    public string Provider { get; set; } = "ollama";
    public string Endpoint { get; set; } = "http://localhost:11434/";
    public string Model { get; set; } = "";
    /// <summary>Sarvam API subscription key. Supply through user secrets (Agent:ApiKey) or Agent__ApiKey; never commit it.</summary>
    public string ApiKey { get; set; } = "";
    /// <summary>Chat completions path relative to Endpoint for the Sarvam provider.</summary>
    public string ChatPath { get; set; } = "v1/chat/completions";
    public int TimeoutSeconds { get; set; } = 180;
    public int MaxToolRounds { get; set; } = 6;
    public int MaxToolCalls { get; set; } = 20;
    public int MaxToolResultCharacters { get; set; } = 30000;
    public int MaxMessageCharacters { get; set; } = 12000;
    /// <summary>Completion token budget for the Sarvam provider (reasoning tokens count toward this).</summary>
    public int MaxCompletionTokens { get; set; } = 4096;
    /// <summary>Explicit agent-level allowlist, intersected with manager policy. Empty exposes no MCP tools.</summary>
    public string[] AllowedMcpTools { get; set; } = [];
}
