# Financial ingestion

Two manual notebooks publish structural source JSON to separate RabbitMQ routes. A Python consumer normalizes each incoming message and writes source snapshots, filings, facts, issues, and run status to MongoDB.

| Input | Notebook | RabbitMQ routing key | Consumer normalizer |
| --- | --- | --- | --- |
| Screener | `ingestion_screener/load_financial_data.ipynb` | `screener` | `ScreenerNormalizer` |
| NSE XBRL | `ingestion_xblr/nse_xbrl_downloader_with_normalization.ipynb` | `xblr` | `XbrlNormalizer` |

The XBRL filename is retained for familiarity; it performs structural XML parsing only. Canonical financial normalization is entirely in `financial_ingestion/normalizers.py`. The package's `extractors.py` and `producers.py` are the single shared extraction and RabbitMQ publishing implementation. There are no CLI producer commands.

## Run locally

1. Put symbols in the repository-root `StockAnalysis_AI/symbols.csv` with a `symbol` header. Both notebooks resolve this file through the editable local package, regardless of the Jupyter working directory.
2. Create a local `.env` in this directory. Set `RABBITMQ_USER` and `RABBITMQ_PASSWORD`; `Settings.from_env()` reads this file and builds a local AMQP URL, encoding special characters such as `#`. These credentials take precedence over any `RABBITMQ_URL` in the process. Alternatively, set an already URL-encoded `RABBITMQ_URL` when the username and password are not supplied. Set `MONGO_URI` if running locally outside Compose and `POSTGRES_DSN` for the XBRL notebook. Process environment variables take precedence over `.env`. The XBRL notebook uses PostgreSQL only to resolve `NAME_OF_COMPANY` for each symbol. Never put credentials in notebooks.
3. From this directory install the notebook environment: `python -m pip install -e '.[notebook]'`.
4. Run `docker compose up --build -d`; Compose reads `RABBITMQ_USER` and `RABBITMQ_PASSWORD` from `.env` or your shell. The consumer image initializes RabbitMQ routing and MongoDB collections before consuming. If using external services, run `financial-ingestion init-rabbit`, `financial-ingestion init-mongo`, then `financial-ingestion consume`.
5. Run either notebook manually. Each notebook reads `symbols.csv`, continues after per-company or per-filing errors, and publishes immediately. Failures are logged. A failed RabbitMQ publication stays in the producer's durable `archive` outbox; rerun `financial-ingestion publish-pending` after recovering the broker.

The notebooks read this directory's `.env` through `Settings.from_env()`. With the included Compose stack, `RABBITMQ_USER` and `RABBITMQ_PASSWORD` connect to `localhost:5672`; the container connects to `rabbitmq:5672` with the same credentials. To use a full URL instead, set `RABBITMQ_URL=amqp://USER:URL_ENCODED_PASSWORD@localhost:5672/%2F`. MongoDB in Compose is available to host tools at `mongodb://localhost:27017/`, while the consumer uses `mongodb://mongo:27017/`. `POSTGRES_DSN` is needed only for XBRL.

## Screener request pacing

The shared fetch layer reuses the notebook's HTTP session and waits between
requests, including retries, standalone fallback requests and the next symbol
after an error. Run one Screener notebook at a time: pacing is per session, not
a distributed limit across processes. Restart the notebook kernel after updating
the editable package so the new fetch code is loaded.

Add these optional settings to `financial_ingestion/.env` (defaults shown):

```dotenv
SCREENER_REQUEST_DELAY_SECONDS=100
SCREENER_REQUEST_JITTER_SECONDS=5
SCREENER_MAX_ATTEMPTS=3
SCREENER_BACKOFF_SECONDS=30
SCREENER_MAX_BACKOFF_SECONDS=120
SCREENER_FAILURE_COOLDOWN_SECONDS=300
```

Normal requests wait 100–105 seconds after the previous response, preserving
the existing notebook's conservative success delay and applying it to failures
too. Increase `SCREENER_REQUEST_DELAY_SECONDS` to slow down further. These are
local defaults, not a guaranteed Screener rate limit. HTTP 500 does not by itself prove
rate limiting. Transient HTTP 429/500/502/503/504 responses and connection/timeouts
retry up to three total attempts, with exponential backoff and jitter. The
backoff cap applies before jitter; a longer `Retry-After` (seconds or HTTP date)
is honored. After exhausting transient retries, the shared session keeps a
five-minute cooldown before the next symbol. Failed symbols are logged and the
loop continues; rerun failed symbols later by selecting them in `symbols.csv`.

401/403 and other permanent HTTP errors are not retried. Only an explicit 404
on the consolidated page triggers the existing standalone fallback. Error pages
are never published. HTML parsing, archival and RabbitMQ payloads are unchanged.
Do not add HTTPAdapter retries or parallel fetching on top of this retry loop.

## MongoDB queries

```javascript
use financial_ingestion
// Most recent selected Screener dataset for a symbol
const head = db.screener_snapshots.findOne({kind:'head', symbol:'INDOMIM', source:'SCREENER'});
db.financial_facts.find({dataset_id:head.dataset_id}).sort({period_end:-1}).limit(20);
// Inspect unmapped labels or invalid rows
db.screener_snapshots.find({kind:'issues', dataset_id:head.dataset_id});
```

For XBRL use `financial_filings` instead of `screener_snapshots`. Raw source envelopes are preserved in the corresponding dataset documents. Unmapped numeric labels retain their source names; unresolved rows are recorded in issue documents. Valid facts are stored even if another row is unresolved; a dataset with blocking structural issues is not selected as the current head. Percentages are stored as percentage points; monetary Screener figures use the explicitly parsed page heading to convert crores/lakhs to INR. Calculated financial ratios are outside this ingestion service.

RabbitMQ `screener` and `xblr` are topic exchange routing keys bound to distinct durable queues. On processing errors messages move to a failed queue after retries; the consumer continues with other messages. Inspect `financial-ingestion replay-failed screener --limit 1` or use `xblr` after correcting the cause. Docker Compose is for local use; adjust credentials and persistence for the deployment host.


## Repair null Screener head pointers

Older Screener ingestions can leave current head pointers unpublished when the optional shareholding section fails even though core financial facts normalized successfully. New ingestion treats a shareholding-only failure as non-blocking; failures in core financial sections remain blocking.

After deploying this change, repair existing null Screener heads with:

```powershell
cd C:\\Repo\\StockAnalysis_AI\\financial_ingestion
docker exec -i financial_ingestion-mongo-1 mongosh financial_ingestion --quiet < scripts/repair_screener_heads.js
```

The repair is conservative: it only selects datasets that contain VALID facts and whose only blocking issue is `tables.shareholding` with code `FAILED`. It prints repaired/skipped counts and leaves other null heads untouched for investigation.

Validate afterward:

```powershell
docker exec -it financial_ingestion-mongo-1 mongosh financial_ingestion --quiet --eval "print('Remaining null Screener heads: ' + db.screener_snapshots.countDocuments({kind:'head',source:'SCREENER',dataset_id:null}));"
```
