using Microsoft.Extensions.AI;
using ModelContextProtocol.Protocol;
using StockAnalysis.Agent.Api.Contracts;

namespace StockAnalysis.Agent.Api.Services;

public interface IMcpClientManager
{
    Task InitializeAsync(CancellationToken cancellationToken = default);

    Task RefreshServerAsync(string serverId, CancellationToken cancellationToken = default);

    Task RefreshUnavailableServersAsync(CancellationToken cancellationToken = default);

    Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(CancellationToken cancellationToken = default);

    Task<IReadOnlyList<AIFunction>> GetAgentFunctionsAsync(CancellationToken cancellationToken = default);

    Task<CallToolResult> InvokeToolAsync(
        string qualifiedName,
        IReadOnlyDictionary<string, object?>? arguments = null,
        CancellationToken cancellationToken = default);

    IReadOnlyList<McpServerStatus> GetServerStatuses();

    McpReadinessStatus GetReadiness();
}
