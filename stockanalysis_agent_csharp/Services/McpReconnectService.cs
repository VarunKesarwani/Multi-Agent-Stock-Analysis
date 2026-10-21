using Microsoft.Extensions.Options;
using StockAnalysis.Agent.Api.Configuration;

namespace StockAnalysis.Agent.Api.Services;

public sealed class McpReconnectService(
    IMcpClientManager manager,
    IOptions<McpClientManagerOptions> options,
    ILogger<McpReconnectService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(
            TimeSpan.FromSeconds(options.Value.ReconnectIntervalSeconds));

        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                try
                {
                    await manager.RefreshUnavailableServersAsync(stoppingToken);
                }
                catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
                {
                    break;
                }
                catch (Exception exception)
                {
                    logger.LogError(exception, "MCP reconnect attempt failed unexpectedly; monitoring will continue.");
                }
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // Normal host shutdown.
        }
    }
}
