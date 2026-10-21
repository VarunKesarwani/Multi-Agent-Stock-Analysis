namespace MarketDataMcpServer.Services;

public class PriceMovementProxyService
{
    private readonly HttpClient _httpClient;

    public PriceMovementProxyService(HttpClient httpClient)
    {
        _httpClient = httpClient;
    }

    public async Task<object?> GetLatestPriceAsync(string symbol)
    {
        var response = await _httpClient.GetAsync($"/api/price/{symbol}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<object>();
    }

    public async Task<object?> GetOhlcHistoryAsync(string symbol, int limit)
    {
        var response = await _httpClient.GetAsync($"/api/ohlc/{symbol}?limit={limit}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<object>();
    }

    public async Task<object?> GetIndicatorAsync(string indicator, string symbol, int period)
    {
        var response = await _httpClient.GetAsync($"/api/indicator/{indicator}/{symbol}?period={period}");
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<object>();
    }
}
