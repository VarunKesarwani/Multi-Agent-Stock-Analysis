using Dapper;
using MarketDataMcpServer.Models;
using Npgsql;

namespace MarketDataMcpServer.Services;

public class MarketDataService
{
    private readonly string _connectionString;

    public MarketDataService(string connectionString)
    {
        _connectionString = connectionString;
    }

    public async Task<object?> GetCompanyAsync(string symbol)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync();

        const string sql = @"
            SELECT
                ""SYMBOL"" AS symbol,
                ""NAME_OF_COMPANY"" AS company_name,
                ""SERIES"" AS series,
                ""DATE_OF_LISTING"" AS date_of_listing,
                ""ISIN_NUMBER"" AS isin_number,
                ""FACE_VALUE"" AS face_value,
                created_at,
                updated_at
            FROM company_master
            WHERE ""SYMBOL"" = @symbol;
        ";

        return await connection.QuerySingleOrDefaultAsync(sql, new { symbol });
    }

    public async Task<IEnumerable<object>> GetEquityHistoryAsync(string symbol, int limit)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync();

        const string sql = @"
            SELECT
                ""DATE1"" AS date1,
                ""SYMBOL"" AS symbol,
                ""SERIES"" AS series,
                ""CLOSE_PRICE"" AS close_price,
                ""OPEN_PRICE"" AS open_price,
                ""HIGH_PRICE"" AS high_price,
                ""LOW_PRICE"" AS low_price,
                ""LAST_PRICE"" AS last_price,
                ""AVG_PRICE"" AS avg_price,
                ""TTL_TRD_QNTY"" AS ttl_trd_qnty,
                ""TURNOVER_LACS"" AS turnover_lacs
            FROM equity_bhavcopy
            WHERE ""SYMBOL"" = @symbol
            ORDER BY ""DATE1"" DESC
            LIMIT @limit;
        ";

        return await connection.QueryAsync(sql, new { symbol, limit });
    }

    public async Task<IEnumerable<object>> GetFoHistoryAsync(string symbol, int limit)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync();

        const string sql = @"
            SELECT
                ""DATE1"" AS date1,
                ""SYMBOL"" AS symbol,
                ""EXPIRY_DATE"" AS expiry_date,
                ""INSTRUMENT_NUMBER"" AS instrument_number,
                ""CLOSE_PRICE"" AS close_price,
                ""OPEN_PRICE"" AS open_price,
                ""HIGH_PRICE"" AS high_price,
                ""LOW_PRICE"" AS low_price,
                ""LAST_PRICE"" AS last_price,
                ""TTL_TRD_QNTY"" AS ttl_trd_qnty,
                ""TURNOVER_LACS"" AS turnover_lacs
            FROM fo_bhavcopy
            WHERE ""SYMBOL"" = @symbol
            ORDER BY ""DATE1"" DESC
            LIMIT @limit;
        ";

        return await connection.QueryAsync(sql, new { symbol, limit });
    }

    public Task<object?> GetLatestEquitySnapshotAsync(string symbol)
    {
        return GetLatestEquitySnapshotAsync(symbol, CancellationToken.None);
    }

    public async Task<object?> GetLatestEquitySnapshotAsync(string symbol, CancellationToken cancellationToken)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);

        const string sql = @"
            SELECT
                ""DATE1"" AS date1,
                ""SYMBOL"" AS symbol,
                ""SERIES"" AS series,
                ""CLOSE_PRICE"" AS close_price,
                ""OPEN_PRICE"" AS open_price,
                ""HIGH_PRICE"" AS high_price,
                ""LOW_PRICE"" AS low_price,
                ""LAST_PRICE"" AS last_price,
                ""AVG_PRICE"" AS avg_price,
                ""TTL_TRD_QNTY"" AS ttl_trd_qnty,
                ""TURNOVER_LACS"" AS turnover_lacs
            FROM equity_bhavcopy
            WHERE ""SYMBOL"" = @symbol
            ORDER BY ""DATE1"" DESC
            LIMIT 1;
        ";

        return await connection.QuerySingleOrDefaultAsync(new CommandDefinition(
            sql,
            new { symbol },
            cancellationToken: cancellationToken));
    }

    public async Task<IEnumerable<OhlcvCandle>> GetOhlcvHistoryAsync(string symbol, int limit, CancellationToken cancellationToken = default)
    {
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);

        const string sql = @"
            SELECT
                ""DATE1"" AS ""Date"",
                ""OPEN_PRICE"" AS ""Open"",
                ""HIGH_PRICE"" AS ""High"",
                ""LOW_PRICE"" AS ""Low"",
                ""CLOSE_PRICE"" AS ""Close"",
                ""TTL_TRD_QNTY"" AS ""Volume"",
                ""SYMBOL"" AS ""CompanyId""
            FROM equity_bhavcopy
            WHERE ""SYMBOL"" = @symbol
              AND ""OPEN_PRICE"" IS NOT NULL
              AND ""HIGH_PRICE"" IS NOT NULL
              AND ""LOW_PRICE"" IS NOT NULL
              AND ""CLOSE_PRICE"" IS NOT NULL
            ORDER BY ""DATE1"" DESC
            LIMIT @limit;
        ";

        return await connection.QueryAsync<OhlcvCandle>(new CommandDefinition(
            sql,
            new { symbol, limit },
            cancellationToken: cancellationToken));
    }
}
