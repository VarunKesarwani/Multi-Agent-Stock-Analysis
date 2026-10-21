# StockAnalysis_AI command reference

Windows PowerShell commands. Repository root: `C:\Repo\StockAnalysis_AI`.
Updated 2026-10-04 from project chat history and current repository entry points.
Commands were inspected, not executed against the local Windows services or databases.

Run each foreground server/worker in a separate terminal. Configure each project's
local environment first; process environment variables may override .env values.
Do not run the same producer/consumer both locally and in Docker unless intentional.

Startup order: Docker infrastructure → required ingestion workers → MCP servers →
AI agent → DevUI. Historical ingestion jobs need not remain running to query stored data.

## 1. Docker health and diagnostics

Containers, rather than images, have a running/health status.

~~~powershell
cd C:\Repo\StockAnalysis_AI
docker info
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker compose ls -a

Get-ChildItem -Path . -Recurse -File -Include compose.yml,compose.yaml,docker-compose.yml,docker-compose.yaml |
  Select-Object -ExpandProperty FullName
~~~

Inspect a selected container; replace the example name with the actual name shown above:

~~~powershell
docker inspect --format '{{json .State}}' ingestion_news-connect-1
docker logs --tail 100 ingestion_news-connect-1
~~~

Running means the process is running; healthy requires a configured health check.
Restarting indicates repeated exits. TCP connectivity alone does not prove authentication,
query access, or data readiness.

~~~powershell
# PostgreSQL, Kafka, RabbitMQ, MongoDB
Test-NetConnection 127.0.0.1 -Port 5432
Test-NetConnection 127.0.0.1 -Port 29092
Test-NetConnection 127.0.0.1 -Port 5672
Test-NetConnection 127.0.0.1 -Port 27017

Invoke-RestMethod http://127.0.0.1:6333/collections | ConvertTo-Json -Depth 10
# Included local Elasticsearch stack has security disabled
Invoke-RestMethod "http://127.0.0.1:9200/_cluster/health?pretty"
Invoke-RestMethod http://127.0.0.1:8083/connectors
~~~

## 2. Start stopped containers / Compose stacks

Start one existing stopped container (replace the placeholder):

~~~powershell
docker start <container-name>
~~~

Start configured stacks from their own folders so project .env files are resolved consistently.
Whole-stack startup can also start ingestion workers.

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_Price
docker compose up -d
docker compose ps -a

cd C:\Repo\StockAnalysis_AI\financial_ingestion
docker compose up -d
docker compose ps -a

cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose up -d
docker compose ps -a

cd C:\Repo\StockAnalysis_AI\Ingestion_AnnualReport
docker compose -f .\compose.yml up -d
docker compose -f .\compose.yml ps -a
~~~

Inspect the previously failing services before repeatedly restarting:

~~~powershell
cd C:\Repo\StockAnalysis_AI\financial_ingestion
docker compose logs --tail 100 consumer

cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose logs --tail 100 connect
~~~

After correcting configuration, rebuild changed worker images when needed:

~~~powershell
cd C:\Repo\StockAnalysis_AI\financial_ingestion
docker compose up -d --build consumer

cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose up -d --build connect
~~~

## 3. Individual ingestion projects

### 3.1 Price ingestion

Use the configured PostgreSQL connection and installed project dependencies.

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_Price
python .\main.py --help
python .\main.py
~~~

Alternative: the previously used equity/F&O backfill. Adjust the dates to the required window.
This skips company master, company market, and Screener stages.

~~~powershell
python .\main.py --skip-company-master --skip-company-market --skip-screener --start-date 2026-03-30 --end-date 2026-09-30 --fo-start-date 2026-03-30 --fo-end-date 2026-09-30
~~~

### 3.2 Screener ingestion

Verified in financial_ingestion/README.md: producers are manual notebooks; there are
no standalone producer CLI commands. Use repository-root symbols.csv with a symbol header.
Configure financial_ingestion/.env with RabbitMQ credentials.

~~~powershell
cd C:\Repo\StockAnalysis_AI\financial_ingestion
python -m pip install -e ".[notebook]"
docker compose up --build -d
docker compose logs -f --tail 100 consumer
~~~

Open `financial_ingestion/ingestion_screener/load_financial_data.ipynb`
in VS Code/Jupyter, select the Python environment containing the editable package,
and run its cells. Run one Screener notebook at a time to preserve request pacing.

### 3.3 XBRL ingestion

Use the same financial_ingestion setup and Docker consumer.
Configure POSTGRES_DSN in financial_ingestion/.env for company-name lookup.

Open `financial_ingestion/ingestion_xblr/nse_xbrl_downloader_with_normalization.ipynb`
and run its cells with the same environment. The notebook publishes to the
`xblr` routing key; this spelling is intentional in the existing code.

Local consumer alternative, when using external services instead of the Docker consumer:

~~~powershell
cd C:\Repo\StockAnalysis_AI\financial_ingestion
financial-ingestion init-rabbit
financial-ingestion init-mongo
financial-ingestion consume
~~~

This requires local MONGO_URI and RabbitMQ settings. Initialization is setup work;
normal subsequent runs need only consume. After a broker failure, publish saved outbox messages:

~~~powershell
financial-ingestion publish-pending
~~~

### 3.4 Annual Report PDF to Markdown

Verified against Ingestion_AnnualReport/pdf_process.py. Configure the annual PDF,
symbols CSV, Markdown output, and summary paths through the project's document settings.

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_AnnualReport
python .\pdf_process.py
~~~

Successful duplicate conversions are skipped. Deliberate reprocessing only:

~~~powershell
python .\pdf_process.py --force
~~~

### 3.5 Annual Report chunking and embedding

Ensure configured Markdown/education input directories exist and contain the intended files.
Earlier runs failed because those configured directories were missing.

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_AnnualReport
docker compose -f .\compose.yml up -d
python .\main.py --env .env ingest

Invoke-RestMethod http://127.0.0.1:6333/collections | ConvertTo-Json -Depth 10
~~~

Optional RAG HTTP API (previously port 8000):

~~~powershell
python .\main.py --env .env serve
~~~

A 404 at / alone does not mean the API failed to start.

### 3.6 News ingestion

For host-run producer/enrichment, start infrastructure explicitly:

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose up -d kafka elasticsearch
docker compose ps -a
~~~

Producer, in its own terminal:

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_News
$env:KAFKA_BOOTSTRAP_SERVERS = '127.0.0.1:29092'
python .\news_producer.py
~~~

Alternatively run the producer in Docker, not both:

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose up -d --build news-producer
~~~

Enrichment consumer, in a separate terminal, using the configured LLM provider:

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_News
$env:KAFKA_BOOTSTRAP_SERVERS = '127.0.0.1:29092'
python .\news_enrichment_consumer.py
~~~

Elasticsearch sink: Kafka Connect, not a separate Python sink script.

~~~powershell
cd C:\Repo\StockAnalysis_AI\Ingestion_News
docker compose up -d --build connect
Invoke-RestMethod http://127.0.0.1:8083/connector-plugins
Invoke-RestMethod http://127.0.0.1:8083/connectors
Invoke-RestMethod http://127.0.0.1:8083/connectors/news-elasticsearch-sink/status |
  ConvertTo-Json -Depth 10
~~~

The status command requires an already registered connector. If absent, use the registration
instructions in Ingestion_News/README.md and kafka-connect/news-elasticsearch-sink.json.

Optional monitoring UIs:

~~~powershell
docker compose up -d kibana kafka-ui
~~~

Kibana: http://127.0.0.1:5601. Kafka UI: http://127.0.0.1:8084 by default.

## 4. MCP projects

| Server | Port | Notes |
| --- | --- | --- |
| C# market/price | 5000 | Existing agent default |
| Financial Python | 8001 | MongoDB |
| News Python | 8002 | Elasticsearch |
| Annual Report RAG Python | 8003 | Qdrant and embeddings |
| Python market/price | 8004 | Stage-one parallel migration |
| Kite | Remote | https://mcp.kite.trade/mcp |

Python launch commands use project .venv environments. Create/install once (or reinstall
after dependency changes); run the executable for subsequent launches. Ports depend on
project configuration unless explicitly set below.

### 4.1 Existing C# market/price MCP

~~~powershell
cd C:\Repo\StockAnalysis_AI\marketdata-mcp-csharp
python -m pip install pandas numpy statsmodels stocktrends
$env:PythonIndicators__Executable = (Get-Command python).Source

$credential = Get-Credential -UserName postgres -Message 'Enter your PostgreSQL password'
$env:ConnectionStrings__DefaultConnection = "Host=localhost;Port=5432;Database=StockAnalysis_Bhavcopy;Username=postgres;Password=`"$($credential.GetNetworkCredential().Password)`""

dotnet restore
dotnet run --urls http://localhost:5000
~~~

Indicator smoke check, in another terminal:

~~~powershell
curl.exe -i "http://localhost:5000/api/indicator/rsi/TCS?period=14&limit=250"
~~~

A prior RSI request returned 502 from the Python runner. Starting the C# host alone does
not establish indicator correctness.

### 4.2 Python market/price MCP — parallel migration

The repository now contains stage one: EQ prices plus EMA, RSI, and MACD.
Keep the C# server available while validating; no automatic agent cutover.

~~~powershell
cd C:\Repo\StockAnalysis_AI\marketdata_mcp_python
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

$env:PGHOST = 'localhost'
$env:PGPORT = '5432'
$env:PGDATABASE = 'StockAnalysis_Bhavcopy'
$credential = Get-Credential -UserName postgres -Message 'Enter PostgreSQL credentials'
$env:PGUSER = $credential.UserName
$env:PGPASSWORD = $credential.GetNetworkCredential().Password
$env:MARKET_SERIES = 'EQ'

.\.venv\Scripts\marketdata-validate.exe --symbol TCS --limit 250
$env:MCP_PORT = '8004'
.\.venv\Scripts\marketdata-mcp.exe
~~~

In another terminal:

~~~powershell
Invoke-RestMethod http://127.0.0.1:8004/health
Invoke-RestMethod http://127.0.0.1:8004/health/ready
cd C:\Repo\StockAnalysis_AI\marketdata_mcp_python
.\.venv\Scripts\python.exe -m marketdata_mcp.smoke --symbol TCS
~~~

PG* variables are required in every terminal doing direct DB validation. The client smoke
terminal does not need them. The project's .env.example is documentation, not automatically loaded.
See marketdata_mcp_python/README.md for optional agent cutover and rollback.

### 4.3 Financial MCP

~~~powershell
cd C:\Repo\StockAnalysis_AI\financialdata_mcp_python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:MONGODB_URI = 'mongodb://localhost:27017/?directConnection=true'
.\.venv\Scripts\financialdata-mcp.exe
~~~

### 4.4 News MCP

~~~powershell
cd C:\Repo\StockAnalysis_AI\newsdata_mcp_python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:ELASTICSEARCH_URL = 'http://localhost:9200'
$env:ELASTICSEARCH_INDEX = 'news-enriched-*'
.\.venv\Scripts\newsdata-mcp.exe
~~~

### 4.5 Annual Report RAG MCP

~~~powershell
cd C:\Repo\StockAnalysis_AI\annualreport_rag_mcp_python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:QDRANT_URL = 'http://localhost:6333'
$env:OLLAMA_URL = 'http://localhost:11434'
.\.venv\Scripts\annualreport-rag-mcp.exe
~~~

### 4.6 Kite MCP

Remote service; no local server launch. With the agent running and Kite configured:

~~~powershell
$body = @{ arguments = @{} } | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri 'http://localhost:8080/api/mcp/tools/kite__login/invoke' -Method Post -ContentType 'application/json' -Body $body |
  ConvertTo-Json -Depth 20
~~~

Open the returned broker login URL yourself and complete login.

## 5. AI agent + MCP client manager

Start the required MCP servers and Ollama first. Select an installed tool-capable model;
qwen2.5-coder:7b is retained from the existing command file.

~~~powershell
ollama list
cd C:\Repo\StockAnalysis_AI\stockanalysis_agent_csharp
$env:Agent__Enabled = 'true'
$env:Agent__Endpoint = 'http://localhost:11434/'
$env:Agent__Model = 'qwen2.5-coder:7b'

# Enable annual_reports only after its endpoint/tool names are verified.
# This index matches the existing server configuration; recheck after reordering it.
$env:McpClientManager__Servers__3__Enabled = 'true'

dotnet restore
dotnet run --urls http://localhost:8080
~~~

Connection and readiness checks, in another terminal:

~~~powershell
Invoke-RestMethod http://localhost:8080/api/mcp/servers | ConvertTo-Json -Depth 10
Invoke-RestMethod http://localhost:8080/api/mcp/tools | ConvertTo-Json -Depth 20
Invoke-RestMethod http://localhost:8080/health/ready
~~~

Tool discovery does not independently prove every tool call or LLM response succeeds.

~~~powershell
$body = @{
  mode = 'short_term'
  message = 'Analyze TCS momentum for a 1 to 4 week holding period using MACD, EMA 5/13/21/55, volume, RSI and latest news.'
} | ConvertTo-Json

Invoke-RestMethod -Uri 'http://localhost:8080/api/agent/chat' -Method Post -ContentType 'application/json' -Body $body |
  ConvertTo-Json -Depth 20
~~~

The Python market stage-one server supports only its documented indicator subset.
Inspect actual tool results and response status before interpreting an analysis.

## 6. DevUI

Keep the agent on port 8080 running, then use another terminal:

~~~powershell
cd C:\Repo\StockAnalysis_AI
dotnet restore .\stockanalysis_devui_csharp\StockAnalysis.DevUI.csproj
dotnet run --project .\stockanalysis_devui_csharp\StockAnalysis.DevUI.csproj --launch-profile DevUI
~~~

Open http://127.0.0.1:8081/devui and select short_term, long_term, portfolio, or tax.
DevUI uses the existing agent's LLM and MCP connections; it has no separate model configuration.

Optional backend override, set in the DevUI terminal before launching:

~~~powershell
$env:AgentApi__BaseUrl = 'http://127.0.0.1:8080/'
~~~

Both processes must run on the same machine; the DevUI adapter accepts loopback origins.
Each request is independent, so include the needed symbols, dates, and context in each message.
