from __future__ import annotations

from typing import Any, Protocol

import httpx
from qdrant_client import QdrantClient, models


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self._model = model
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, trust_env=False)

    def embed(self, text: str) -> list[float]:
        response = self._client.post(
            "/api/embed",
            json={"model": self._model, "input": [text], "truncate": True, "keep_alive": "10m"},
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings") or []
        if not embeddings or not embeddings[0]:
            raise RuntimeError("Ollama returned no embedding for the query.")
        return [float(value) for value in embeddings[0]]

    def ping(self) -> bool:
        try:
            return self._client.get("/api/version").is_success
        except httpx.HTTPError:
            return False


def _match_filter(symbol: str, year: int | str | None, document_type: str | None) -> models.Filter:
    conditions: list[models.Condition] = [
        models.FieldCondition(key="symbol", match=models.MatchValue(value=symbol)),
    ]
    if year is not None:
        year_text = str(year).strip()
        year_variants: list[models.Condition] = [
            models.FieldCondition(key="year", match=models.MatchValue(value=year_text))
        ]
        if year_text.isdigit():
            year_variants.append(
                models.FieldCondition(key="year", match=models.MatchValue(value=int(year_text)))
            )
        conditions.append(models.Filter(should=year_variants))
    if document_type:
        conditions.append(
            models.FieldCondition(key="document_type", match=models.MatchValue(value=document_type))
        )
    return models.Filter(must=conditions)


def _citation(point_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source_file") or payload.get("source_pdf") or "unknown"
    chunk = payload.get("original_chunk_id")
    part = payload.get("chunk_part")
    locator = f"{source}#chunk-{chunk}" if chunk is not None else f"{source}#point-{point_id}"
    if part is not None:
        locator += f"-part-{part}"
    return {
        "id": locator,
        "source_file": source,
        "source_path": payload.get("source_path"),
        "page": payload.get("page") or payload.get("page_number"),
        "section": payload.get("section") or payload.get("heading"),
        "chunk_id": chunk,
        "chunk_part": part,
    }


def _serialize_hit(hit: Any) -> dict[str, Any]:
    payload = dict(hit.payload or {})
    point_id = str(hit.id)
    return {
        "point_id": point_id,
        "score": round(float(hit.score), 6),
        "text": payload.get("text", ""),
        "metadata": {key: value for key, value in payload.items() if key != "text"},
        "citation": _citation(point_id, payload),
    }


class AnnualReportRepository:
    def __init__(
        self,
        qdrant: QdrantClient,
        embedder: Embedder,
        collection: str,
        max_results: int = 20,
    ) -> None:
        self.qdrant = qdrant
        self.embedder = embedder
        self.collection = collection
        self.max_results = max_results

    @classmethod
    def connect(
        cls,
        *,
        qdrant_url: str,
        qdrant_api_key: str | None,
        collection: str,
        ollama_url: str,
        embedding_model: str,
        timeout_seconds: float,
        max_results: int,
    ) -> "AnnualReportRepository":
        return cls(
            QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key,
                timeout=timeout_seconds,
                trust_env=False,
                check_compatibility=False,
            ),
            OllamaEmbedder(ollama_url, embedding_model, timeout_seconds),
            collection,
            max_results,
        )

    def _limit(self, requested: int) -> int:
        if requested < 1:
            raise ValueError("limit must be positive")
        return min(requested, self.max_results)

    def search(
        self,
        *,
        query: str,
        symbol: str,
        year: int | str | None,
        document_type: str | None,
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be blank")
        if len(normalized_query) > 2_000:
            raise ValueError("query must be at most 2000 characters")
        vector = self.embedder.embed(normalized_query)
        response = self.qdrant.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=_match_filter(symbol, year, document_type),
            limit=self._limit(limit),
            score_threshold=min_score,
            with_payload=True,
            with_vectors=False,
        )
        points = getattr(response, "points", response)
        return [_serialize_hit(point) for point in points]

    def health(self) -> dict[str, bool]:
        qdrant_ok = False
        try:
            self.qdrant.get_collection(self.collection)
            qdrant_ok = True
        except Exception:  # Health checks must return a result even when a dependency is unavailable.
            pass
        ping = getattr(self.embedder, "ping", None)
        ollama_ok = bool(ping()) if ping else True
        return {"qdrant": qdrant_ok, "ollama": ollama_ok}
