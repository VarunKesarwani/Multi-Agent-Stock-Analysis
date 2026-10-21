using MarketDataMcpServer.Models;

namespace MarketDataMcpServer.Services;

public sealed class IndicatorCatalog
{
    private readonly IReadOnlyList<IndicatorDefinition> _indicators = new List<IndicatorDefinition>
    {
        new("sma", "calculate_sma", "trend", "Simple Moving Average", 14, true),
        new("ema", "calculate_ema", "trend", "Exponential Moving Average", 14, true),
        new("macd", "calculate_macd", "trend", "Moving Average Convergence Divergence", 14, true),
        new("supertrend", "calculate_supertrend", "trend", "SuperTrend trend-following indicator", 14, true),
        new("adx", "calculate_adx", "trend", "Average Directional Index", 14, true),
        new("aroon", "calculate_aroon", "trend", "Aroon trend strength indicator", 14, true),
        new("psar", "calculate_psar", "trend", "Parabolic SAR", 14, true),
        new("heiken_ashi", "calculate_heiken_ashi", "trend", "Heiken Ashi candles", 14, true),
        new("rsi", "calculate_rsi", "momentum", "Relative Strength Index", 14, true),
        new("stoch_rsi", "calculate_stoch_rsi", "momentum", "Stochastic RSI", 14, true),
        new("stochastic", "calculate_stochastic", "momentum", "Stochastic Oscillator", 14, true),
        new("awesome", "calculate_awesome", "momentum", "Awesome Oscillator", 14, true),
        new("williams_r", "calculate_williams_r", "momentum", "Williams Percent Range", 14, true),
        new("cci", "calculate_cci", "momentum", "Commodity Channel Index", 14, true),
        new("force", "calculate_force", "momentum", "Force Index", 14, true),
        new("mfi", "calculate_mfi", "momentum", "Money Flow Index", 14, true),
        new("elder_impulse", "calculate_elder_impulse", "momentum", "Elder Impulse System", 14, true),
        new("atr", "calculate_atr", "volatility", "Average True Range", 14, true),
        new("bollinger", "calculate_bollinger", "volatility", "Bollinger Bands", 20, true),
        new("volatility", "calculate_volatility", "volatility", "Annualized volatility", 14, true),
        new("renko", "calculate_renko", "volatility", "Renko chart values", 14, true),
        new("obv", "calculate_obv", "volume", "On-Balance Volume", 14, true),
        new("accdist", "calculate_accdist", "volume", "Accumulation Distribution", 14, true),
        new("vwap", "calculate_vwap", "volume", "Volume Weighted Average Price", 14, true),
        new("pivot", "calculate_pivot", "levels", "Pivot point support and resistance levels", 14, true),
        new("fibonacci", "calculate_fibonacci", "levels", "Fibonacci support and resistance levels", 14, true),
        new("support_resistance", "calculate_support_resistance", "levels", "Support and resistance levels", 14, true),
        new("doji", "calculate_doji", "pattern", "Doji candlestick detector", 14, true),
        new("shooting_star", "calculate_shooting_star", "pattern", "Shooting star candlestick detector", 14, true),
        new("maru_bozu", "calculate_maru_bozu", "pattern", "Maru Bozu candlestick detector", 14, true),
        new("cagr", "calculate_cagr", "performance", "Compound annual growth rate", 14, true),
        new("sharpe", "calculate_sharpe", "performance", "Sharpe ratio", 14, true),
        new("max_drawdown", "calculate_max_drawdown", "performance", "Maximum drawdown", 14, true),
        new("daily_pct_change", "calculate_daily_pct_change", "performance", "Daily percentage change series", 14, true),
        new("slope", "calculate_slope", "utility", "Regression slope angle", 5, true)
    };

    public IReadOnlyList<IndicatorDefinition> GetAll() => _indicators;

    public IndicatorDefinition? FindByIndicatorOrToolName(string name)
    {
        return _indicators.FirstOrDefault(indicator =>
            string.Equals(indicator.Name, name, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(indicator.ToolName, name, StringComparison.OrdinalIgnoreCase));
    }
}