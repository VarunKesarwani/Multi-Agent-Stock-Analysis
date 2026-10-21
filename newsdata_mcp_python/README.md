# News Data MCP Server

Read-only MCP server for Ollama-enriched news indexed in Elasticsearch. It follows the event contract
from `Ingestion_News`: title, RSS summary, category, publication time, generated summary, overall tone,
and company-specific tones.

## Tools

| Tool | Purpose |
|---|---|
| `news_search` | Full-text search with category, source, tone, company, and date filters. |
| `news_get_company_news` | Fetch enriched articles associated with one ticker symbol. |
| `news_get_tone_summary` | Count tone and average confidence overall or for one company. |
| `news_get_timeline` | Aggregate article count and overall tone over time. |
| `news_list_categories` | Discover indexed news categories. |

The index name is deliberately configurable because the repository does not yet define the Kafka
Elasticsearch sink connector's target index. The default is `news-enriched-*`.

Expected keyword-capable fields are `category`, `source`, `enrichment_status`, `analysis.overall_tone`,
and `analysis.company_tones.symbol`. Standard Elasticsearch dynamic mappings expose these as `.keyword`.
For stable production behavior, define an explicit index template before enabling the sink connector.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export ELASTICSEARCH_URL=http://localhost:9200
export ELASTICSEARCH_INDEX='news-enriched-*'
newsdata-mcp
```

- MCP endpoint: `http://localhost:8002/mcp`
- Liveness probe: `http://localhost:8002/health`

## Docker

```bash
docker build -t newsdata-mcp .
docker run --rm --env-file .env -p 8002:8002 newsdata-mcp
```

Use Elasticsearch credentials with read privileges only. Add the Docker service name or deployed
hostname to `MCP_ALLOWED_HOSTS`.

## Test

```bash
pytest
```

