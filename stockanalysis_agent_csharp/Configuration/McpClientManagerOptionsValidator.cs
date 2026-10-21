using Microsoft.Extensions.Options;

namespace StockAnalysis.Agent.Api.Configuration;

public sealed class McpClientManagerOptionsValidator : IValidateOptions<McpClientManagerOptions>
{
    public ValidateOptionsResult Validate(string? name, McpClientManagerOptions options)
    {
        var errors = new List<string>();

        if (options.InitializationTimeoutSeconds is < 1 or > 300)
        {
            errors.Add("InitializationTimeoutSeconds must be between 1 and 300.");
        }

        if (options.ToolCallTimeoutSeconds is < 1 or > 300)
        {
            errors.Add("ToolCallTimeoutSeconds must be between 1 and 300.");
        }

        if (options.ReconnectIntervalSeconds is < 5 or > 3600)
        {
            errors.Add("ReconnectIntervalSeconds must be between 5 and 3600.");
        }

        if (options.MaxParallelConnections is < 1 or > 16)
        {
            errors.Add("MaxParallelConnections must be between 1 and 16.");
        }

        if (!options.Servers.Any(server => server.Enabled))
        {
            errors.Add("At least one MCP server must be enabled.");
        }

        var duplicateIds = options.Servers
            .GroupBy(server => server.Id, StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() > 1)
            .Select(group => group.Key);

        foreach (var duplicateId in duplicateIds)
        {
            errors.Add($"MCP server id '{duplicateId}' is duplicated.");
        }

        foreach (var server in options.Servers)
        {
            if (!ToolNamePolicy.IsValidServerId(server.Id))
            {
                errors.Add($"MCP server id '{server.Id}' must start with a letter and contain only lowercase letters, numbers, '_' or '-'.");
            }

            if (!Uri.TryCreate(server.Endpoint, UriKind.Absolute, out var endpoint) ||
                (endpoint.Scheme != Uri.UriSchemeHttp && endpoint.Scheme != Uri.UriSchemeHttps))
            {
                errors.Add($"MCP endpoint for '{server.Id}' must be an absolute HTTP or HTTPS URL.");
            }

            if (server.AllowedTools.Any(string.IsNullOrWhiteSpace))
            {
                errors.Add($"Allowed tools for MCP server '{server.Id}' cannot contain an empty name.");
            }

            var duplicateTools = server.AllowedTools
                .Where(tool => !string.IsNullOrWhiteSpace(tool))
                .GroupBy(tool => tool, StringComparer.Ordinal)
                .Where(group => group.Count() > 1)
                .Select(group => group.Key);

            foreach (var duplicateTool in duplicateTools)
            {
                errors.Add($"Allowed tool '{duplicateTool}' is duplicated for MCP server '{server.Id}'.");
            }
        }

        return errors.Count == 0
            ? ValidateOptionsResult.Success
            : ValidateOptionsResult.Fail(errors);
    }
}
