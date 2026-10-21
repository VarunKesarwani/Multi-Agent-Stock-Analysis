"""Ollama/OpenAI embeddings with validation and bounded retries."""

import logging
import math
import random
import time
from typing import Sequence

import requests

LOG = logging.getLogger(__name__)


class EmbeddingClient:
    """Use a caller-owned HTTP session and validated configuration."""

    def __init__(self, config, session):
        self.config = config
        self.session = session

    @property
    def embed_url(self) -> str:
        return f"{self.config.ollama_base_url.rstrip('/')}/api/embed"

    def _embed_once(self, texts: Sequence[str]) -> list[list[float]]:
        if self.config.embedding_type == "openai":
            response = self.session.post(
                f"{self.config.openai_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                json={
                    "model": self.config.embedding_model,
                    "input": list(texts),
                    "encoding_format": "float",
                },
                timeout=(
                    self.config.connect_timeout_seconds,
                    self.config.read_timeout_seconds,
                ),
            )
            response.raise_for_status()
            data = sorted(
                response.json().get("data", []), key=lambda item: item["index"]
            )
            if [item["index"] for item in data] != list(range(len(texts))):
                raise ValueError("OpenAI returned unexpected embedding indices")
            return self._validate_vectors(
                [item["embedding"] for item in data], len(texts)
            )
        response = self.session.post(
            self.embed_url,
            json={
                "model": self.config.embedding_model,
                "input": list(texts),
                "truncate": True,
                "keep_alive": "10m",
            },
            timeout=(
                self.config.connect_timeout_seconds,
                self.config.read_timeout_seconds,
            ),
        )
        if not response.ok:
            detail = response.text[:1_000].replace("\n", " ")
            raise RuntimeError(f"Ollama HTTP {response.status_code}: {detail}")

        result = response.json()
        embeddings = result.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError(
                "Ollama returned an unexpected number of embeddings: "
                f"expected {len(texts)}, received "
                f"{len(embeddings) if isinstance(embeddings, list) else 'invalid response'}"
            )
        if any(not isinstance(vector, list) or not vector for vector in embeddings):
            raise RuntimeError("Ollama returned an empty or invalid embedding")
        return self._validate_vectors(embeddings, len(texts))

    @staticmethod
    def _validate_vectors(vectors, count):
        if len(vectors) != count or not vectors or not vectors[0]:
            raise ValueError("Unexpected embedding count or empty vector")
        size = len(vectors[0])
        for vector in vectors:
            if len(vector) != size or any(not math.isfinite(float(x)) for x in vector):
                raise ValueError(
                    "Embedding vectors must have equal size and finite values"
                )
        return vectors

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed one batch with bounded exponential-backoff retries."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return self._embed_once(texts)
            except (requests.RequestException, RuntimeError, ValueError) as error:
                last_error = error
                if attempt == self.config.max_retries:
                    break
                delay = self.config.retry_base_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, min(1.0, delay * 0.25))
                LOG.info(
                    f"Embedding attempt {attempt}/{self.config.max_retries} failed "
                    f"for {len(texts)} input(s): {error}. Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
        raise RuntimeError(
            f"Embedding failed after {self.config.max_retries} attempts: {last_error}"
        ) from last_error
