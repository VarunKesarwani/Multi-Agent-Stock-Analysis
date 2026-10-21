"""Read-only semantic retrieval over annual and educational documents."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import models


class SearchRequest(BaseModel):
    """Optional exact metadata filters; annual reports need no mandatory symbol."""

    model_config = ConfigDict(
        str_strip_whitespace=True, extra="forbid", allow_inf_nan=False
    )
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    document_type: str | None = Field(default=None, min_length=1, max_length=100)
    symbol: str | None = Field(default=None, min_length=1, max_length=100)
    year: str | int | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    min_score: float | None = Field(default=None, ge=-1, le=1)


def metadata_filter(request: SearchRequest) -> models.Filter | None:
    """Preserve existing payload labels and accept integer/string year formats."""
    conditions = []
    for key in ("document_type", "symbol", "topic"):
        value = getattr(request, key)
        if value is not None:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
            )
    if request.year is not None:
        year = str(request.year)
        variants = [
            models.FieldCondition(key="year", match=models.MatchValue(value=year))
        ]
        if year.isdigit():
            variants.append(
                models.FieldCondition(
                    key="year", match=models.MatchValue(value=int(year))
                )
            )
        conditions.append(models.Filter(should=variants))
    return models.Filter(must=conditions) if conditions else None


class Retriever:
    """Reuse the ingestion embedding model and reject incompatible collections."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        """Retrieve passages with source metadata without creating a collection."""
        p = self.pipeline
        if not p.qdrant.collection_exists(p.config.collection_name):
            return []
        p._check_embedding_contract()
        vector = p.embed_texts([request.query])[0]
        # Validate existing dimensions without the ingestion create-on-missing path.
        info = p.qdrant.get_collection(p.config.collection_name).config.params.vectors
        if (
            isinstance(info, dict)
            or info.size != len(vector)
            or info.distance != models.Distance.COSINE
        ):
            raise ValueError(
                "Query model and collection vector configuration do not match"
            )
        response = p.qdrant.query_points(
            collection_name=p.config.collection_name,
            query=vector,
            query_filter=metadata_filter(request),
            limit=request.limit,
            score_threshold=request.min_score,
            with_payload=True,
            with_vectors=False,
        )
        hits = []
        for point in response.points:
            payload = dict(point.payload or {})
            text = payload.pop("text", "")
            if not isinstance(text, str) or not text.strip():
                continue
            hits.append(
                {
                    "point_id": str(point.id),
                    "score": float(point.score),
                    "text": text,
                    "metadata": payload,
                    "citation": {
                        "source_file": payload.get("source_file")
                        or payload.get("source_pdf"),
                        "page": payload.get("page_number") or payload.get("page"),
                        "section": payload.get("section") or payload.get("heading"),
                        "chunk_id": payload.get(
                            "original_chunk_id", payload.get("chunk_id")
                        ),
                        "chunk_part": payload.get("chunk_part"),
                    },
                }
            )
        return hits
