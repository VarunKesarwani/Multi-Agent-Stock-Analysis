# Financial Data MCP Server

Read-only MCP server for the normalized MongoDB model created by
`financial_ingestion/mongodb_financial_setup.js`. It resolves current dataset heads before querying
`financial_facts`, so superseded ingestions are not mixed into results.

## Tools

| Tool | Purpose |
|---|---|
| `financial_get_current_facts` | Fetch current normalized facts with bounded filters. |
| `financial_get_statement` | Build a period-oriented Screener statement view. |
| `financial_compare_sources` | Compare current Screener and NSE XBRL values. |
| `financial_list_metrics` | Discover available statements, metrics, labels, and units. |
| `financial_get_ingestion_status` | Inspect recent ingestion runs. |

The service intentionally does not expose arbitrary MongoDB filters, aggregation pipelines, or write
operations. Decimal128 values are returned as strings to preserve financial precision.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export MONGODB_URI='mongodb://localhost:27017/?directConnection=true'
financialdata-mcp
```

- MCP endpoint: `http://localhost:8001/mcp`
- Liveness probe: `http://localhost:8001/health`

## Docker

```bash
docker build -t financialdata-mcp .
docker run --rm --env-file .env -p 8001:8001 financialdata-mcp
```

Use a MongoDB account with read access only. Add the Docker service name or deployed hostname to
`MCP_ALLOWED_HOSTS`; entries support exact names and the SDK's `:*` port wildcard.

## Test

```bash
pytest
```

