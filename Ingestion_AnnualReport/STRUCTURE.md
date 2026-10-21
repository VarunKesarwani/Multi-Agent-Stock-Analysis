# RAG project structure

The diagram is implemented inside the existing `Ingestion_AnnualReport` project so
existing notebook imports and scripts remain usable. It is a working ingestion,
retrieval and answer service backed by Qdrant, rather than an empty folder scaffold.

| Diagram location | Implementation and responsibility |
| --- | --- |
| `README.md` | Setup, commands and architecture |
| `requirements.txt` | Runtime dependencies; optional notebook extras are separate |
| `.env` | Local secrets and overrides; copy `.env.example`, never commit `.env` |
| `.gitignore` | Excludes secrets, runtime logs, caches and local vector storage |
| `config.yaml` | Non-secret defaults for models, chunking, Qdrant and retrieval |
| `src/ingestion/loader.py` | Annual Markdown and educational PDF extraction, metadata and per-file failure handling |
| `src/ingestion/pipeline.py` | Resume, bounded batches, failed-batch isolation and ingestion orchestration |
| `src/chunking/chunker.py` | Heading/table blocks, bounded character chunks, overlap and stable point IDs |
| `src/embeddings/embedder.py` | Ollama/OpenAI embedding HTTP calls, retries and vector validation |
| `src/vectordb/vector_store.py` | Qdrant collection contracts, existing-ID lookup and persistence |
| `src/retrieval/retriever.py` | Read-only similarity search, metadata filters and source citations |
| `src/retrieval/service.py` | Retrieval → bounded prompt context → answer generation |
| `src/prompts/prompt_templates.py` | Grounded prompts with numbered sources and a context character budget |
| `src/llm/llm_client.py` | Local Ollama or OpenAI answer generation |
| `src/api/routes.py` | FastAPI `/health`, `/search` and `/ask` endpoints |
| `src/utils/helpers.py` | Rotating application logs and batching |
| `src/utils/settings.py`, `config.py`, `runtime.py` | Shared configuration loading and validation |
| `tests/test_app.py` | API, retrieval, configuration and provider contract tests |
| `logs/app.log` | Runtime log created by `main.py`; contents are ignored by Git |
| `main.py` | `ingest`, `search`, `ask`, `serve` commands |

## Compatibility and boundaries

The root `document_ingestion.py`, `chunk_embedding_pipeline.py`,
`ingestion_settings.py` and `markdown_structure.py` are compatibility facades.
Business logic lives under `src/`; existing notebooks can retain their imports.
`pdf_process.py` remains the existing annual-PDF conversion utility because it is
also called directly by notebooks. Run it before ingesting annual Markdown.
The original root regression tests are retained alongside the new `tests/` suite.

The diagram lists examples such as CSV/website loaders and Chroma/FAISS. This
implementation follows the project's actual inputs (annual reports and educational
PDFs) and existing Qdrant database. It does not add unused vector stores or scrapers.
Both document types remain in the same configured collection with distinct metadata.
This preserves the current project behavior and the user's shared-collection design.

The separately deployed `annualreport_rag_mcp_python` service is unchanged. Its
existing payload schema continues to work. It remains the MCP route for the agent;
these new HTTP endpoints provide direct local testing and integration. Its current
Ollama configuration must continue to match the ingestion model. Switching this
project to OpenAI embeddings also requires separately updating any consuming MCP
configuration/implementation to support that provider.

## Behavior and limitations

- Retrieval reuses the exact embedding configuration used for ingestion. It rejects
  mixed/unlabelled embeddings unless the existing explicit legacy opt-in is enabled.
  A missing collection returns no passages; searches never create it.
- Filters are exact matches. Use `Annual Report` for the existing annual label and
  `financial_education` for educational PDFs. Symbol is optional for education.
  Numeric year filters match both integer and string year payloads.
- Answers include `[S1]`-style source labels and the actual supplied excerpts.
  Page numbers appear only when extracted from PDF metadata. LLM-generated citation
  correctness is not independently verified; inspect returned sources when needed.
- No hits means no LLM call. `/health` checks liveness only. Dependency/configuration
  errors return HTTP 503; malformed request bodies return HTTP 422.
- Character budgets are not token budgets. Configure chunk size and context budget
  for the chosen model. Ollama embedding retains the existing truncation behavior.
- Existing append/upsert semantics are preserved: edited documents can leave older
  chunks. Use a new collection for a clean rebuild or model change; this refactor
  does not automatically delete existing points.
- PDF extraction does not add OCR. Scanned PDFs with no extractable text are logged
  as failed while other files continue. Failed-file runs exit with status 1.
- The API defaults to loopback and has no authentication. It is intended for local
  use; add authentication at a gateway before exposing it remotely.
