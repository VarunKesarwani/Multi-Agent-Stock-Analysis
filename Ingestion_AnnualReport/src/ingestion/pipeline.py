"""Resumable embedding-to-Qdrant ingestion for financial-document chunks.

The pipeline is deliberately sequential at the batch level. A single local Ollama
instance is normally more stable with small input batches than with many concurrent
requests. Failed batches are retried and then divided until a bad input is isolated,
so one chunk cannot terminate the complete ingestion run.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.chunking.chunker import prepare_chunks
from src.embeddings.embedder import EmbeddingClient
from src.utils.config import PipelineConfig
from src.utils.helpers import _batched
from src.vectordb.vector_store import VectorStore

if TYPE_CHECKING:
    import requests as requests_types


LOG = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    input_chunks: int
    prepared_chunks: int
    skipped_existing: int = 0
    stored: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnnualReportEmbeddingPipeline:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        session: "requests_types.Session | None" = None,
        qdrant_client: "QdrantClient | None" = None,
    ) -> None:
        self.config = config or PipelineConfig.from_env()
        self.config.validate()
        self.session = session or requests.Session()
        self.qdrant = qdrant_client or QdrantClient(
            url=self.config.qdrant_url,
            api_key=self.config.qdrant_api_key,
            timeout=self.config.qdrant_timeout_seconds,
        )

    @property
    def embed_url(self):
        return EmbeddingClient(self.config, self.session).embed_url

    def _embed_once(self, texts):
        return EmbeddingClient(self.config, self.session)._embed_once(texts)

    _validate_vectors = staticmethod(EmbeddingClient._validate_vectors)

    def close(self) -> None:
        """Release HTTP and Qdrant connections after a run."""
        self.session.close()
        self.qdrant.close()

    def embed_texts(self, texts):
        return EmbeddingClient(self.config, self.session).embed_texts(texts)

    def _embed_resilient(
        self, batch: Sequence[dict[str, Any]]
    ) -> tuple[
        list[tuple[dict[str, Any], list[float]]], list[tuple[dict[str, Any], str]]
    ]:
        """Recursively divide a failed batch until the bad chunk is isolated."""
        try:
            vectors = self.embed_texts([chunk["text"] for chunk in batch])
            return list(zip(batch, vectors)), []
        except RuntimeError as error:
            if len(batch) == 1:
                return [], [(batch[0], str(error))]
            midpoint = len(batch) // 2
            LOG.info(
                f"Embedding batch of {len(batch)} failed; retrying as "
                f"{midpoint} + {len(batch) - midpoint} inputs."
            )
            left_ok, left_failed = self._embed_resilient(batch[:midpoint])
            right_ok, right_failed = self._embed_resilient(batch[midpoint:])
            return left_ok + right_ok, left_failed + right_failed

    def _collection_exists(self):
        return VectorStore(self.config, self.qdrant)._collection_exists()

    def _ensure_collection(self, vector_size):
        return VectorStore(self.config, self.qdrant)._ensure_collection(vector_size)

    def _check_embedding_contract(self):
        return VectorStore(self.config, self.qdrant)._check_embedding_contract()

    def _existing_ids(self, chunks):
        return VectorStore(self.config, self.qdrant)._existing_ids(chunks)

    def _write_failures(self, failures: Sequence[tuple[dict[str, Any], str]]) -> None:
        if not failures:
            return
        path = Path(self.config.failure_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as handle:
            for chunk, error in failures:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": timestamp,
                            "point_id": chunk["point_id"],
                            "source_file": chunk.get("source_file"),
                            "original_chunk_id": chunk.get("original_chunk_id"),
                            "chunk_part": chunk.get("chunk_part"),
                            "characters": len(chunk["text"]),
                            "error": error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def run(self, chunks: Sequence[dict[str, Any]]) -> IngestionSummary:
        started = time.monotonic()
        prepared = prepare_chunks(
            chunks,
            self.config.max_chunk_chars,
            self.config.chunk_overlap_chars,
        )
        summary = IngestionSummary(
            input_chunks=len(chunks),
            prepared_chunks=len(prepared),
        )
        self._check_embedding_contract()
        for chunk in prepared:
            chunk["embedding_type"] = self.config.embedding_type
            chunk["embedding_model"] = self.config.embedding_model
            chunk["chunk_size_chars"] = self.config.max_chunk_chars
            chunk["chunk_overlap_chars"] = self.config.chunk_overlap_chars
        existing_ids = self._existing_ids(prepared)
        pending = [chunk for chunk in prepared if chunk["point_id"] not in existing_ids]
        summary.skipped_existing = len(prepared) - len(pending)

        LOG.info(
            f"Prepared {len(prepared)} bounded chunks from {len(chunks)} inputs; "
            f"{summary.skipped_existing} already stored, {len(pending)} pending."
        )
        if not pending:
            summary.elapsed_seconds = time.monotonic() - started
            return summary

        completed = 0
        for batch_number, batch in enumerate(
            _batched(pending, self.config.embed_batch_size), start=1
        ):
            batch_started = time.monotonic()
            embedded, failures = self._embed_resilient(batch)

            if embedded:
                self._ensure_collection(len(embedded[0][1]))
                VectorStore(self.config, self.qdrant).upsert(embedded)
                summary.stored += len(embedded)

            self._write_failures(failures)
            summary.failed += len(failures)
            completed += len(batch)
            elapsed = time.monotonic() - started
            rate = completed / elapsed if elapsed else 0.0
            remaining = len(pending) - completed
            eta = remaining / rate if rate else 0.0
            LOG.info(
                f"Batch {batch_number}: {completed}/{len(pending)} pending chunks "
                f"handled ({summary.stored} stored, {summary.failed} failed) | "
                f"batch {time.monotonic() - batch_started:.1f}s | ETA {eta / 60:.1f}m"
            )

        summary.elapsed_seconds = time.monotonic() - started
        return summary

    def query(self, text: str, limit: int = 5, *, document_type: str | None = None):
        """Embed a query with the same model and search the configured collection."""
        self._check_embedding_contract()
        vector = self.embed_texts([text])[0]
        self._ensure_collection(len(vector))
        return self.qdrant.query_points(
            collection_name=self.config.collection_name,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="document_type", match=MatchValue(value=document_type)
                    )
                ]
            )
            if document_type
            else None,
            limit=limit,
            with_payload=True,
        )
