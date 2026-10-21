"""FastAPI read/search and grounded-answer endpoints."""

import logging
from functools import partial

from fastapi import FastAPI, HTTPException

from src.retrieval.retriever import SearchRequest
from src.retrieval.service import open_service

LOG = logging.getLogger(__name__)


def create_app(env_file=None, *, service_factory=None) -> FastAPI:
    """Build an app without opening provider connections during import."""
    app = FastAPI(title="Financial Documents RAG", version="1.0.0")
    factory = service_factory or partial(open_service, env_file)

    @app.get("/health")
    def health() -> dict:
        """Process liveness only; search exercises provider connectivity."""
        return {"status": "ok", "check": "liveness"}

    def invoke(operation: str, request: SearchRequest) -> dict:
        try:
            with factory() as service:
                effective = (
                    request
                    if "limit" in request.model_fields_set
                    else request.model_copy(update={"limit": service.settings.top_k})
                )
                return getattr(service, operation)(effective)
        except Exception as error:
            # Provider exception messages may contain URLs or credentials.
            LOG.error("RAG %s failed (%s)", operation, type(error).__name__)
            raise HTTPException(
                status_code=503,
                detail="RAG dependency or configuration unavailable; check server configuration.",
            ) from None

    @app.post("/search")
    def search(request: SearchRequest) -> dict:
        """Retrieve source passages without answer generation."""
        return invoke("search", request)

    @app.post("/ask")
    def ask(request: SearchRequest) -> dict:
        """Generate an answer grounded in retrieved passages."""
        return invoke("ask", request)

    return app


app = create_app()
