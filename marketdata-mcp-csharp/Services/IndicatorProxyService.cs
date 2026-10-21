namespace MarketDataMcpServer.Services;

public class IndicatorProxyService
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;

    public IndicatorProxyService(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _baseUrl = configuration["IndicatorService:BaseUrl"]
            ?? Environment.GetEnvironmentVariable("INDICATOR_SERVICE_URL")
            ?? "http://localhost:8000";
    }

    public async Task<object> GetIndicatorAsync(string indicator, string symbol)
    {
        var response = await _httpClient.PostAsJsonAsync($"{_baseUrl.TrimEnd('/')}/indicator/{indicator}", new
        {
            symbol,
            length = 14
        });

        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<object>() ?? new { symbol, indicator };
    }
}
