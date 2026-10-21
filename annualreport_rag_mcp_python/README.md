# Annual Report RAG MCP Server

Read-only MCP server for retrieving cited annual-report passages from the Qdrant collection produced by
`Ingestion_AnnualReport/chunk_embedding_pipeline.py`. It uses the same Ollama embedding endpoint and
model as ingestion; it does not generate answers or modify vectors.

## Tools

| Tool | Purpose |
|---|---|
| `reports_search_annual_report` | Semantic search constrained by symbol and optional report year/type. |
| `reports_get_report_section` | Retrieve passages relevant to a named section within one symbol/year report. |

Each result contains the chunk text, similarity score, retained ingestion metadata, and a stable citation
object. Clients should cite those sources when forming an answer. Section retrieval is semantic because
the ingestion contract preserves arbitrary source metadata and does not require an exact `section` field.

## Compatibility with ingestion

Defaults deliberately match the annual-report embedding pipeline:

- Qdrant collection: `annual_reports`
- Ollama model: `nomic-embed-text`
- Ollama endpoint: `/api/embed`
- distance is determined by the existing Qdrant collection (ingestion creates it with cosine distance)
- symbol/year filters support years stored as strings or integers

For best results, run retrieval with the same `EMBEDDING_MODEL` used during ingestion.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export QDRANT_URL=http://localhost:6333
export OLLAMA_URL=http://localhost:11434
annualreport-rag-mcp
```

- MCP endpoint: `http://localhost:8003/mcp`
- Dependency health probe: `http://localhost:8003/health`

The health endpoint returns HTTP 503 while Qdrant, the configured collection, or Ollama is unavailable.

## Docker

```bash
docker build -t annualreport-rag-mcp .
docker run --rm --env-file .env -p 8003:8003 annualreport-rag-mcp
```

When Qdrant and Ollama run on the Docker host, configure their URLs with a host address reachable from
the container. Use a Qdrant API key with read-only collection access when authentication is enabled.

## Test

```bash
pytest
```

