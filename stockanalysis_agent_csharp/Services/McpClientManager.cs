using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Options;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using StockAnalysis.Agent.Api.Configuration;
using StockAnalysis.Agent.Api.Contracts;

namespace StockAnalysis.Agent.Api.Services;

public sealed class McpClientManager : IMcpClientManager, IAsyncDisposable
{
    public const string HttpClientName = "mcp-servers";

    private readonly McpClientManagerOptions _options;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILoggerFactory _loggerFactory;
    private readonly ILogger<McpClientManager> _logger;
    private readonly ConcurrentDictionary<string, ServerConnection> _connections;
    private readonly SemaphoreSlim _initializationGate = new(1, 1);
    private volatile bool _initialized;

    public McpClientManager(
        IOptions<McpClientManagerOptions> options,
        IHttpClientFactory httpClientFactory,
        ILoggerFactory loggerFactory,
        ILogger<McpClientManager> logger)
    {
        _options = options.Value;
        _httpClientFactory = httpClientFactory;
        _loggerFactory = loggerFactory;
        _logger = logger;
        _connections = new ConcurrentDictionary<string, ServerConnection>(
            _options.Servers.ToDictionary(
                server => server.Id,
                server => new ServerConnection(server),
                StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        if (_initialized)
        {
            return;
        }

        await _initializationGate.WaitAsync(cancellationToken);
        try
        {
            if (_initialized)
            {
                return;
            }

            await Parallel.ForEachAsync(
                _connections.Values,
                new ParallelOptions
                {
                    CancellationToken = cancellationToken,
                    MaxDegreeOfParallelism = _options.MaxParallelConnections
                },
                async (connection, token) => await ConnectAsync(connection, force: false, token));

            _initialized = true;
        }
        finally
        {
            _initializationGate.Release();
        }
    }

    public async Task RefreshServerAsync(
        string serverId,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(serverId);

        if (!_connections.TryGetValue(serverId, out var connection))
        {
            throw new KeyNotFoundException($"MCP server '{serverId}' is not configured.");
        }

        await ConnectAsync(connection, force: true, cancellationToken);
    }

    public async Task RefreshUnavailableServersAsync(
        CancellationToken cancellationToken = default)
    {
        await InitializeAsync(cancellationToken);

        var unavailable = _connections.Values
            .Where(connection => connection.Options.Enabled &&
                connection.State is not McpConnectionState.Connected)
            .ToArray();

        await Parallel.ForEachAsync(
            unavailable,
            new ParallelOptions
            {
                CancellationToken = cancellationToken,
                MaxDegreeOfParallelism = _options.MaxParallelConnections
            },
            async (connection, token) => await ConnectAsync(connection, force: true, token));
    }

    public async Task<IReadOnlyList<McpToolDescriptor>> ListToolsAsync(
        CancellationToken cancellationToken = default)
    {
        await InitializeAsync(cancellationToken);
        return _connections.Values
            .SelectMany(connection => connection.Tools.Values)
            .Select(registration => registration.Descriptor)
            .OrderBy(tool => tool.QualifiedName, StringComparer.Ordinal)
            .ToArray();
    }

    public async Task<IReadOnlyList<AIFunction>> GetAgentFunctionsAsync(
        CancellationToken cancellationToken = default)
    {
        await InitializeAsync(cancellationToken);
        return _connections.Values
            .SelectMany(connection => connection.Tools.Values)
            .OrderBy(registration => registration.Descriptor.QualifiedName, StringComparer.Ordinal)
            .Select(registration => registration.AgentFunction)
            .ToArray();
    }

    public async Task<CallToolResult> InvokeToolAsync(
        string qualifiedName,
        IReadOnlyDictionary<string, object?>? arguments = null,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(qualifiedName);
        await InitializeAsync(cancellationToken);

        var initialRegistration = FindTool(qualifiedName) ??
            throw new KeyNotFoundException($"MCP tool '{qualifiedName}' is not registered.");
        var connection = initialRegistration.Connection;

        // Calls to different data domains remain parallel, while serializing
        // operations per server prevents reconnect from disposing an active client.
        await connection.Gate.WaitAsync(cancellationToken);
        try
        {
            var registration = connection.Tools.TryGetValue(qualifiedName, out var current)
                ? current
                : throw new KeyNotFoundException(
                    $"MCP tool '{qualifiedName}' is no longer registered by server '{connection.Options.Id}'.");

            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(_options.ToolCallTimeoutSeconds));

            try
            {
                var result = await registration.SourceTool.CallAsync(
                    arguments,
                    cancellationToken: timeout.Token);
                connection.State = McpConnectionState.Connected;
                connection.LastError = null;
                return result;
            }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            {
                var message =
                    $"MCP tool '{qualifiedName}' exceeded the {_options.ToolCallTimeoutSeconds}-second timeout.";
                connection.MarkDegraded(message);
                throw new TimeoutException(message);
            }
            catch (Exception exception)
            {
                connection.MarkDegraded(exception.Message);
                _logger.LogError(
                    exception,
                    "MCP tool {ToolName} failed on server {ServerId}.",
                    qualifiedName,
                    connection.Options.Id);
                throw;
            }
        }
        finally
        {
            connection.Gate.Release();
        }
    }

    public IReadOnlyList<McpServerStatus> GetServerStatuses() =>
        _connections.Values
            .Select(connection => connection.GetStatus())
            .OrderBy(status => status.ServerId, StringComparer.Ordinal)
            .ToArray();

    public McpReadinessStatus GetReadiness()
    {
        var enabled = _connections.Values
            .Where(connection => connection.Options.Enabled)
            .ToArray();
        var unavailableRequired = enabled
            .Where(connection => connection.Options.Required &&
                connection.State is not McpConnectionState.Connected)
            .Select(connection => connection.Options.Id)
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();

        return new McpReadinessStatus(
            unavailableRequired.Length == 0,
            enabled.Count(connection => connection.State is McpConnectionState.Connected),
            enabled.Length,
            unavailableRequired);
    }

    private ToolRegistration? FindTool(string qualifiedName) =>
        _connections.Values
            .SelectMany(connection => connection.Tools.Values)
            .FirstOrDefault(item => string.Equals(
                item.Descriptor.QualifiedName,
                qualifiedName,
                StringComparison.Ordinal));

    private async Task ConnectAsync(
        ServerConnection connection,
        bool force,
        CancellationToken cancellationToken)
    {
        if (!connection.Options.Enabled)
        {
            connection.State = McpConnectionState.Disabled;
            return;
        }

        await connection.Gate.WaitAsync(cancellationToken);
        try
        {
            if (!force && connection.Client is not null)
            {
                return;
            }

            connection.LastAttemptAt = DateTimeOffset.UtcNow;
            connection.State = McpConnectionState.Connecting;
            await DisposeConnectionAsync(connection);

            var endpoint = new Uri(connection.Options.Endpoint, UriKind.Absolute);
            var transportOptions = new HttpClientTransportOptions
            {
                Name = connection.Options.Id,
                Endpoint = endpoint,
                TransportMode = HttpTransportMode.StreamableHttp,
                ConnectionTimeout = TimeSpan.FromSeconds(_options.InitializationTimeoutSeconds),
                EnableStandaloneGetStream = false,
                AdditionalHeaders = connection.Options.Headers.Count == 0
                    ? null
                    : connection.Options.Headers
            };

            var transport = new HttpClientTransport(
                transportOptions,
                _httpClientFactory.CreateClient(HttpClientName),
                _loggerFactory);

            try
            {
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                timeout.CancelAfter(TimeSpan.FromSeconds(_options.InitializationTimeoutSeconds));

                var client = await McpClient.CreateAsync(
                    transport,
                    new McpClientOptions
                    {
                        ClientInfo = new Implementation
                        {
                            Name = "stockanalysis-agent-api",
                            Version = "0.1.0"
                        },
                        InitializationTimeout = TimeSpan.FromSeconds(
                            _options.InitializationTimeoutSeconds)
                    },
                    _loggerFactory,
                    timeout.Token);

                var discoveredTools = await client.ListToolsAsync(
                    cancellationToken: timeout.Token);
                var allowedTools = connection.Options.AllowedTools.Count == 0
                    ? discoveredTools
                    : discoveredTools
                        .Where(tool => connection.Options.AllowedTools.Contains(
                            tool.Name,
                            StringComparer.Ordinal))
                        .ToArray();

                var registrations = allowedTools.Select(tool =>
                {
                    var qualifiedName = ToolNamePolicy.Qualify(
                        connection.Options.Id,
                        tool.Name);
                    var descriptor = new McpToolDescriptor(
                        qualifiedName,
                        connection.Options.Id,
                        tool.Name,
                        tool.Title,
                        tool.Description,
                        tool.JsonSchema.Clone());
                    AIFunction agentFunction = new ManagedMcpFunction(
                        this,
                        descriptor,
                        tool.ReturnJsonSchema,
                        tool.JsonSerializerOptions);
                    return new ToolRegistration(
                        connection,
                        tool,
                        agentFunction,
                        descriptor);
                }).ToDictionary(
                    item => item.Descriptor.QualifiedName,
                    StringComparer.Ordinal);

                LogMissingAllowlistedTools(
                    connection,
                    discoveredTools.Select(tool => tool.Name));

                connection.Transport = transport;
                connection.Client = client;
                connection.Tools = registrations;
                connection.State = McpConnectionState.Connected;
                connection.LastConnectedAt = DateTimeOffset.UtcNow;
                connection.LastError = null;

                _logger.LogInformation(
                    "Connected to MCP server {ServerId} at {Endpoint}; exposed {ToolCount} of {DiscoveredToolCount} discovered tools.",
                    connection.Options.Id,
                    endpoint,
                    registrations.Count,
                    discoveredTools.Count);
            }
            catch
            {
                await transport.DisposeAsync();
                throw;
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            connection.Tools = new Dictionary<string, ToolRegistration>();
            connection.MarkDegraded(exception.Message);
            _logger.LogWarning(
                exception,
                "MCP server {ServerId} at {Endpoint} is unavailable. Agent API will continue and retry later.",
                connection.Options.Id,
                connection.Options.Endpoint);
        }
        finally
        {
            connection.Gate.Release();
        }
    }

    private void LogMissingAllowlistedTools(
        ServerConnection connection,
        IEnumerable<string> discoveredToolNames)
    {
        if (connection.Options.AllowedTools.Count == 0)
        {
            return;
        }

        var discovered = discoveredToolNames.ToHashSet(StringComparer.Ordinal);
        var missing = connection.Options.AllowedTools
            .Where(tool => !discovered.Contains(tool))
            .ToArray();
        if (missing.Length > 0)
        {
            _logger.LogWarning(
                "MCP server {ServerId} did not advertise allowlisted tools: {MissingTools}.",
                connection.Options.Id,
                string.Join(", ", missing));
        }
    }

    private static async ValueTask DisposeConnectionAsync(ServerConnection connection)
    {
        connection.Tools = new Dictionary<string, ToolRegistration>();

        if (connection.Client is not null)
        {
            await connection.Client.DisposeAsync();
            connection.Client = null;
        }

        if (connection.Transport is not null)
        {
            await connection.Transport.DisposeAsync();
            connection.Transport = null;
        }
    }

    public async ValueTask DisposeAsync()
    {
        foreach (var connection in _connections.Values)
        {
            await connection.Gate.WaitAsync();
            try
            {
                await DisposeConnectionAsync(connection);
            }
            finally
            {
                connection.Gate.Release();
                connection.Gate.Dispose();
            }
        }

        _initializationGate.Dispose();
    }

    private sealed class ServerConnection(McpServerOptions options)
    {
        public McpServerOptions Options { get; } = options;
        public SemaphoreSlim Gate { get; } = new(1, 1);
        public HttpClientTransport? Transport { get; set; }
        public McpClient? Client { get; set; }
        public IReadOnlyDictionary<string, ToolRegistration> Tools { get; set; } =
            new Dictionary<string, ToolRegistration>();
        public McpConnectionState State { get; set; } = McpConnectionState.Disconnected;
        public DateTimeOffset? LastAttemptAt { get; set; }
        public DateTimeOffset? LastConnectedAt { get; set; }
        public string? LastError { get; set; }

        public void MarkDegraded(string error)
        {
            State = McpConnectionState.Degraded;
            LastError = error;
        }

        public McpServerStatus GetStatus() => new(
            Options.Id,
            Options.Endpoint,
            Options.Required,
            State,
            Tools.Count,
            LastAttemptAt,
            LastConnectedAt,
            LastError);
    }

    private sealed record ToolRegistration(
        ServerConnection Connection,
        McpClientTool SourceTool,
        AIFunction AgentFunction,
        McpToolDescriptor Descriptor);

    private sealed class ManagedMcpFunction(
        McpClientManager manager,
        McpToolDescriptor descriptor,
        JsonElement? returnJsonSchema,
        JsonSerializerOptions serializerOptions) : AIFunction
    {
        public override string Name => descriptor.QualifiedName;

        public override string Description => descriptor.Description;

        public override JsonElement JsonSchema => descriptor.InputSchema;

        public override JsonElement? ReturnJsonSchema => returnJsonSchema;

        public override JsonSerializerOptions JsonSerializerOptions => serializerOptions;

        protected override async ValueTask<object?> InvokeCoreAsync(
            AIFunctionArguments arguments,
            CancellationToken cancellationToken)
        {
            return await manager.InvokeToolAsync(
                descriptor.QualifiedName,
                arguments,
                cancellationToken);
        }
    }
}
