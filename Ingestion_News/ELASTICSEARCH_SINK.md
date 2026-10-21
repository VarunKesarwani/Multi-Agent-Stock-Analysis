# Elasticsearch news sink

## Run Elasticsearch locally

From `Ingestion_News`, start the single-node Elasticsearch service:

```bash
docker compose up -d elasticsearch
curl http://localhost:9200
```

The API is exposed only on the host's `127.0.0.1:9200`; containers on
this Compose network can use `http://elasticsearch:9200`. The named volume
`news_elasticsearch_data` retains indexed data across container restarts.
This local setup disables Elasticsearch authentication. Do not expose its port
to a public interface.

Starting Elasticsearch does not move news from Kafka into an index. Apply the
index template below, then run a Kafka Connect worker with the Elasticsearch
sink plugin and register the checked-in connector. Kafka and Kafka Connect are included in this Compose file. The connector is
registered separately, after the worker is healthy.

The sink writes enriched Kafka topics to Elasticsearch indices consumed by
`newsdata_mcp_python`.

## Start Connect and register the sink from PowerShell

Run these commands from `Ingestion_News` after setting up Kafka and
Elasticsearch. The first build downloads the Elasticsearch sink plugin:

```powershell
docker compose up -d --build connect
Invoke-RestMethod http://localhost:8083/connector-plugins
```

Wait until the REST call returns a plugin list containing
`io.confluent.connect.elasticsearch.ElasticsearchSinkConnector`. Apply the
template before starting the connector:

```powershell
Invoke-RestMethod -Method Put `
  -Uri "http://localhost:9200/_index_template/news-enriched-v1" `
  -ContentType "application/json" `
  -InFile ".\elasticsearch\news-enriched-index-template.json"

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8083/connectors" `
  -ContentType "application/json" `
  -InFile ".\kafka-connect\news-elasticsearch-sink.json"

Invoke-RestMethod http://localhost:8083/connectors/news-elasticsearch-sink/status
```

A second POST returns a conflict when the connector already exists; inspect
its status rather than registering a duplicate. The worker must remain
running to move `news_enriched_*` events into Elasticsearch.

## Topic and index mapping

| Kafka topic | Elasticsearch index |
|---|---|
| `news_enriched_economy` | `news-enriched-economy` |
| `news_enriched_markets` | `news-enriched-markets` |
| `news_enriched_business` | `news-enriched-business` |
| `news_enriched_technology` | `news-enriched-technology` |
| `news_enriched_finance` | `news-enriched-finance` |

The RegexRouter transformation performs this conversion. The MCP server's
default `ELASTICSEARCH_INDEX=news-enriched-*` therefore covers every category.

## Apply the mapping before starting the connector

```bash
curl --fail-with-body \
  -X PUT http://localhost:9200/_index_template/news-enriched-v1 \
  -H 'Content-Type: application/json' \
  --data-binary @elasticsearch/news-enriched-index-template.json
```

The mapping is strict so an unexpected event-schema change cannot silently
produce a wrong field type. It explicitly supports both `COMPLETED` records and
the `FAILED` records produced when Ollama enrichment fails.

For a multi-node Elasticsearch environment, change `number_of_replicas` from
`0` to at least `1`. The checked-in value is intended for this project's local,
single-node environment.

## Create the DLQ

Create the DLQ explicitly so its partition count and retention are controlled:

```bash
kafka-topics --bootstrap-server localhost:29092 \
  --create --if-not-exists \
  --topic news_elasticsearch_sink_dlq \
  --partitions 1 \
  --replication-factor 1 \
  --config retention.ms=1209600000
```

The example retains failed records for 14 days. Increase the replication factor
for a multi-broker cluster.

## Register the sink connector

The checked-in connector configuration uses `http://elasticsearch:9200`,
which the Compose Connect worker can resolve on the shared network.
Add `connection.username` and `connection.password` through a Kafka Connect
secrets/config provider when Elasticsearch authentication is enabled; do not
commit credentials to this JSON file.

```bash
curl --fail-with-body \
  -X POST http://localhost:8083/connectors \
  -H 'Content-Type: application/json' \
  --data-binary @kafka-connect/news-elasticsearch-sink.json
```

For an existing connector, send only the inner `config` object to:

```text
PUT /connectors/news-elasticsearch-sink/config
```

## Delivery and failure behavior

- `news_id` is already the Kafka string key. With `key.ignore=false`, it becomes
  the Elasticsearch document `_id`.
- `write.method=INSERT` replaces the full document and uses Kafka-offset-based
  external versioning. Replays do not create duplicate articles, and stale
  writes cannot overwrite a later record.
- `schema.ignore=true` prevents the schema-less JSON converter from asking the
  connector to infer mappings; the explicit index template owns the mapping.
- Malformed documents are logged at WARN, copied to the DLQ, and skipped so one
  bad article does not stop the pipeline.
- `flush.synchronously=true` is required because the RegexRouter changes the
  destination index name.

## Validate

```bash
curl --fail-with-body http://localhost:8083/connectors/news-elasticsearch-sink/status
curl --fail-with-body http://localhost:9200/_index_template/news-enriched-v1
curl --fail-with-body 'http://localhost:9200/news-enriched-*/_count'
curl --fail-with-body 'http://localhost:9200/news-enriched-*/_mapping'
```

The first indexed document creates its category index using the template. If an
index already exists with a dynamic mapping, applying the template does not
retroactively change it. Reindex that data into a newly created matching index
before enabling this sink.
