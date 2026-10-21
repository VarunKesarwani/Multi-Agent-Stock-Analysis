"""Qdrant persistence and embedding-space compatibility checks."""

import logging
from typing import Any, Sequence

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
    PointStruct,
    VectorParams,
)

from src.utils.helpers import _batched


def create_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    """Build a Qdrant payload while retaining useful source metadata."""
    excluded = {"point_id"}
    payload = {key: value for key, value in chunk.items() if key not in excluded}
    payload["content_type"] = payload.pop("type", payload.get("content_type"))
    return payload


LOG = logging.getLogger(__name__)


class VectorStore:
    """Use a caller-owned Qdrant client with the configured collection."""

    def __init__(self, config, qdrant):
        self.config = config
        self.qdrant = qdrant

    def _collection_exists(self) -> bool:
        return bool(self.qdrant.collection_exists(self.config.collection_name))

    def _ensure_collection(self, vector_size: int) -> None:
        if not self._collection_exists():
            self.qdrant.create_collection(
                collection_name=self.config.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            LOG.info(
                f"Created Qdrant collection '{self.config.collection_name}' "
                f"with vector size {vector_size}."
            )
            return

        info = self.qdrant.get_collection(self.config.collection_name)
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, dict):
            raise ValueError(
                "This pipeline requires an unnamed dense-vector collection"
            )
        if vectors_config.distance != Distance.COSINE:
            raise ValueError("This pipeline requires a cosine-distance collection")
        existing_size = getattr(vectors_config, "size", None)
        if existing_size is not None and existing_size != vector_size:
            raise ValueError(
                f"Collection '{self.config.collection_name}' expects vectors of size "
                f"{existing_size}, but model '{self.config.embedding_model}' returned "
                f"{vector_size}. Use a new collection or the original embedding model."
            )

    def _check_embedding_contract(self) -> None:
        """Reject mixed embedding spaces, even when vector dimensions match."""
        if not self._collection_exists():
            return
        compatible = [
            Filter(
                must=[
                    FieldCondition(
                        key="embedding_type",
                        match=MatchValue(value=self.config.embedding_type),
                    ),
                    FieldCondition(
                        key="embedding_model",
                        match=MatchValue(value=self.config.embedding_model),
                    ),
                ]
            )
        ]
        if self.config.allow_legacy_embeddings:
            compatible.append(
                Filter(
                    must=[
                        IsEmptyCondition(is_empty=PayloadField(key="embedding_type")),
                        IsEmptyCondition(is_empty=PayloadField(key="embedding_model")),
                    ]
                )
            )
        records, _ = self.qdrant.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(must_not=[Filter(should=compatible)]),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        if records:
            raise ValueError(
                "Collection contains another embedding model or unlabelled legacy vectors. "
                "Use a new collection. Only set ALLOW_LEGACY_EMBEDDINGS=true after "
                "confirming legacy vectors used this exact provider and model."
            )

    def _existing_ids(self, chunks: Sequence[dict[str, Any]]) -> set[str]:
        if not self.config.skip_existing or not self._collection_exists():
            return set()
        existing: set[str] = set()

        # Current format: stable content-derived UUID point IDs.
        for batch in _batched(chunks, self.config.qdrant_lookup_batch_size):
            records = self.qdrant.retrieve(
                collection_name=self.config.collection_name,
                ids=[chunk["point_id"] for chunk in batch],
                with_payload=False,
                with_vectors=False,
            )
            existing.update(str(record.id) for record in records)

        # Legacy notebook format: integer IDs copied directly from chunk_id.
        # Only skip a legacy point when its source and complete text still match;
        # this prevents a reordered input directory from skipping the wrong chunk.
        legacy_candidates = [
            chunk
            for chunk in chunks
            if chunk["point_id"] not in existing
            and self.config.allow_legacy_embeddings
            and not chunk.get("document_id")
            and chunk.get("chunk_part_count") == 1
            and isinstance(chunk.get("original_chunk_id"), int)
        ]
        for batch in _batched(legacy_candidates, self.config.qdrant_lookup_batch_size):
            by_legacy_id = {chunk["original_chunk_id"]: chunk for chunk in batch}
            records = self.qdrant.retrieve(
                collection_name=self.config.collection_name,
                ids=list(by_legacy_id),
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                chunk = by_legacy_id.get(record.id)
                payload = record.payload or {}
                if (
                    chunk is not None
                    and payload.get("text") == chunk.get("text")
                    and payload.get("source_file") == chunk.get("source_file")
                ):
                    existing.add(chunk["point_id"])
        return existing

    def upsert(self, embedded: Sequence[tuple[dict[str, Any], list[float]]]) -> None:
        """Persist stable IDs and source metadata, waiting for acknowledgement."""
        points = [
            PointStruct(
                id=chunk["point_id"], vector=vector, payload=create_payload(chunk)
            )
            for chunk, vector in embedded
        ]
        self.qdrant.upsert(
            collection_name=self.config.collection_name, points=points, wait=True
        )
