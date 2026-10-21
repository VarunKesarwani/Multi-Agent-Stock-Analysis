using System.Text.RegularExpressions;

namespace StockAnalysis.Agent.Api.Configuration;

public static partial class ToolNamePolicy
{
    [GeneratedRegex("^[a-z][a-z0-9_-]*$", RegexOptions.CultureInvariant)]
    private static partial Regex ServerIdRegex();

    public static bool IsValidServerId(string value) =>
        !string.IsNullOrWhiteSpace(value) && ServerIdRegex().IsMatch(value);

    public static string Qualify(string serverId, string toolName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(serverId);
        ArgumentException.ThrowIfNullOrWhiteSpace(toolName);
        return $"{serverId}__{toolName}";
    }
}

