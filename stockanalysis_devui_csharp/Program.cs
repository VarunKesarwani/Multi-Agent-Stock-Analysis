using Microsoft.Extensions.AI;
using System.Net;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DevUI;
using Microsoft.Agents.AI.Hosting;
using Microsoft.Agents.AI.Hosting.OpenAI;
using StockAnalysis.DevUI;

var builder = WebApplication.CreateBuilder(args);
if (!builder.Environment.IsDevelopment())
    throw new InvalidOperationException("DevUI is a local development application. Use the Development launch profile.");

builder.WebHost.UseUrls("http://127.0.0.1:8081");
var endpoint = builder.Configuration["AgentApi:BaseUrl"] ?? "http://127.0.0.1:8080/";
if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var baseUri) ||
    !baseUri.IsLoopback || (baseUri.Scheme != "http" && baseUri.Scheme != "https") ||
    !string.IsNullOrEmpty(baseUri.UserInfo) || baseUri.AbsolutePath != "/" ||
    !string.IsNullOrEmpty(baseUri.Query) || !string.IsNullOrEmpty(baseUri.Fragment))
    throw new InvalidOperationException("AgentApi:BaseUrl must be a loopback HTTP(S) origin.");

builder.Services.AddHttpClient("agent-api", client =>
{
    client.BaseAddress = baseUri;
    client.Timeout = TimeSpan.FromSeconds(210);
}).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });

foreach (var mode in new[] { "short_term", "long_term", "portfolio", "tax" })
{
    builder.AddAIAgent(mode, (services, name) =>
        new AgentApiChatClient(services.GetRequiredService<IHttpClientFactory>()
            .CreateClient("agent-api"), name).AsAIAgent(
                name: name,
                description: $"Stock analysis: {name}. Each request is independent; include all required context. Text only."));
}

builder.AddDevUI();
builder.AddOpenAIResponses();
builder.AddOpenAIConversations();
var app = builder.Build();

// Protect all routes, including the separately mapped Responses/Conversations API.
app.Use(async (context, next) =>
{
    if (context.Connection.RemoteIpAddress is not { } address || !IPAddress.IsLoopback(address))
    {
        context.Response.StatusCode = StatusCodes.Status403Forbidden;
        return;
    }
    // Reject cross-origin browser calls to this unauthenticated local development host.
    if (context.Request.Headers.TryGetValue("Origin", out var origin) &&
        (!Uri.TryCreate(origin.ToString(), UriKind.Absolute, out var uri) ||
         !string.Equals(uri.Authority, context.Request.Host.Value, StringComparison.OrdinalIgnoreCase) ||
         uri.Scheme != context.Request.Scheme))
    {
        context.Response.StatusCode = StatusCodes.Status403Forbidden;
        return;
    }
    await next();
});
app.MapOpenAIResponses();
app.MapOpenAIConversations();
app.MapDevUI();
app.MapGet("/", () => Results.Redirect("/devui"));
app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "stockanalysis-devui" }));
app.Run();

public partial class Program;
