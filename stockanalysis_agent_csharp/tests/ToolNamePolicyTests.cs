using StockAnalysis.Agent.Api.Configuration;

namespace StockAnalysis.Agent.Api.Tests;

public sealed class ToolNamePolicyTests
{
    [Theory]
    [InlineData("market")]
    [InlineData("annual_reports")]
    [InlineData("kite")]
    [InlineData("server-2")]
    public void Valid_server_ids_are_accepted(string serverId)
    {
        Assert.True(ToolNamePolicy.IsValidServerId(serverId));
    }

    [Theory]
    [InlineData("")]
    [InlineData("Market")]
    [InlineData("2server")]
    [InlineData("server id")]
    public void Invalid_server_ids_are_rejected(string serverId)
    {
        Assert.False(ToolNamePolicy.IsValidServerId(serverId));
    }

    [Fact]
    public void Tool_name_is_qualified_with_server_id()
    {
        Assert.Equal(
            "financial__financial_get_statement",
            ToolNamePolicy.Qualify("financial", "financial_get_statement"));
    }

    [Fact]
    public void Kite_tool_name_is_qualified_to_avoid_market_tool_collisions()
    {
        Assert.Equal("kite__get_ohlc", ToolNamePolicy.Qualify("kite", "get_ohlc"));
    }
}
