namespace StockAnalysis.Agent.Api.Services;

public sealed class McpClientWarmupService(
    IMcpClientManager manager,
    ILogger<McpClientWarmupService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        try
        {
            await manager.InitializeAsync(stoppingToken);
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // Normal host shutdown.
        }
        catch (Exception exception)
        {
            logger.LogError(exception, "Unexpected MCP client manager warm-up failure.");
        }
    }
}

