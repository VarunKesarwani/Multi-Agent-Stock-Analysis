using System.Diagnostics;
using System.Text.Json;
using MarketDataMcpServer.Models;

namespace MarketDataMcpServer.Services;

public sealed class PythonIndicatorService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    private readonly MarketDataService _marketDataService;
    private readonly IndicatorCatalog _indicatorCatalog;
    private readonly ILogger<PythonIndicatorService> _logger;
    private readonly string _pythonExecutable;
    private readonly string _runnerPath;
    private readonly int _timeoutSeconds;

    public PythonIndicatorService(
        MarketDataService marketDataService,
        IndicatorCatalog indicatorCatalog,
        IConfiguration configuration,
        ILogger<PythonIndicatorService> logger)
    {
        _marketDataService = marketDataService;
        _indicatorCatalog = indicatorCatalog;
        _logger = logger;
        _pythonExecutable = configuration["PythonIndicators:Executable"]
            ?? Environment.GetEnvironmentVariable("PYTHON_EXECUTABLE")
            ?? "python";
        _timeoutSeconds = configuration.GetValue("PythonIndicators:TimeoutSeconds", 60);

        var configuredRunner = configuration["PythonIndicators:RunnerPath"]
            ?? Environment.GetEnvironmentVariable("PYTHON_INDICATOR_RUNNER");
        _runnerPath = string.IsNullOrWhiteSpace(configuredRunner)
            ? Path.Combine(AppContext.BaseDirectory, "Python", "indicator_runner.py")
            : configuredRunner;
    }

    public async Task<object> CalculateAsync(string indicatorName, string symbol, int period, int limit, CancellationToken cancellationToken = default)
    {
        var indicator = _indicatorCatalog.FindByIndicatorOrToolName(indicatorName)
            ?? throw new ArgumentException($"Unknown indicator '{indicatorName}'.", nameof(indicatorName));

        if (!indicator.PythonSupported)
        {
            throw new NotSupportedException($"Indicator '{indicator.Name}' is registered but not yet implemented in the Python bridge.");
        }

        var rows = (await _marketDataService.GetOhlcvHistoryAsync(symbol, limit, cancellationToken)).ToList();
        if (rows.Count == 0)
        {
            return new
            {
                indicator = indicator.Name,
                symbol,
                period,
                data = Array.Empty<object>()
            };
        }

        var payload = new
        {
            indicator = indicator.Name,
            symbol,
            period,
            rows
        };

        var payloadPath = Path.Combine(Path.GetTempPath(), $"mcp-indicator-{Guid.NewGuid():N}.json");
        await File.WriteAllTextAsync(payloadPath, JsonSerializer.Serialize(payload, JsonOptions), cancellationToken);

        try
        {
            using var process = StartPythonProcess(payloadPath);
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(_timeoutSeconds));

            var stdoutTask = process.StandardOutput.ReadToEndAsync(timeout.Token);
            var stderrTask = process.StandardError.ReadToEndAsync(timeout.Token);

            await process.WaitForExitAsync(timeout.Token);

            var stdout = await stdoutTask;
            var stderr = await stderrTask;

            if (process.ExitCode != 0)
            {
                _logger.LogError("Python indicator runner failed with exit code {ExitCode}: {Error}", process.ExitCode, stderr);
                throw new InvalidOperationException($"Python indicator runner failed: {stderr}");
            }

            return JsonSerializer.Deserialize<object>(stdout, JsonOptions)
                ?? new { indicator = indicator.Name, symbol, period, data = Array.Empty<object>() };
        }
        finally
        {
            TryDelete(payloadPath);
        }
    }

    private Process StartPythonProcess(string payloadPath)
    {
        if (!File.Exists(_runnerPath))
        {
            throw new FileNotFoundException("Python indicator runner was not found.", _runnerPath);
        }

        var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = _pythonExecutable,
                ArgumentList = { _runnerPath, payloadPath },
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            }
        };

        process.Start();
        return process;
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Best-effort cleanup for temp payloads.
        }
    }
}