using StockAnalysis.Agent.Api.Configuration;

namespace StockAnalysis.Agent.Api.Tests;

public sealed class McpClientManagerOptionsValidatorTests
{
    private readonly McpClientManagerOptionsValidator _validator = new();

    [Fact]
    public void Valid_configuration_passes()
    {
        var options = new McpClientManagerOptions
        {
            Servers =
            [
                new McpServerOptions { Id = "financial", Endpoint = "http://localhost:8001/mcp" }
            ]
        };

        Assert.True(_validator.Validate(null, options).Succeeded);
    }

    [Fact]
    public void Duplicate_server_ids_fail_case_insensitively()
    {
        var options = new McpClientManagerOptions
        {
            Servers =
            [
                new McpServerOptions { Id = "news", Endpoint = "http://localhost:8002/mcp" },
                new McpServerOptions { Id = "NEWS", Endpoint = "http://localhost:9002/mcp" }
            ]
        };

        var result = _validator.Validate(null, options);

        Assert.True(result.Failed);
        Assert.Contains(result.Failures, message => message.Contains("duplicated", StringComparison.Ordinal));
    }

    [Fact]
    public void Configuration_requires_at_least_one_enabled_server()
    {
        var options = new McpClientManagerOptions
        {
            Servers =
            [
                new McpServerOptions
                {
                    Id = "annual_reports",
                    Endpoint = "http://localhost:8003/mcp",
                    Enabled = false,
                    Required = false
                }
            ]
        };

        var result = _validator.Validate(null, options);

        Assert.True(result.Failed);
        Assert.Contains(result.Failures, message => message.Contains("At least one", StringComparison.Ordinal));
    }

    [Fact]
    public void Duplicate_allowlisted_tool_fails()
    {
        var options = new McpClientManagerOptions
        {
            Servers =
            [
                new McpServerOptions
                {
                    Id = "news",
                    Endpoint = "http://localhost:8002/mcp",
                    AllowedTools = ["news_search", "news_search"]
                }
            ]
        };

        var result = _validator.Validate(null, options);

        Assert.True(result.Failed);
        Assert.Contains(result.Failures, message => message.Contains("Allowed tool", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(0, 4)]
    [InlineData(30, 0)]
    [InlineData(3601, 17)]
    public void Invalid_reconnect_or_parallel_limits_fail(
        int reconnectIntervalSeconds,
        int maxParallelConnections)
    {
        var options = new McpClientManagerOptions
        {
            ReconnectIntervalSeconds = reconnectIntervalSeconds,
            MaxParallelConnections = maxParallelConnections,
            Servers =
            [
                new McpServerOptions
                {
                    Id = "market",
                    Endpoint = "http://localhost:5000/mcp"
                }
            ]
        };

        Assert.True(_validator.Validate(null, options).Failed);
    }
}
